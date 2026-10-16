"""Regrese #8 se skutečným Store/Recorderem; EDC odpovědi jsou syntetické.

Ověřujeme zapsané časové body, znovunačtení JSON, opakování jen mezer,
souběh a zrušení. Tyto vzorky neprohlašují 31. květen za platnost živé SSE.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from custom_components.edc_sharing.api_policy import EdcApiError, EdcAuthenticationError
from custom_components.edc_sharing.calculation import (
    EanInfo,
    profile_date_ranges_backwards,
)
from custom_components.edc_sharing.coordinator import EdcSharingCoordinator
from custom_components.edc_sharing.diagnostics import async_get_config_entry_diagnostics
from custom_components.edc_sharing.health import inspect_statistics_health
from custom_components.edc_sharing.sensor import EdcHistoryBackfillStatusSensor
from tests_homeassistant.test_startup_diagnostics import (
    cache_history,
    make_api,
    make_entry,
)
from tests_homeassistant.test_statistics_health import dst_profile, profile

pytestmark = pytest.mark.freeze_time("2026-10-28T12:00:00Z")


@pytest.fixture(autouse=True)
def no_backfill_delay(monkeypatch):
    """V testu zkrátit pouze prodlevu; skutečný API klient a validátor zůstávají."""
    monkeypatch.setattr("custom_components.edc_sharing.coordinator._BACKFILL_REQUEST_DELAY", 0)


def full_profile(*days):
    """96 čtvrthodin za běžný den: 240 kWh spotřeba, 96 kWh sdílení."""
    raw = profile()
    raw["content"] = []
    for day in days:
        for slot in range(96):
            hour, minute = divmod(slot * 15, 60)
            end_hour, end_minute = divmod((slot + 1) * 15, 60)
            raw["content"].append({
                "date": day,
                "start": f"{hour:02d}:{minute:02d}",
                "end": f"{end_hour:02d}:{end_minute:02d}",
                "values": [1, 0, -2.5, -1.5],
            })
    return raw


def coordinator_for_range(hass, entry, api, start, end):
    """Připravit ručně spuštěný průchod; žádné první načtení či plánovač navíc."""
    coordinator = EdcSharingCoordinator(hass, entry, api)
    coordinator.eans = (EanInfo("target", "target"),)
    coordinator.history_backfill_scan_start = start
    coordinator.history_backfill_cursor = end
    coordinator.history_backfill_status = "running"
    coordinator.history_backfill_total_chunks = len(profile_date_ranges_backwards(start, end))
    entry.runtime_data = SimpleNamespace(coordinator=coordinator, api=api)
    return coordinator


async def test_partial_boundary_imports_valid_data_and_retries_only_gaps_after_restore(
    hass, recorder_mock, hass_storage,
):
    """Částečný první den a absentující den nepohřbí prostřední úplný den.

    Opakování po Store reload opraví jen mezery a nepřičte již zapsané hodiny.
    Existující hodinové statistiky i původní cache zůstávají skutečně čitelné.
    """
    await hass.config.async_set_time_zone("Europe/Prague")
    entry, api = make_entry(hass), make_api(hass)
    raw = full_profile("2026-05-31", "2026-06-01")
    raw["content"][0]["values"][2] = None
    api._request_once.return_value = raw
    coordinator = coordinator_for_range(
        hass, entry, api, date(2026, 5, 31), date(2026, 6, 3),
    )
    await coordinator._async_backfill_history()
    await recorder_mock.async_block_till_done()
    assert coordinator.history_backfill_status == "completed_with_gaps"
    assert coordinator.history_backfill_imported_days == 1
    assert coordinator.history_backfill_imported_hours == 47
    assert set(coordinator._history_days) == {date(2026, 6, 1)}
    assert coordinator.history_backfill_pending_ranges == [
        {"start": "2026-05-31", "end": "2026-06-01", "reason": "missing_measurements"},
        {"start": "2026-06-02", "end": "2026-06-03", "reason": "missing_day"},
    ]
    health = await inspect_statistics_health(hass, entry, date(2026, 5, 31), date(2026, 6, 3))
    assert all(item["points"] == 47 for item in health["statistics"].values())
    assert len(health["statistics"]) == 8
    persisted = hass_storage[coordinator._history_store.key]["data"]
    assert persisted["cursor"] == "2026-05-31"
    assert len(persisted["imported_hour_keys"]) == 47
    await coordinator.async_shutdown()

    restored = EdcSharingCoordinator(hass, entry, api)
    await restored.async_initialize()
    entry.runtime_data.coordinator = restored
    calls = api._request_once.await_count
    assert not restored.async_start_history_backfill(resume_only=True)
    assert api._request_once.await_count == calls
    sensor = EdcHistoryBackfillStatusSensor(entry)
    assert sensor.native_value == "completed_with_gaps"
    assert sensor.extra_state_attributes["history_backfill_progress"] == 100
    assert sensor.extra_state_attributes["history_backfill_pending_days"] == 2
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["history_backfill"]["pending_ranges"] == restored.history_backfill_pending_ranges
    assert "private" not in str(diagnostics)

    async def corrected(_method, _path, payload):
        # Průchod má číst jen oba chybějící dny, nikoli celý původní blok.
        assert payload["dateFrom"] == payload["dateTo"]
        assert payload["dateFrom"] in {"2026-05-31", "2026-06-02"}
        return full_profile(payload["dateFrom"])

    api._request_once.side_effect = corrected
    assert restored.async_start_history_backfill()
    task = restored._history_backfill_task
    assert not restored.async_start_history_backfill()
    await task
    await recorder_mock.async_block_till_done()
    assert api._request_once.await_count == calls + 2
    assert restored.history_backfill_status == "completed"
    assert restored.history_backfill_pending_ranges == []
    assert restored.history_backfill_imported_days == 3
    assert restored.history_backfill_imported_hours == 72
    assert len(restored._history_days) == 3
    health = await inspect_statistics_health(hass, entry, date(2026, 5, 31), date(2026, 6, 3))
    assert all(item["points"] == 72 for item in health["statistics"].values())
    await restored.async_shutdown()


async def test_legacy_cache_is_preserved_and_corrupt_gap_ledger_cannot_claim_success(
    hass, recorder_mock, hass_storage,
):
    """Store v1 bez nových polí zachová kWh; poškozená evidence vyžádá nový průchod."""
    entry, api = make_entry(hass), make_api(hass)
    await cache_history(hass, entry)
    coordinator = EdcSharingCoordinator(hass, entry, api)
    await coordinator.async_initialize()
    assert coordinator.history_backfill_status == "completed"
    assert coordinator.history_backfill_pending_ranges == []
    assert float(coordinator._history_days[date(2026, 10, 12)].shared) == 10
    stored = hass_storage[coordinator._history_store.key]["data"]
    stored.update(
        pending_ranges=[{"start": "bad-date", "end": "2026-10-13", "reason": "missing_day"}],
        scan_start="2025-10-14", scan_end="2026-09-01",
    )
    await coordinator._history_store.async_save(stored)
    await coordinator.async_initialize()
    assert coordinator.history_backfill_status == "failed"
    assert coordinator.history_backfill_cursor == date(2026, 9, 1)
    assert float(coordinator._history_days[date(2026, 10, 12)].shared) == 10
    await coordinator.async_shutdown()


@pytest.mark.parametrize("one_sided", [False, True])
async def test_empty_and_one_sided_profiles_are_pending_not_zero(
    hass, recorder_mock, one_sided,
):
    """Prázdno ani jediná role nedokazují počátek skupiny a nesmějí tvořit kWh."""
    entry, api = make_entry(hass), make_api(hass)
    raw = full_profile("2026-05-31")
    if one_sided:
        raw["valueColumns"] = raw["valueColumns"][:2]
        for row in raw["content"]:
            row["values"] = row["values"][:2]
    else:
        raw = {"content": []}
    api._request_once.return_value = raw
    coordinator = coordinator_for_range(hass, entry, api, date(2026, 5, 31), date(2026, 6, 2))
    await coordinator._async_backfill_history()
    assert coordinator.history_backfill_status == "completed_with_gaps"
    assert coordinator.history_backfill_pending_ranges == [{
        "start": "2026-05-31", "end": "2026-06-02",
        "reason": "unverified_validity" if one_sided else "missing_day",
    }]
    assert coordinator.history_backfill_imported_days == 0
    assert coordinator.history_backfill_imported_hours == 0
    assert not coordinator._history_days
    await recorder_mock.async_block_till_done()
    health = await inspect_statistics_health(hass, entry, date(2026, 5, 31), date(2026, 6, 2))
    assert all(item["points"] == 0 for item in health["statistics"].values())
    await coordinator.async_shutdown()


@pytest.mark.parametrize("failure", ["network", "auth", "schema", "resolution"])
async def test_real_errors_keep_cursor_and_existing_pending_ranges(hass, recorder_mock, failure):
    """Výjimka z povolené kvality nesmí oslabit transport, přihlášení či schéma."""
    entry, api = make_entry(hass), make_api(hass)
    if failure == "network":
        api._request_once.side_effect = EdcApiError("Síť není dostupná.", category="network")
    elif failure == "auth":
        api._request_once.side_effect = EdcAuthenticationError("Přihlášení odmítnuto.")
    elif failure == "schema":
        api._request_once.return_value = {"renamedContent": []}
    else:
        raw = full_profile("2026-05-31")
        raw["content"][0]["end"] = "00:17"
        api._request_once.return_value = raw
    coordinator = coordinator_for_range(hass, entry, api, date(2026, 5, 31), date(2026, 6, 1))
    coordinator._history_backfill_gaps = {date(2026, 6, 2): "missing_day"}
    await coordinator._async_backfill_history()
    assert coordinator.history_backfill_status == "failed"
    assert coordinator.history_backfill_cursor == date(2026, 6, 1)
    assert coordinator.history_backfill_processed_chunks == 0
    assert coordinator.history_backfill_imported_hours == 0
    assert coordinator.history_backfill_pending_ranges == [{
        "start": "2026-06-02", "end": "2026-06-03", "reason": "missing_day",
    }]
    await coordinator.async_shutdown()


@pytest.mark.parametrize(("day", "hours"), [("2026-03-29", 23), ("2026-10-25", 25)])
async def test_dst_days_remain_complete(hass, recorder_mock, day, hours):
    """Změna času není mezera; obě podzimní 02:00 mají odlišné UTC klíče."""
    await hass.config.async_set_time_zone("Europe/Prague")
    entry, api = make_entry(hass), make_api(hass)
    api._request_once.return_value = dst_profile(day)
    start = date.fromisoformat(day)
    coordinator = coordinator_for_range(hass, entry, api, start, start + timedelta(days=1))
    await coordinator._async_backfill_history()
    assert coordinator.history_backfill_status == "completed"
    assert coordinator.history_backfill_imported_days == 1
    assert coordinator.history_backfill_imported_hours == hours
    await recorder_mock.async_block_till_done()
    health = await inspect_statistics_health(hass, entry, start, start + timedelta(days=1))
    assert all(item["points"] == hours for item in health["statistics"].values())
    await coordinator.async_shutdown()


async def test_cancelled_scan_resumes_older_block_and_persisted_gap(hass, recorder_mock):
    """Zrušení po prvním Store zápisu neztratí starší blok ani jeho novou mezeru."""
    entry, api = make_entry(hass), make_api(hass)
    waiting = asyncio.Event()

    async def interrupted(_method, _path, payload):
        if payload["dateFrom"] == "2026-05-31":
            waiting.set()
            await asyncio.Event().wait()
        return {"content": []}

    api._request_once.side_effect = interrupted
    coordinator = coordinator_for_range(hass, entry, api, date(2026, 5, 31), date(2026, 7, 2))
    task = asyncio.create_task(coordinator._async_backfill_history())
    await asyncio.wait_for(waiting.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert coordinator.history_backfill_status == "paused"
    assert coordinator.history_backfill_cursor == date(2026, 6, 1)
    assert coordinator.history_backfill_processed_chunks == 1
    assert coordinator.history_backfill_pending_ranges == [{
        "start": "2026-06-01", "end": "2026-07-02", "reason": "missing_day",
    }]
    await coordinator.async_shutdown()

    restored = EdcSharingCoordinator(hass, entry, api)
    await restored.async_initialize()
    requested = []

    async def recovered(_method, _path, payload):
        requested.append((payload["dateFrom"], payload["dateTo"]))
        raw = profile()
        start, end = date.fromisoformat(payload["dateFrom"]), date.fromisoformat(payload["dateTo"])
        raw["content"] = [
            {"date": (start + timedelta(days=offset)).isoformat(), "values": [1, 0, -2.5, -1.5]}
            for offset in range((end - start).days + 1)
        ]
        return raw

    api._request_once.side_effect = recovered
    assert restored.async_start_history_backfill(resume_only=True)
    await restored._history_backfill_task
    assert requested == [("2026-05-31", "2026-05-31"), ("2026-06-01", "2026-07-01")]
    assert restored.history_backfill_status == "completed"
    assert restored.history_backfill_processed_chunks == 2
    assert restored.history_backfill_imported_days == 32
    await restored.async_shutdown()
