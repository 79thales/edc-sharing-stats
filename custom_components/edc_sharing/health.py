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

from .api import EdcApiError
from .calculation import parse_hourly_profile, profile_resolution
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
            # API seznamu používá statistics_unit_of_measurement, nikoli
            # interní SQL metadata unit_of_measurement. Mean níže je v této
            # uložené jednotce; uživatelská zobrazovací jednotka se může lišit.
            "unit": meta.get("statistics_unit_of_measurement") if meta else None,
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
        "checks": {
            "authentication": "not_probed",
            "groups": "not_probed",
            "profile": "cached_only",
            "parser": coordinator.data_quality.get("resolution", "unknown"),
            "import": "queue_count_only",
            "recorder": "read_completed",
        },
    }


async def inspect_connection_health(entry, start: date) -> dict:
    """Výslovná čtecí kontrola skupin a jediného dne bez importu nebo změny cache.

    Používá runtime API a jeho společné limity. Nepotvrzuje, že je zaplaceno,
    nezapisuje žádné hodnoty ani neodesílá e-mail. Stupně nejsou zaměnitelné:
    platné přihlášení může fungovat a profil přesto chybět. Zrušení zachováváme.
    """
    api = entry.runtime_data.api
    result = {
        "authentication": "not_probed",
        "groups": "not_probed",
        "profile": "not_probed",
        "parser": "not_probed",
        "profile_day": start.isoformat(),
    }
    try:
        async with asyncio.timeout(120):
            groups = await api.async_get_groups()
            result.update(authentication="verified_by_read", groups="read_completed")
            if not any(
                item.get("sseId") == int(entry.data[CONF_SSE_ID]) for item in groups
            ):
                result["groups"] = "configured_group_not_listed"
                result["status"] = "inconclusive"
                return result
            raw = await api.async_get_daily_profile(
                int(entry.data[CONF_SSE_ID]), start, start + timedelta(days=1)
            )
            result["profile"] = "read_completed"
            resolution = profile_resolution(raw)
            hours = parse_hourly_profile(raw, local_tz=dt_util.get_default_time_zone())
            result.update(
                parser=resolution,
                complete_hours=sum(row.complete for row in hours),
                incomplete_hours=sum(not row.complete for row in hours),
            )
    except EdcApiError as error:
        result.update(
            status="unavailable",
            failure_category=error.category,
            http_status=error.status,
            retry_at=error.retry_at.isoformat() if error.retry_at else None,
        )
    except ValueError:
        result.update(status="inconclusive", failure_category="contract")
    except TimeoutError:
        result.update(status="unavailable", failure_category="timeout")
    else:
        result["status"] = "ok" if resolution != "empty" else "inconclusive"
    return result


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
        vol.Optional("fresh", default=False): bool,
    }
)
@websocket_api.async_response
async def websocket_statistics_health(hass, connection, msg) -> None:
    """Chyba/stará data/timeout nejsou úspěch; chybová větev nevrací soukromý obsah."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(
            msg["id"], "entry_not_ready", "EDC instance není připravena."
        )
        return
    if getattr(entry, "runtime_data", None) is None:
        from .diagnostics import async_get_config_entry_diagnostics

        # Správce musí dostat zachovaný důvod i při setup_retry. Fresh není
        # oprávnění obejít start nebo uložený zákaz; zde se neposílá žádné HTTP.
        connection.send_result(
            msg["id"],
            {
                "ready": False,
                "status": "entry_not_ready",
                "diagnostics": await async_get_config_entry_diagnostics(hass, entry),
                "connection_probe": {"status": "not_probed"},
            },
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
        if msg.get("fresh", False):
            result["connection_probe"] = await inspect_connection_health(entry, start)
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
