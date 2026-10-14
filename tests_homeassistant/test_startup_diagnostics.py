"""Skutečný setup HA: první chyba, legacy čekání, cache a bezpečná obnova.

Síť EDC je nahrazena pouze na hranici jednotlivého požadavku. Koordinátor,
první refresh, stav config entry, Store, entity a plánování zůstávají skutečné.
Nejde o test živého EDC ani fyzického disku; storage fixture používá HA JSON.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.edc_sharing.api import EdcApiClient
from custom_components.edc_sharing.api_policy import ApiAccountState
from custom_components.edc_sharing.calculation import (
    parse_daily_profile,
    parse_daily_target_profiles,
)
from custom_components.edc_sharing.coordinator import (
    EdcSharingCoordinator,
    _serialize_daily_row,
    _serialize_target_daily_row,
)
from custom_components.edc_sharing.diagnostics import async_get_config_entry_diagnostics
from custom_components.edc_sharing.health import async_register_health_commands
from tests_homeassistant.test_statistics_health import profile

pytestmark = pytest.mark.freeze_time("2026-10-14T07:00:00Z")


def make_entry(hass):
    entry = MockConfigEntry(
        domain="edc_sharing",
        version=2,
        data={
            "username": "private-user",
            "password": "private-password",
            "sse_id": 1,
            "sse_name": "Synthetic group",
        },
    )
    entry.add_to_hass(hass)
    return entry


def make_api(hass):
    state = ApiAccountState()
    state.persist = Store(hass, 1, "edc_sharing.test.api_wait").async_save
    api = EdcApiClient(
        async_get_clientsession(hass), "private-user", "private-password", state
    )
    api.last_status = 200
    api._request_once = AsyncMock(return_value={"renamedContent": []})
    return api


async def cache_history(hass, entry):
    """Uložit skutečným Store validní den 10 kWh sdílení, nikoli falešnou nulu."""
    raw = profile()
    raw["content"] = [{"date": "2026-10-12", "values": [10, 0, -16, -6]}]
    coordinator = EdcSharingCoordinator(hass, entry, make_api(hass))
    await coordinator._history_store.async_save(
        {
            "status": "completed",
            "earliest_date": "2026-10-12",
            "daily_rows": [
                _serialize_daily_row(row) for row in parse_daily_profile(raw)
            ],
            "target_daily_rows": [
                _serialize_target_daily_row(row)
                for row in parse_daily_target_profiles(raw)
            ],
        }
    )
    await coordinator.async_shutdown()


async def test_first_setup_failure_is_logged_persisted_and_exported_without_runtime(
    hass, recorder_mock, hass_storage, hass_ws_client, caplog
):
    await hass.config.async_set_time_zone("Europe/Prague")
    entry, api = make_entry(hass), make_api(hass)
    with (
        patch(
            "custom_components.edc_sharing.async_setup",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.edc_sharing.async_get_api_client",
            new=AsyncMock(return_value=api),
        ),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    diagnostic = await async_get_config_entry_diagnostics(hass, entry)
    assert not diagnostic["ready"]
    assert diagnostic["original_failure"]["reason_code"] == "profile_lists"
    assert diagnostic["original_failure"]["http_status"] == 200
    assert diagnostic["original_failure"]["phase"] == "profile_validation"
    assert "strukturu profilových seznamů" in caplog.text
    assert "private" not in str(diagnostic)
    persisted = hass_storage["edc_sharing.test.api_wait"]["data"]
    assert persisted["last_failure"]["reason_code"] == "profile_lists"
    async_register_health_commands(hass)
    client = await hass_ws_client(hass)
    calls = api._request_once.await_count
    await client.send_json(
        {
            "id": 1,
            "type": "edc_sharing/statistics/health",
            "entry_id": entry.entry_id,
            "fresh": True,
        }
    )
    result = await client.receive_json()
    assert result["success"]
    assert not result["result"]["ready"]
    assert (
        result["result"]["diagnostics"]["original_failure"]["reason_code"]
        == "profile_lists"
    )
    assert api._request_once.await_count == calls


async def test_cached_start_exposes_diagnostics_but_does_not_import_or_send_until_recovery(
    hass, recorder_mock, hass_storage, caplog
):
    await hass.config.async_set_time_zone("Europe/Prague")
    entry, api = make_entry(hass), make_api(hass)
    await cache_history(hass, entry)
    until = datetime.now(UTC) + timedelta(hours=6)
    scope = api.account_state.scope("/profiles-data/standard/overview", {"sseId": 1})
    api.account_state.restore(
        {scope: {"until": until.isoformat(), "category": "contract"}}
    )
    with (
        patch(
            "custom_components.edc_sharing.async_setup",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.edc_sharing.async_get_api_client",
            new=AsyncMock(return_value=api),
        ),
        patch(
            "custom_components.edc_sharing.report.EdcReportManager.async_start"
        ) as start_reports,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        coordinator = entry.runtime_data.coordinator
        assert coordinator.cached_startup
        assert not coordinator.last_update_success
        assert not coordinator._history_import_enabled
        assert coordinator._history_backfill_task is None
        assert float(coordinator.data.latest.shared) == 10
        assert coordinator.data.latest_day == date(2026, 10, 12)
        assert coordinator.next_attempt_at >= until - timedelta(seconds=1)
        assert coordinator.update_interval.total_seconds() >= 21599
        api._request_once.assert_not_awaited()
        start_reports.assert_not_called()
        registry = er.async_get(hass)
        diagnostic_id = registry.async_get_entity_id(
            "sensor", "edc_sharing", "1_last_update_attempt"
        )
        state = hass.states.get(diagnostic_id)
        assert state is not None and state.state != "unavailable"
        assert state.attributes["data_quality"]["cached_only"]
        diagnostic = await async_get_config_entry_diagnostics(hass, entry)
        assert diagnostic["cached_startup"]
        assert diagnostic["original_failure"]["reason_code"] == "legacy"
        assert "Starší verze neuložila" in caplog.text
        assert "private" not in str(diagnostic)

        # Simulovat až uplynutí původní lhůty; neobcházet živé omezení EDC.
        api.account_state.blocks.clear()
        api.account_state.deadlines.clear()

        async def valid_read(_method, _path, payload):
            raw = profile()
            raw["content"] = [{"date": payload["dateFrom"], "values": [10, 0, -16, -6]}]
            return raw

        api._request_once.side_effect = valid_read
        await coordinator.async_refresh()
        assert coordinator.last_update_success
        assert not coordinator.cached_startup
        assert coordinator._history_import_enabled
        assert coordinator.update_interval == timedelta(hours=1)
        start_reports.assert_called_once()
        await coordinator.async_refresh()
        start_reports.assert_called_once()
    await hass.config_entries.async_unload(entry.entry_id)


async def test_old_local_schema_failure_does_not_discard_valid_recent_day(
    hass, recorder_mock
):
    await hass.config.async_set_time_zone("Europe/Prague")
    entry, api = make_entry(hass), make_api(hass)

    async def read(_method, _path, payload):
        if payload["dateFrom"] < "2026-10-01":
            return {"renamedContent": []}
        raw = profile()
        raw["content"] = [{"date": "2026-10-12", "values": [10, 0, -16, -6]}]
        return raw

    api._request_once.side_effect = read
    coordinator = EdcSharingCoordinator(hass, entry, api)
    result = await coordinator._async_update_data()
    assert result.latest_day == date(2026, 10, 12)
    assert float(result.latest.shared) == 10
    assert coordinator.data_quality["incomplete_blocks"] == 1
    assert coordinator.data_quality["hourly_reason"] == "daily_only"
    assert api._request_once.await_count == 2
    assert api.account_state.last_failure["reason_code"] == "profile_lists"
    await coordinator.async_shutdown()


async def test_all_null_historical_day_cannot_advance_cursor(hass, recorder_mock):
    entry, api = make_entry(hass), make_api(hass)
    raw = profile()
    raw["content"] = [{"date": "2026-10-12", "values": [None, None, None, None]}]
    api._request_once.return_value = raw
    coordinator = EdcSharingCoordinator(hass, entry, api)
    coordinator.history_backfill_scan_start = date(2026, 10, 12)
    coordinator.history_backfill_cursor = date(2026, 10, 13)
    coordinator.history_backfill_status = "running"
    await coordinator._async_backfill_history()
    assert coordinator.history_backfill_status == "failed"
    assert coordinator.history_backfill_cursor == date(2026, 10, 13)
    assert coordinator.history_backfill_processed_chunks == 0
    assert coordinator.history_backfill_imported_days == 0
    assert coordinator.history_backfill_imported_hours == 0
    await coordinator.async_shutdown()
