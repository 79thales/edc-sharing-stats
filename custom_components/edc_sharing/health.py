"""Administrátorská čtecí kontrola cache a skutečných hodinových statistik."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time, timedelta

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    async_list_statistic_ids,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import CONF_SSE_ID, DOMAIN
from .energy import target_hourly_statistic_id


async def inspect_statistics_health(
    hass: HomeAssistant, entry, start: date, end: date
) -> dict:
    """Číst nejvýše 31 místních dnů pro vlastní skupinu a známé cíle.

    Vstupy jsou [od, do), čtení Recorderu běží v jeho executor poolu. Počty
    potvrzují uložené body, nikoli jen zařazení do fronty. Akce neposílá EDC
    požadavky a neukládá změny. Výsledek s ID je určen pouze správci HA.
    """
    if (
        type(start) is not date
        or type(end) is not date
        or not 1 <= (end - start).days <= 31
    ):
        raise ValueError("Kontrola vyžaduje 1 až 31 kalendářních dnů.")
    coordinator = entry.runtime_data.coordinator
    sse_id = entry.data[CONF_SSE_ID]
    metrics = ("shared", "consumption", "grid", "coverage")
    identifiers = {f"{DOMAIN}:{sse_id}_{metric}_hourly" for metric in metrics}
    targets = {item.ean for item in coordinator.eans if item.role == "target"}
    if len(targets) > 100:
        raise ValueError("Čtecí kontrola má limit 100 cílových míst.")
    identifiers.update(
        target_hourly_statistic_id(sse_id, ean, metric)
        for ean in targets
        for metric in metrics
    )
    local_tz = dt_util.get_default_time_zone()
    start_time = datetime.combine(start, time.min, tzinfo=local_tz).astimezone(UTC)
    end_time = datetime.combine(end, time.min, tzinfo=local_tz).astimezone(UTC)
    async with asyncio.timeout(30):
        metadata = {
            item["statistic_id"]: item
            for item in await async_list_statistic_ids(hass, identifiers)
        }
        points = await get_instance(hass).async_add_executor_job(
            statistics_during_period,
            hass,
            start_time,
            end_time,
            identifiers,
            "hour",
            None,
            {"mean"},
        )
    result = {}
    for identifier in sorted(identifiers):
        rows = [
            row for row in points.get(identifier, []) if row.get("mean") is not None
        ]
        meta = metadata.get(identifier)
        result[identifier] = {
            "status": "missing_statistic"
            if meta is None
            else "available"
            if rows
            else "empty_period",
            "points": len(rows),
            "unit": meta.get("unit_of_measurement") if meta else None,
            "first": datetime.fromtimestamp(rows[0]["start"], UTC).isoformat()
            if rows
            else None,
            "last": datetime.fromtimestamp(rows[-1]["start"], UTC).isoformat()
            if rows
            else None,
        }
    return {
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "timezone": str(local_tz),
        "quality": coordinator.data_quality,
        "last_attempt_result": coordinator.last_attempt_result,
        "statistics": result,
    }


def async_register_health_commands(hass: HomeAssistant) -> None:
    """Přidat pouze admin-only čtecí příkaz; používá existující autentizaci HA."""
    websocket_api.async_register_command(hass, websocket_statistics_health)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        "type": "edc_sharing/statistics/health",
        vol.Required("entry_id"): str,
        vol.Optional("date_from"): str,
        vol.Optional("date_to"): str,
    }
)
@websocket_api.async_response
async def websocket_statistics_health(hass, connection, msg) -> None:
    """Chyba/stará data/timeout nejsou úspěch; chybová větev nevrací soukromý obsah."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if (
        entry is None
        or entry.domain != DOMAIN
        or getattr(entry, "runtime_data", None) is None
    ):
        connection.send_error(
            msg["id"], "entry_not_ready", "EDC instance není připravena."
        )
        return
    try:
        latest = getattr(entry.runtime_data.coordinator.data, "latest_day", None)
        start = (
            date.fromisoformat(msg["date_from"])
            if "date_from" in msg
            else (latest or dt_util.now().date() - timedelta(days=1))
        )
        end = (
            date.fromisoformat(msg["date_to"])
            if "date_to" in msg
            else start + timedelta(days=1)
        )
        result = await inspect_statistics_health(hass, entry, start, end)
    except (ValueError, OverflowError):
        connection.send_error(
            msg["id"], "invalid_range", "Zadejte platné období do 31 dnů."
        )
    except TimeoutError:
        connection.send_error(
            msg["id"], "recorder_timeout", "Čtení statistiky překročilo 30 sekund."
        )
    except (HomeAssistantError, KeyError, RuntimeError):
        connection.send_error(
            msg["id"], "recorder_unavailable", "Čtecí kontrola Recorderu není dostupná."
        )
    else:
        connection.send_result(msg["id"], result)
