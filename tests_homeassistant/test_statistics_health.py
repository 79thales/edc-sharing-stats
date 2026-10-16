"""Skutečný Recorder: zápis, čtení přes stejné API jako graf a oprava bodů."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_test_home_assistant,
)

from custom_components.edc_sharing.calculation import (
    EanInfo,
    parse_daily_profile,
    parse_hourly_profile,
    parse_hourly_target_profiles,
)
from custom_components.edc_sharing.coordinator import EdcSharingCoordinator
from custom_components.edc_sharing.diagnostics import async_get_config_entry_diagnostics
from custom_components.edc_sharing.health import (
    async_register_health_commands,
    inspect_statistics_health,
)
from custom_components.edc_sharing.history import (
    async_import_hourly_history,
    async_import_target_hourly_history,
)

# Čas zmrazit před vytvořením auth fixture: posun až v testu by zneplatnil JWT.
pytestmark = pytest.mark.freeze_time("2026-10-14T12:00:00Z")


def profile():
    return {
        "valueColumns": [
            {"ean": "producer", "type": "D", "dir": "IN"},
            {"ean": "producer", "type": "D", "dir": "OUT"},
            {"ean": "target", "type": "O", "dir": "IN"},
            {"ean": "target", "type": "O", "dir": "OUT"},
        ],
        "content": [
            {
                "date": "2026-10-12",
                "start": f"12:{minute:02d}:00",
                "end": "13:00:00" if minute == 45 else f"12:{minute + 15:02d}:00",
                "values": [{"v": 1}, {"v": 0}, {"v": -2.5}, {"v": -1.5}],
            }
            for minute in (0, 15, 30, 45)
        ],
    }


def dst_profile(day):
    """Nezávislé 23/25 hodinové vzorky: opakovaná 02:00 není duplicita energie.

    Každý hodinový řádek má 16 kWh spotřebu, 6 kWh síť a 10 kWh sdílení.
    Jarní interval 01–03 trvá v UTC hodinu, podzimní 02–02 rovněž.
    """
    result = profile()
    starts = (
        [0, 1, *range(3, 24)] if day == "2026-03-29" else [0, 1, 2, 2, *range(3, 24)]
    )
    result["content"] = []
    for index, hour in enumerate(starts):
        end = (
            3
            if day == "2026-03-29" and hour == 1
            else 2
            if day == "2026-10-25" and index == 2
            else hour + 1
        )
        result["content"].append(
            {
                "date": day,
                "start": f"{hour:02d}:00:00",
                "end": f"{end:02d}:00:00",
                "values": [{"v": 10}, {"v": 0}, {"v": -16}, {"v": -6}],
            }
        )
    return result


def make_entry(hass):
    entry = MockConfigEntry(
        domain="edc_sharing",
        data={"sse_id": 1, "sse_name": "Synthetic group"},
        version=2,
    )
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            eans=(EanInfo("target", "target"),),
            data_quality={"queued_hours": 1},
            data=SimpleNamespace(latest_day=date(2026, 10, 12)),
            last_attempt_result="success",
        )
    )
    return entry


def queue(hass, raw):
    tz = ZoneInfo("Europe/Prague")
    now = datetime.now(UTC)
    async_import_hourly_history(
        hass,
        sse_id=1,
        sse_name="Synthetic group",
        hours=parse_hourly_profile(raw, local_tz=tz),
        sale_price=Decimal(2),
        now=now,
        local_tz=tz,
    )
    async_import_target_hourly_history(
        hass,
        sse_id=1,
        sse_name="Synthetic group",
        ean="target",
        target_name="Synthetic target",
        hours=parse_hourly_target_profiles(raw, local_tz=tz),
        now=now,
        local_tz=tz,
    )


async def test_real_recorder_read_correction_and_empty_period(
    hass, recorder_mock, hass_ws_client, freezer
):
    """D09/D10: žádný mock zápisu/SQL; stejná ID a mean jako nativní graf."""
    freezer.move_to("2026-10-14T12:00:00Z")
    await hass.config.async_set_time_zone("Europe/Prague")
    entry = make_entry(hass)
    raw = profile()
    queue(hass, raw)
    await recorder_mock.async_block_till_done()
    async_register_health_commands(hass)
    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 1, "type": "edc_sharing/statistics/health", "entry_id": entry.entry_id}
    )
    result = await client.receive_json()
    assert result["success"]
    statistics = result["result"]["statistics"]
    assert statistics["edc_sharing:1_shared_hourly"]["points"] == 1
    assert statistics["edc_sharing:1_target_shared_hourly"]["points"] == 1
    assert statistics["edc_sharing:1_target_shared_hourly"]["unit"] == "kWh"
    assert statistics["edc_sharing:1_target_coverage_hourly"]["unit"] == "%"
    assert (
        statistics["edc_sharing:1_shared_hourly"]["first"]
        == "2026-10-12T10:00:00+00:00"
    )
    await client.send_json(
        {
            "id": 2,
            "type": "recorder/statistics_during_period",
            "start_time": "2026-10-11T22:00:00Z",
            "end_time": "2026-10-12T22:00:00Z",
            "period": "hour",
            "statistic_ids": [
                f"edc_sharing:1_target_{metric}_hourly"
                for metric in ("shared", "consumption", "grid", "coverage")
            ],
            "types": ["mean"],
        }
    )
    response = await client.receive_json()
    assert response["success"]
    assert response["result"]["edc_sharing:1_target_shared_hourly"][0]["mean"] == 4
    assert (
        response["result"]["edc_sharing:1_target_consumption_hourly"][0]["mean"] == 10
    )
    assert response["result"]["edc_sharing:1_target_grid_hourly"][0]["mean"] == 6
    assert response["result"]["edc_sharing:1_target_coverage_hourly"][0]["mean"] == 40
    queue(hass, raw)
    raw["content"][0]["values"][3]["v"] = -1
    queue(hass, raw)
    await recorder_mock.async_block_till_done()
    health = await inspect_statistics_health(
        hass, entry, date(2026, 10, 12), date(2026, 10, 13)
    )
    assert health["statistics"]["edc_sharing:1_target_shared_hourly"]["points"] == 1
    await client.send_json(
        {
            "id": 3,
            "type": "recorder/statistics_during_period",
            "start_time": "2026-10-11T22:00:00Z",
            "end_time": "2026-10-12T22:00:00Z",
            "period": "hour",
            "statistic_ids": ["edc_sharing:1_target_shared_hourly"],
            "types": ["mean"],
        }
    )
    response = await client.receive_json()
    assert response["result"]["edc_sharing:1_target_shared_hourly"][0]["mean"] == 4.5
    empty = await inspect_statistics_health(
        hass, entry, date(2026, 10, 13), date(2026, 10, 14)
    )
    assert (
        empty["statistics"]["edc_sharing:1_shared_hourly"]["status"] == "empty_period"
    )


async def test_health_requires_admin(
    hass, recorder_mock, hass_ws_client, hass_read_only_access_token
):
    entry = make_entry(hass)
    async_register_health_commands(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await client.send_json(
        {
            "id": 1,
            "type": "edc_sharing/statistics/health",
            "entry_id": entry.entry_id,
            "fresh": True,
        }
    )
    response = await client.receive_json()
    assert not response["success"]


async def test_shareable_diagnostics_omit_secrets_and_arbitrary_new_fields(hass):
    """A14: standardní export neobsahuje konfiguraci ani nové interní atributy."""
    entry = make_entry(hass)
    entry.runtime_data.api = SimpleNamespace(
        last_status=400, last_failure_category="validation", password="private-secret"
    )
    coordinator = entry.runtime_data.coordinator
    coordinator.last_success_at = None
    coordinator.next_attempt_at = None
    coordinator.data_quality["unapproved_new_field"] = "private-secret"
    coordinator.bank_account = "private-secret"
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["failure_category"] == "validation"
    assert "private-secret" not in str(result)
    assert "Synthetic" not in str(result)
    assert "edc_sharing:" not in str(result)


async def test_fresh_probe_is_explicit_and_never_imports(
    hass, recorder_mock, hass_ws_client
):
    """Admin musí výslovně požádat o nový EDC read; žádný zápis ani jiná akce."""
    entry = make_entry(hass)
    api = SimpleNamespace(
        async_get_groups=AsyncMock(return_value=[{"sseId": 1}]),
        async_get_daily_profile=AsyncMock(return_value=profile()),
    )
    entry.runtime_data.api = api
    async_register_health_commands(hass)
    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 1, "type": "edc_sharing/statistics/health", "entry_id": entry.entry_id}
    )
    assert (await client.receive_json())["success"]
    api.async_get_groups.assert_not_awaited()
    await client.send_json(
        {
            "id": 2,
            "type": "edc_sharing/statistics/health",
            "entry_id": entry.entry_id,
            "fresh": True,
        }
    )
    response = await client.receive_json()
    assert response["success"]
    assert response["result"]["connection_probe"]["complete_hours"] == 1
    api.async_get_daily_profile.assert_awaited_once_with(
        1, date(2026, 10, 12), date(2026, 10, 13)
    )
    await recorder_mock.async_block_till_done()
    result = await inspect_statistics_health(
        hass, entry, date(2026, 10, 12), date(2026, 10, 13)
    )
    assert all(item["points"] == 0 for item in result["statistics"].values())


async def test_partial_hours_are_not_queued(hass, recorder_mock):
    entry = make_entry(hass)
    raw = profile()
    raw["content"].pop()
    queue(hass, raw)
    await recorder_mock.async_block_till_done()
    result = await inspect_statistics_health(
        hass, entry, date(2026, 10, 12), date(2026, 10, 13)
    )
    assert all(item["points"] == 0 for item in result["statistics"].values())


async def test_partial_backfill_preserves_gap_history_and_restore(
    hass, recorder_mock, hass_storage, monkeypatch,
):
    """Neúplný blok uloží mezeru, uchová dobrou historii i existující Recorder.

    JSON persistence používá standardní HA storage fixture, nikoli nový vlastní
    serializér. Obnovení probíhá v nové instanci HA; Recorder zápis/čtení zůstává
    skutečné, bez mocku. Tento test neprohlašuje fixture za test fyzického disku.
    """
    # Se zmrazeným časem nečekat na nově dosaženou produkční prodlevu.
    monkeypatch.setattr("custom_components.edc_sharing.coordinator._BACKFILL_REQUEST_DELAY", 0)
    await hass.config.async_set_time_zone("Europe/Prague")
    entry = make_entry(hass)
    queue(hass, profile())
    await recorder_mock.async_block_till_done()
    raw = profile()
    raw["content"].pop()
    api = SimpleNamespace(async_get_daily_profile=AsyncMock(return_value=raw))
    coordinator = EdcSharingCoordinator(hass, entry, api)
    coordinator.history_backfill_scan_start = date(2026, 10, 12)
    coordinator.history_backfill_cursor = date(2026, 10, 13)
    coordinator.history_backfill_status = "running"
    coordinator.history_backfill_total_chunks = 1
    prior = profile()
    prior["content"] = [
        {"date": "2026-10-10", "values": [{"v": 10}, {"v": 0}, {"v": -16}, {"v": -6}]}
    ]
    coordinator._history_days = {row.day: row for row in parse_daily_profile(prior)}
    entry.runtime_data.coordinator = coordinator
    await coordinator._async_backfill_history()
    assert coordinator.history_backfill_status == "completed_with_gaps"
    assert coordinator.history_backfill_cursor == date(2026, 10, 12)
    assert coordinator.history_backfill_processed_chunks == 1
    assert coordinator.history_backfill_imported_hours == 0
    assert float(coordinator._history_days[date(2026, 10, 10)].shared) == 10
    assert (
        hass_storage[coordinator._history_store.key]["data"]["cursor"] == "2026-10-12"
    )
    assert hass_storage[coordinator._history_store.key]["data"]["pending_ranges"] == [{
        "start": "2026-10-12", "end": "2026-10-13", "reason": "incomplete_day",
    }]
    await recorder_mock.async_block_till_done()
    result = await inspect_statistics_health(
        hass, entry, date(2026, 10, 12), date(2026, 10, 13)
    )
    assert result["statistics"]["edc_sharing:1_shared_hourly"]["points"] == 1
    async with async_test_home_assistant(
        config_dir=hass.config.config_dir
    ) as restarted:
        try:
            restored = EdcSharingCoordinator(restarted, entry, api)
            await restored.async_initialize()
            assert restored.history_backfill_status == "completed_with_gaps"
            assert restored.history_backfill_cursor == date(2026, 10, 12)
            assert restored.history_backfill_pending_ranges == coordinator.history_backfill_pending_ranges
            assert float(restored._history_days[date(2026, 10, 10)].shared) == 10
        finally:
            await restarted.async_stop(force=True)


@pytest.mark.parametrize("persistent_database", [True])
async def test_statistics_survive_real_recorder_restart(
    async_test_recorder, hass, freezer
):
    """P0: zavřít skutečný Recorder a načíst stejnou databázi v nové instanci HA."""
    freezer.move_to("2026-10-14T12:00:00Z")
    async with async_test_recorder(hass) as instance:
        queue(hass, profile())
        await instance.async_block_till_done()
    await hass.async_stop(force=True)
    async with (
        async_test_home_assistant(config_dir=hass.config.config_dir) as restarted,
        async_test_recorder(restarted) as instance,
    ):
        await restarted.config.async_set_time_zone("Europe/Prague")
        entry = make_entry(restarted)
        result = await inspect_statistics_health(
            restarted, entry, date(2026, 10, 12), date(2026, 10, 13)
        )
        assert result["statistics"]["edc_sharing:1_target_shared_hourly"]["points"] == 1
        # Pomocný contextmanager pouze vytvoří instanci; test musí provést
        # skutečný shutdown, jinak zůstanou denní cleanup callbacky Recorderu.
        await restarted.async_stop(force=True)
