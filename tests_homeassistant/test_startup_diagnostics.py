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
from custom_components.edc_sharing.api_policy import (
    ApiAccountState,
    EdcApiError,
    EdcAuthenticationError,
)
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
from custom_components.edc_sharing.health import (
    async_register_health_commands,
    inspect_statistics_health,
)
from tests_homeassistant.test_statistics_health import profile, queue

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
            "sale_price": 2,
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


async def test_login_step_is_exported_and_persisted_by_real_ha_setup(
    hass, recorder_mock, hass_storage, caplog
):
    """HA Store i export zachovají přesný HTTP krok neúspěšného prvního startu.

    Nahrazen je pouze síťový požadavek. Start, plánovač, záznam do Store a
    sdílitelná diagnostika jsou skutečné; žádný EDC login se neodesílá.
    """
    entry, api = make_entry(hass), make_api(hass)
    api._request_once.side_effect = EdcApiError(
        "Přihlašovací služba EDC vrátila HTTP 403.",
        category="permission",
        status=403,
        phase="authentication",
        authentication_step="credentials_redirect_get",
    )
    with (
        patch("custom_components.edc_sharing.async_setup", new=AsyncMock(return_value=True)),
        patch("custom_components.edc_sharing.async_get_api_client", new=AsyncMock(return_value=api)),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    diagnostic = await async_get_config_entry_diagnostics(hass, entry)
    failure = diagnostic["original_failure"]
    assert failure["authentication_step"] == "credentials_redirect_get"
    assert failure["http_status"] == 403
    assert failure["wait_source"] == "local_policy"
    assert "krok=credentials_redirect_get" in caplog.text
    persisted = hass_storage["edc_sharing.test.api_wait"]["data"]
    restored = ApiAccountState()
    restored.restore(persisted)
    assert restored.diagnostic_failure()["authentication_step"] == "credentials_redirect_get"
    assert "private" not in str((diagnostic, persisted))


async def test_cached_start_exposes_diagnostics_but_does_not_import_or_send_until_recovery(
    hass, recorder_mock, hass_storage, caplog
):
    await hass.config.async_set_time_zone("Europe/Prague")
    entry, api = make_entry(hass), make_api(hass)
    await cache_history(hass, entry)
    # Před aktualizací existovaly tyto uživatelem přejmenované entity.
    # Oprava nesmí vyžadovat nová ID, mazání zařízení ani regeneraci dashboardu.
    registry = er.async_get(hass)
    group_sensor = registry.async_get_or_create(
        "sensor",
        "edc_sharing",
        "1_shared_today",
        config_entry=entry,
        suggested_object_id="my_saved_group_sharing",
    )
    source_sensor = registry.async_get_or_create(
        "sensor",
        "edc_sharing",
        "1_sharing_ean_producer",
        config_entry=entry,
        suggested_object_id="my_saved_source_ean",
    )
    target_sensor = registry.async_get_or_create(
        "sensor",
        "edc_sharing",
        "1_target_target_shared_latest_available_day",
        config_entry=entry,
        suggested_object_id="my_saved_target_sharing",
    )
    registry.async_update_entity(group_sensor.entity_id, name="My retained sharing")
    queue(hass, profile())
    await recorder_mock.async_block_till_done()
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
        group_state = hass.states.get(group_sensor.entity_id)
        assert float(group_state.state) == 10
        assert group_state.attributes["data_date"] == "2026-10-12"
        assert group_state.attributes["friendly_name"] == "My retained sharing"
        assert group_state.attributes["data_source"] == "retained_history"
        assert group_state.attributes["last_fetch_result"] == "failed"
        assert hass.states.get(source_sensor.entity_id).state == "producer"
        assert float(hass.states.get(target_sensor.entity_id).state) == 10
        total_id = registry.async_get_entity_id(
            "sensor", "edc_sharing", "1_surplus_utilization_total"
        )
        total_state = hass.states.get(total_id)
        assert float(total_state.state) == 100
        assert total_state.attributes["shared_kwh"] == 10
        assert total_state.attributes["available_days"] == 1
        assert total_state.attributes["data_start"] == "2026-10-12"
        assert total_state.attributes["data_end"] == "2026-10-12"
        history = await inspect_statistics_health(
            hass, entry, date(2026, 10, 12), date(2026, 10, 13)
        )
        assert history["statistics"]["edc_sharing:1_shared_hourly"]["points"] == 1
        diagnostic = await async_get_config_entry_diagnostics(hass, entry)
        assert diagnostic["cached_startup"]
        assert diagnostic["original_failure"]["reason_code"] == "legacy"
        assert "Starší verze neuložila" in caplog.text
        assert "private" not in str(diagnostic)

        # Opakovaná čekací chyba nesmí znepřístupnit hodnoty/atributy ani
        # měnit jejich data. Diagnostika se přitom aktualizuje i po dvou chybách.
        await coordinator.async_refresh()
        assert float(hass.states.get(group_sensor.entity_id).state) == 10
        assert (
            hass.states.get(group_sensor.entity_id).attributes["data_date"]
            == "2026-10-12"
        )
        api._request_once.assert_not_awaited()
        start_reports.assert_not_called()

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


async def test_ean_metadata_survives_storage_reload_without_registry(
    hass, hass_storage
):
    entry, api = make_entry(hass), make_api(hass)
    await cache_history(hass, entry)
    coordinator = EdcSharingCoordinator(hass, entry, api)
    await coordinator.async_initialize()
    from custom_components.edc_sharing.calculation import EanInfo

    coordinator.eans = (EanInfo("producer", "sharing"), EanInfo("target", "target"))
    await coordinator._async_save_history_backfill_state()
    restored = EdcSharingCoordinator(hass, entry, api)
    await restored.async_initialize()
    assert restored.eans == coordinator.eans
    assert float(restored._history_days[date(2026, 10, 12)].shared) == 10
    await coordinator.async_shutdown()
    await restored.async_shutdown()


@pytest.mark.parametrize("pending_day", ("omitted", "null", "NaN", "Infinity"))
async def test_pending_final_day_keeps_previous_day_and_existing_sensors_available(
    hass, recorder_mock, pending_day
):
    """Den čekající na zveřejnění neruší předchozí kWh ani jejich skutečné datum.

    Testuje se obvyklé zpoždění EDC: poslední den není vůbec v odpovědi,
    nebo má známé sloupce s null/NaN/Infinity. Žádná varianta nepřidává
    falešný nulový den ani neposouvá hodnotu 12. října na 13. října.
    """
    await hass.config.async_set_time_zone("Europe/Prague")
    entry, api = make_entry(hass), make_api(hass)
    await cache_history(hass, entry)

    async def valid_history(_method, _path, payload):
        raw = profile()
        raw["content"] = []
        if payload["dateFrom"] <= "2026-10-12" <= payload["dateTo"]:
            raw["content"].append(
                {"date": "2026-10-12", "values": [10, 0, -16, -6]}
            )
            if pending_day != "omitted":
                marker = None if pending_day == "null" else pending_day
                raw["content"].append(
                    {"date": "2026-10-13", "values": [marker] * 4}
                )
        return raw

    api._request_once.side_effect = valid_history
    with (
        patch(
            "custom_components.edc_sharing.async_setup",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.edc_sharing.async_get_api_client",
            new=AsyncMock(return_value=api),
        ),
        patch("custom_components.edc_sharing.report.EdcReportManager.async_start"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        coordinator = entry.runtime_data.coordinator
        assert coordinator.last_update_success
        assert coordinator.has_available_history
        assert coordinator.data.latest_day == date(2026, 10, 12)
        assert set(coordinator._history_days) == {date(2026, 10, 12)}
        registry = er.async_get(hass)
        from custom_components.edc_sharing.sensor import SENSORS, TARGET_SENSORS

        for description in SENSORS:
            entity_id = registry.async_get_entity_id(
                "sensor", "edc_sharing", f"1_{description.key}"
            )
            state = hass.states.get(entity_id)
            assert state is not None and state.state not in ("unavailable", "unknown")
        for description in TARGET_SENSORS:
            entity_id = registry.async_get_entity_id(
                "sensor", "edc_sharing", f"1_target_target_{description.key}"
            )
            state = hass.states.get(entity_id)
            assert state is not None and state.state not in ("unavailable", "unknown")
        group_id = registry.async_get_entity_id("sensor", "edc_sharing", "1_shared_today")
        assert float(hass.states.get(group_id).state) == 10
        assert hass.states.get(group_id).attributes["data_date"] == "2026-10-12"
        assert coordinator.data_quality["missing_measurement_days"] == (
            1 if pending_day != "omitted" else 0
        )
    await hass.config_entries.async_unload(entry.entry_id)


async def test_empty_history_does_not_create_zero_energy(hass, recorder_mock):
    from decimal import Decimal
    from types import SimpleNamespace

    from custom_components.edc_sharing.calculation import calculate_statistics
    from custom_components.edc_sharing.sensor import SENSORS, EdcSharingSensor

    entry, api = make_entry(hass), make_api(hass)
    coordinator = EdcSharingCoordinator(hass, entry, api)
    coordinator.data = calculate_statistics((), Decimal(2), date(2026, 10, 14))
    entry.runtime_data = SimpleNamespace(coordinator=coordinator)
    for description in SENSORS:
        entity = EdcSharingSensor(entry, description)
        assert entity.available == (description.key == "sale_price")
    await coordinator.async_shutdown()


async def test_bad_credentials_keep_history_without_repeating_password(
    hass, recorder_mock
):
    entry, api = make_entry(hass), make_api(hass)
    await cache_history(hass, entry)
    api._request_once.side_effect = EdcAuthenticationError(
        "Neplatné jméno nebo heslo EDC."
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
        patch.object(entry, "async_start_reauth_if_available") as reauth,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        coordinator = entry.runtime_data.coordinator
        reauth.assert_called_once()
        assert coordinator.has_available_history
        assert not coordinator.last_update_success
        assert coordinator.update_interval is None
        registry = er.async_get(hass)
        group_id = registry.async_get_entity_id(
            "sensor", "edc_sharing", "1_shared_today"
        )
        assert float(hass.states.get(group_id).state) == 10
        await coordinator.async_refresh()
        assert api._request_once.await_count == 1
        assert not coordinator._history_import_enabled
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


@pytest.mark.parametrize("marker", (None, "NaN", "Infinity"))
async def test_all_null_historical_day_cannot_advance_cursor(hass, recorder_mock, marker):
    entry, api = make_entry(hass), make_api(hass)
    raw = profile()
    raw["content"] = [{"date": "2026-10-12", "values": [marker] * 4}]
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


async def test_new_complete_day_imports_despite_nonfinite_neighbour_and_keeps_history(
    hass, recorder_mock, caplog
):
    """Regrese v0.2.5: HTTP 200 s NaN nesmí pohřbít nový platný den.

    Síť je nahrazena na hranici požadavku, nikoli validátor nebo koordinátor.
    Dřívější den zůstává uložený, nový obsahuje 96 čtvrthodin a Recorder musí
    mít skutečně 24 hodin pro skupinu i cíl. Další den není falešná nula.
    """
    await hass.config.async_set_time_zone("Europe/Prague")
    entry, api = make_entry(hass), make_api(hass)
    await cache_history(hass, entry)
    registry = er.async_get(hass)
    original = registry.async_get_or_create(
        "sensor", "edc_sharing", "1_shared_today", config_entry=entry,
        suggested_object_id="unchanged_original_sharing",
    )

    async def read(_method, _path, payload):
        raw = profile()
        raw["content"] = []
        if payload["dateFrom"] <= "2026-10-12" <= payload["dateTo"]:
            for day, bad in (("2026-10-12", True), ("2026-10-13", False), ("2026-10-14", True)):
                for slot in range(96):
                    hour, minute = divmod(slot * 15, 60)
                    end_hour, end_minute = divmod((slot + 1) * 15, 60)
                    raw["content"].append({
                        "date": day,
                        "start": f"{hour:02d}:{minute:02d}:00",
                        "end": f"{end_hour:02d}:{end_minute:02d}:00",
                        "values": [1, 0, "NaN" if bad else -2.5, -1.5],
                    })
        return raw

    api._request_once.side_effect = read
    with (
        patch("custom_components.edc_sharing.async_setup", new=AsyncMock(return_value=True)),
        patch("custom_components.edc_sharing.async_get_api_client", new=AsyncMock(return_value=api)),
        patch("custom_components.edc_sharing.report.EdcReportManager.async_start"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await recorder_mock.async_block_till_done()
        coordinator = entry.runtime_data.coordinator
        assert coordinator.last_update_success
        assert not coordinator.cached_startup
        assert coordinator.data.latest_day == date(2026, 10, 13)
        assert set(coordinator._history_days) == {date(2026, 10, 12), date(2026, 10, 13)}
        assert float(coordinator._history_days[date(2026, 10, 12)].shared) == 10
        assert float(coordinator.data.latest.shared) == 96
        assert float(hass.states.get(original.entity_id).state) == 96
        assert coordinator.data_quality["missing_measurement_intervals"] == 192
        assert not api.account_state.blocks
        assert "nekonečnou" not in caplog.text
        health = await inspect_statistics_health(hass, entry, date(2026, 10, 13), date(2026, 10, 14))
        assert len(health["statistics"]) == 8
        assert all(item["points"] == 24 for item in health["statistics"].values())
        # Opakované čtení nepřidává kopii stejné hodiny ani nezmění IDs.
        await coordinator.async_refresh()
        await recorder_mock.async_block_till_done()
        repeated = await inspect_statistics_health(hass, entry, date(2026, 10, 13), date(2026, 10, 14))
        assert all(item["points"] == 24 for item in repeated["statistics"].values())
        assert registry.async_get_entity_id("sensor", "edc_sharing", "1_shared_today") == original.entity_id
    await hass.config_entries.async_unload(entry.entry_id)
