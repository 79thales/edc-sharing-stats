"""Skutečný Recorder: zápis, čtení přes stejné API jako graf a oprava bodů."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_test_home_assistant,
)

from custom_components.edc_sharing.calculation import (
    EanInfo,
    parse_hourly_profile,
    parse_hourly_target_profiles,
)
from custom_components.edc_sharing.health import (
    async_register_health_commands,
    inspect_statistics_health,
)
from custom_components.edc_sharing.history import (
    async_import_hourly_history,
    async_import_target_hourly_history,
)


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
    now = datetime(2026, 10, 14, tzinfo=UTC)
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
            "statistic_ids": ["edc_sharing:1_target_shared_hourly"],
            "types": ["mean"],
        }
    )
    response = await client.receive_json()
    assert response["success"]
    assert response["result"]["edc_sharing:1_target_shared_hourly"][0]["mean"] == 4
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
        {"id": 1, "type": "edc_sharing/statistics/health", "entry_id": entry.entry_id}
    )
    response = await client.receive_json()
    assert not response["success"]


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


@pytest.mark.parametrize("persistent_database", [True])
async def test_statistics_survive_real_recorder_restart(
    async_test_recorder, hass, freezer
):
    """P0: zavřít skutečný Recorder a načíst stejnou databázi v nové instanci HA."""
    freezer.move_to("2026-10-14T12:00:00Z")
    async with async_test_recorder(hass) as instance:
        queue(hass, profile())
        await instance.async_block_till_done()
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
