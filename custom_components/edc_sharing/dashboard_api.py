"""Admin-only, read-only dashboard generation over the existing HA connection."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration
from homeassistant.util.yaml import dump

from .const import CONF_SSE_ID, CONF_SSE_NAME, DOMAIN
from .dashboard import (
    GROUP_KEYS,
    PANEL_PATH,
    TARGET_KEYS,
    DashboardTarget,
    build_dashboard,
)
from .ean_settings import ean_location, ean_name

MODULE_PATH = "/edc_sharing/dashboard-generator.js"
PANEL_ELEMENT = "edc-sharing-dashboard-generator-v1"
_LOGGER = logging.getLogger(__name__)


async def async_setup_dashboard_generator(hass: HomeAssistant) -> None:
    """Register one hidden configuration panel for all EDC config entries."""
    from homeassistant.components.frontend import async_panel_exists
    from homeassistant.components.http import StaticPathConfig
    from homeassistant.components.panel_custom import async_register_panel

    async_register_dashboard_commands(hass)
    if async_panel_exists(hass, PANEL_PATH):
        _LOGGER.warning("EDC dashboard generator URL is already in use; the existing panel was not changed")
        return
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths([
        StaticPathConfig(MODULE_PATH, str(Path(__file__).parent / "frontend/dashboard-generator.js"), False)
    ])
    await async_register_panel(
        hass, frontend_url_path=PANEL_PATH, webcomponent_name=PANEL_ELEMENT,
        module_url=f"{MODULE_PATH}?v={integration.manifest['version']}", require_admin=True,
        config_panel_domain=DOMAIN,
    )


def async_register_dashboard_commands(hass: HomeAssistant) -> None:
    """No custom write endpoint: the frontend uses HA's own Lovelace API."""
    websocket_api.async_register_command(hass, websocket_dashboard_groups)
    websocket_api.async_register_command(hass, websocket_dashboard_preview)


def _registered_sources(hass: HomeAssistant, entry: ConfigEntry) -> tuple[dict, dict, list]:
    """Resolve the current entity IDs, including user renames, without guessing."""
    group_id = str(entry.data[CONF_SSE_ID])
    registered = {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if item.platform == DOMAIN and item.disabled_by is None
    }
    entities = {key: registered[f"{group_id}_{key}"] for key in GROUP_KEYS
                if f"{group_id}_{key}" in registered}
    buttons = {key: registered[f"{group_id}_{key}"] for key in ("refresh_data", "backfill_history")
               if f"{group_id}_{key}" in registered}
    target_pattern = re.compile(rf"^{re.escape(group_id)}_target_(.+)_({'|'.join(TARGET_KEYS)})$")
    target_sensors: dict[str, dict[str, str]] = {}
    for unique_id, entity_id in registered.items():
        if match := target_pattern.fullmatch(unique_id):
            target_sensors.setdefault(match[1], {})[match[2]] = entity_id
    targets = []
    for ean, sensors in sorted(target_sensors.items()):
        name = ean_name(ean, entry.options)
        if name == ean:
            name = f"EAN …{ean[-4:]}"
        if location := ean_location(ean, entry.options):
            name += f" — {location}"
        targets.append(DashboardTarget(name, sensors))
    return entities, buttons, targets


@websocket_api.require_admin
@websocket_api.websocket_command({"type": "edc_sharing/dashboard/groups"})
@websocket_api.async_response
async def websocket_dashboard_groups(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any],
) -> None:
    """Expose names and IDs only, never credentials, bank accounts or reports."""
    connection.send_result(msg["id"], [
        {"entry_id": entry.entry_id, "name": str(entry.data.get(CONF_SSE_NAME) or entry.title)}
        for entry in hass.config_entries.async_entries(DOMAIN)
    ])


@websocket_api.require_admin
@websocket_api.websocket_command({
    "type": "edc_sharing/dashboard/preview",
    vol.Required("entry_id"): str,
    vol.Required("title"): vol.All(str, vol.Length(min=1, max=120)),
    vol.Required("url_path"): vol.All(str, vol.Length(min=3, max=80)),
    vol.Optional("language", default="cs"): vol.In(("cs", "en")),
    vol.Optional("include_targets", default=True): bool,
    vol.Optional("include_details", default=True): bool,
    vol.Optional("include_energy", default=False): bool,
})
@websocket_api.async_response
async def websocket_dashboard_preview(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any],
) -> None:
    """Generate on demand; do not contact EDC, send reports or persist options."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "entry_not_found", "EDC config entry not found")
        return
    entities, buttons, targets = _registered_sources(hass, entry)
    statistics: dict[str, str] = {}
    for metric, key in (("shared", "shared_today"), ("consumption", "consumption_today"),
                        ("grid", "grid_today"), ("unused", "unused_today"),
                        ("coverage", "coverage_today"), ("revenue", "revenue_today")):
        state = hass.states.get(entities.get(key, ""))
        if state is None:
            continue
        for period in ("daily", "hourly"):
            statistic_id = state.attributes.get(f"{period}_statistic_id")
            if isinstance(statistic_id, str) and statistic_id.startswith(f"{DOMAIN}:"):
                statistics[f"{metric}_{period}"] = statistic_id
    try:
        config = build_dashboard(
            title=msg["title"], url_path=msg["url_path"], entities=entities,
            statistics=statistics, buttons=buttons, language=msg["language"],
            targets=targets if msg["include_targets"] else (),
            include_details=msg["include_details"], include_energy=msg["include_energy"],
        )
    except ValueError as err:
        connection.send_error(msg["id"], str(err), "Invalid dashboard name or URL path")
        return
    yaml = await hass.async_add_executor_job(dump, config)
    connection.send_result(msg["id"], {
        "config": config, "yaml": yaml,
        "missing_entities": [key for key in GROUP_KEYS if key not in entities],
        "target_count": len(targets) if msg["include_targets"] else 0,
    })
