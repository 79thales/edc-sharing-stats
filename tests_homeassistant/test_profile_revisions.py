"""Regrese #10 se skutečným Store a Recorderem, pouze HTTP EDC je syntetické.

Částky vybraných dnů odpovídají příkladům issue; čtvrthodinové rozdělení
je vytvořené pro test a nepředstavuje zachycenou odpověď živého účtu.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.util import dt as dt_util

from custom_components.edc_sharing.api_policy import EdcApiError
from custom_components.edc_sharing.calculation import (
    parse_daily_profile,
    parse_daily_target_profiles,
    parse_hourly_profile,
    parse_hourly_target_profiles,
)
from custom_components.edc_sharing.coordinator import EdcSharingCoordinator
from custom_components.edc_sharing.energy import (
    energy_statistic_id,
    target_hourly_statistic_id,
)
from tests_homeassistant.test_startup_diagnostics import make_entry

pytestmark = pytest.mark.freeze_time("2026-10-18T12:00:00Z")


@pytest.fixture(autouse=True)
def revision_delay(monkeypatch):
    """Zmrazený čas nesmí zablokovat produkční prodlevu mezi požadavky."""
    monkeypatch.setattr("custom_components.edc_sharing.coordinator._BACKFILL_REQUEST_DELAY", 0)


def full_day(day: str, shared: str, quality="Z46"):
    """Úplných 96 slotů, dva cíle v poměru 40/60 %, kWh bez zaokrouhlení."""
    total, used = Decimal(shared), Decimal(0)
    content = []
    for slot in range(96):
        value = total / 96 if slot < 95 else total - used
        used += value
        first, second = value * Decimal("0.4"), value * Decimal("0.6")
        start_hour, start_minute = divmod(slot * 15, 60)
        end_hour, end_minute = divmod((slot + 1) * 15, 60)
        # IN spotřeba a OUT síť jsou na portálu záporné; rozdíl je sdílení.
        values = [value * 2, 0, -first - 1, -1, -second - 1, -1]
        content.append({"date": day, "start": f"{start_hour:02d}:{start_minute:02d}",
                        "end": f"{end_hour:02d}:{end_minute:02d}",
                        "values": [{"v": str(value), "q": quality} for value in values]})
    return {"valueColumns": [
        {"ean": ean, "type": role, "dir": direction}
        for ean, role in (("producer", "D"), ("target-a", "O"), ("target-b", "O"))
        for direction in ("IN", "OUT")], "content": content}


def merged(*profiles):
    return profiles[0] | {"content": [row for profile in profiles for row in profile["content"]]}


def seed(coordinator, raw):
    """Legacy cache je kompletní, ale záměrně ještě nemá provenienci CURRENT."""
    coordinator._history_days.update({row.day: row for row in parse_daily_profile(raw)})
    for row in parse_daily_target_profiles(raw):
        coordinator._history_target_days.setdefault(row.ean, {})[row.day] = row
    tz = dt_util.get_default_time_zone()
    coordinator._hours.update({row.start: row for row in parse_hourly_profile(raw, local_tz=tz) if row.complete})
    for row in parse_hourly_target_profiles(raw, local_tz=tz):
        if row.complete:
            coordinator._target_hours.setdefault(row.ean, {})[row.start] = row
    coordinator.data = coordinator._calculate_statistics(Decimal(2), dt_util.now().date())


async def recorder_points(hass, start, end, identifiers):
    """Číst uložené body přes stejný Recorder API kontrakt jako grafy."""
    await get_instance(hass).async_block_till_done()
    tz = dt_util.get_default_time_zone()
    return await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass,
        datetime.combine(start, time.min, tzinfo=tz).astimezone(UTC),
        datetime.combine(end, time.min, tzinfo=tz).astimezone(UTC),
        identifiers, "hour", None, {"mean", "sum"})


async def test_complete_legacy_days_are_replaced_in_cache_recorder_and_cumulative_energy(
    hass, recorder_mock, hass_storage,
):
    """Dva úplné DAILY dny nejsou mezery: opravit je i všechny navazující sumy."""
    await hass.config.async_set_time_zone("Europe/Prague")
    entry = make_entry(hass)
    hass.config_entries.async_update_entry(entry, options={"energy_targets": ["target-a", "target-b"]})
    old = merged(full_day("2026-09-05", "7.28", "Z66"), full_day("2026-09-13", "0.56", "Z99"))
    current = merged(full_day("2026-09-05", "4.39"), full_day("2026-09-13", "0.14"))
    api = SimpleNamespace(async_get_daily_profile=AsyncMock(return_value=current))
    coordinator = EdcSharingCoordinator(hass, entry, api)
    seed(coordinator, old)
    seed(coordinator, full_day("2026-10-01", "2"))
    coordinator._async_import_energy_history(dt_util.now())
    coordinator._async_import_history_if_changed(coordinator.data, tuple(coordinator._hours.values()), dt_util.now())
    before = await recorder_points(hass, date(2026, 9, 1), date(2026, 10, 1), {"edc_sharing:1_shared_hourly"})
    assert sum(row["mean"] for row in before["edc_sharing:1_shared_hourly"]) == pytest.approx(7.84)
    await coordinator._async_save_history_backfill_state()
    # Simulace aktualizace/restartu: skutečný HA Store obnoví staré úplné dny.
    restored = EdcSharingCoordinator(hass, entry, api)
    await restored.async_initialize()
    assert date(2026, 9, 5) in restored.profile_revision_pending_days
    assert restored._history_backfill_gaps == {}
    await restored._async_refresh_profile_revisions()
    assert restored._history_days[date(2026, 9, 5)].shared == pytest.approx(Decimal("4.39"))
    assert date(2026, 9, 5) not in restored.profile_revision_pending_days
    assert restored._profile_revision_due_months() == []
    api.async_get_daily_profile.assert_awaited_once_with(1, date(2026, 9, 1), date(2026, 10, 1))
    daily = "edc_sharing:1_shared_daily"
    group = "edc_sharing:1_shared_hourly"
    target = target_hourly_statistic_id(1, "target-a", "shared")
    energy = energy_statistic_id(1, ("target-a", "target-b"), "shared")
    points = await recorder_points(hass, date(2026, 9, 1), date(2026, 10, 2), {daily, group, target, energy})
    assert points[daily][0]["mean"] == pytest.approx(4.39)
    assert len(points[group]) == len(points[target]) == 72
    assert sum(row["mean"] for row in points[group]) == pytest.approx(6.53)
    assert sum(row["mean"] for row in points[target]) == pytest.approx(6.53 * 0.4)
    assert points[energy][-1]["sum"] == pytest.approx(6.53)
    # Druhý zápis nahradí stejné časové body, nepřičte kWh ani body.
    await restored._async_refresh_profile_month(date(2026, 9, 1))
    again = await recorder_points(hass, date(2026, 9, 1), date(2026, 10, 2), {group, target, energy})
    assert len(again[group]) == 72
    assert again[energy][-1]["sum"] == pytest.approx(6.53)
    assert hass_storage[restored._history_store.key]["data"]["current_profile"]["selection"] == "CURRENT"
    restart = EdcSharingCoordinator(hass, entry, api)
    await restart.async_initialize()
    assert restart._profile_revision_due_months() == []
    for instance in (coordinator, restored, restart):
        await instance.async_shutdown()


@pytest.mark.parametrize("failure", ["empty", "null", "one_sided", "daily_only"])
async def test_unusable_revision_preserves_old_values_and_stays_pending(
    hass, recorder_mock, failure,
):
    """HTTP 200, prázdno ani den bez hodinového profilu nejsou dokončená oprava."""
    entry = make_entry(hass)
    old = full_day("2026-08-05", "7.28")
    raw = full_day("2026-08-05", "4.39")
    if failure == "empty":
        raw["content"] = []
    elif failure == "null":
        raw["content"][0]["values"][2]["v"] = None
    elif failure == "one_sided":
        raw["valueColumns"] = raw["valueColumns"][:2]
        for row in raw["content"]:
            row["values"] = row["values"][:2]
    else:
        raw["content"] = [{"date": "2026-08-05", "values": [8.78, 0, -5.756, -4, -6.634, -4]}]
    coordinator = EdcSharingCoordinator(hass, entry, SimpleNamespace(async_get_daily_profile=AsyncMock(return_value=raw)))
    seed(coordinator, old)
    before = deepcopy(coordinator._history_days)
    await coordinator._async_refresh_profile_revisions()
    assert coordinator._history_days == before
    assert date(2026, 8, 5) in coordinator.profile_revision_pending_days
    # Neúplný měsíc se znovu nezkouší při každé hodinové aktualizaci téhož dne.
    assert coordinator._profile_revision_due_months() == []
    await coordinator.async_shutdown()


async def test_restart_resumes_cancelled_month_and_concurrent_start_is_rejected(
    hass, recorder_mock,
):
    entry = make_entry(hass)
    entered, release = asyncio.Event(), asyncio.Event()

    async def fetch(*args):
        entered.set()
        await release.wait()
        return full_day("2026-08-05", "4.39")

    api = SimpleNamespace(async_get_daily_profile=AsyncMock(side_effect=fetch))
    coordinator = EdcSharingCoordinator(hass, entry, api)
    seed(coordinator, full_day("2026-08-05", "7.28"))
    coordinator._history_import_enabled = True
    assert coordinator.async_start_profile_revisions()
    await entered.wait()
    assert not coordinator.async_start_profile_revisions()
    task = coordinator._profile_revision_task
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    restored = EdcSharingCoordinator(hass, entry, api)
    await restored.async_initialize()
    assert restored._profile_revision_due_months() == [date(2026, 8, 1)]
    release.set()
    await restored._async_refresh_profile_revisions()
    assert restored._history_days[date(2026, 8, 5)].shared == pytest.approx(Decimal("4.39"))
    await coordinator.async_shutdown()
    await restored.async_shutdown()


async def test_later_corrections_are_rechecked_and_server_failure_stops_queue(
    hass, recorder_mock,
):
    entry = make_entry(hass)
    api = SimpleNamespace(async_get_daily_profile=AsyncMock(side_effect=EdcApiError("synthetic")))
    coordinator = EdcSharingCoordinator(hass, entry, api)
    seed(coordinator, merged(full_day("2026-08-05", "7.28"), full_day("2026-07-05", "1")))
    for day in coordinator._history_days:
        coordinator._current_profile_days[day] = "2026-10-01T12:00:00+00:00"
        coordinator._profile_revision_checks[day.replace(day=1)] = date(2026, 10, 1)
    await coordinator._async_refresh_profile_revisions()
    assert api.async_get_daily_profile.await_count == 1
    assert coordinator._history_days[date(2026, 8, 5)].shared == pytest.approx(Decimal("7.28"))
    await coordinator.async_shutdown()


async def test_failed_recorder_queue_is_persisted_and_retried_even_after_current_cache(
    hass, recorder_mock, monkeypatch,
):
    """CURRENT provenience není úspěšný import: selhání fronty nezmizí po restartu."""
    from homeassistant.exceptions import HomeAssistantError
    entry = make_entry(hass)
    api = SimpleNamespace(async_get_daily_profile=AsyncMock(return_value=full_day("2026-08-05", "4.39")))
    coordinator = EdcSharingCoordinator(hass, entry, api)
    seed(coordinator, full_day("2026-08-05", "7.28"))
    with monkeypatch.context() as patcher:
        def fail(*args, **kwargs):
            raise HomeAssistantError("synthetic queue rejection")
        patcher.setattr("custom_components.edc_sharing.coordinator.async_import_daily_history", fail)
        await coordinator._async_refresh_profile_revisions()
    assert date(2026, 8, 1) in coordinator._profile_revision_pending_imports
    restored = EdcSharingCoordinator(hass, entry, api)
    await restored.async_initialize()
    assert date(2026, 8, 1) in restored._profile_revision_pending_imports
    await restored._async_refresh_profile_month(date(2026, 8, 1))
    assert not restored._profile_revision_pending_imports
    await coordinator.async_shutdown()
    await restored.async_shutdown()


async def test_target_only_legacy_month_is_not_omitted_from_reconciliation(hass, recorder_mock):
    """Ani samostatná cílová cache se nesmí ztratit z fronty uzavřených měsíců."""
    entry = make_entry(hass)
    api = SimpleNamespace(async_get_daily_profile=AsyncMock(return_value=full_day("2026-08-05", "4.39")))
    coordinator = EdcSharingCoordinator(hass, entry, api)
    seed(coordinator, full_day("2026-08-05", "7.28"))
    coordinator._history_days.clear()
    assert coordinator._profile_revision_due_months() == [date(2026, 8, 1)]
    await coordinator._async_refresh_profile_revisions()
    assert coordinator._history_days[date(2026, 8, 5)].shared == pytest.approx(Decimal("4.39"))
    assert not coordinator.profile_revision_pending_days
    await coordinator.async_shutdown()
