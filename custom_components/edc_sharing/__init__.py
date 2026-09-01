"""EDC electricity sharing integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EdcApiClient
from .coordinator import EdcSharingCoordinator


@dataclass(slots=True)
class EdcRuntimeData:
    """Runtime data attached to the config entry."""

    api: EdcApiClient
    coordinator: EdcSharingCoordinator


type EdcConfigEntry = ConfigEntry[EdcRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: EdcConfigEntry) -> bool:
    """Set up EDC sharing from a config entry."""
    api = EdcApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = EdcSharingCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = EdcRuntimeData(api, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EdcConfigEntry) -> bool:
    """Unload the integration."""
    return await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])


async def _async_reload_entry(hass: HomeAssistant, entry: EdcConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
