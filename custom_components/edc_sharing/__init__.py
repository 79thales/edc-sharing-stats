"""EDC electricity sharing integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.typing import ConfigType

from .api import EdcApiClient
from .connection import async_get_api_client
from .const import CONF_SSE_ID, DOMAIN, config_entry_unique_id
from .coordinator import EdcSharingCoordinator
from .report import EdcReportManager

PLATFORMS = (Platform.SENSOR, Platform.BUTTON)
_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class EdcRuntimeData:
    """Runtime data attached to the config entry."""

    api: EdcApiClient
    coordinator: EdcSharingCoordinator
    reporter: EdcReportManager


type EdcConfigEntry = ConfigEntry[EdcRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the optional dashboard generator without contacting EDC."""
    from .billing_api import async_setup_billing
    from .dashboard_api import async_setup_dashboard_generator
    from .health import async_register_health_commands

    async_register_health_commands(hass)

    try:
        await async_setup_dashboard_generator(hass)
    except (HomeAssistantError, OSError, ValueError, RuntimeError):
        # A presentation feature must not prevent existing data/report setup.
        _LOGGER.warning(
            "The optional EDC dashboard generator is unavailable; EDC data setup remains enabled"
        )
    try:
        await async_setup_billing(hass)
    except (HomeAssistantError, OSError, ValueError, RuntimeError):
        _LOGGER.warning(
            "The optional EDC billing panel is unavailable; EDC data and reports remain enabled"
        )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Make config entries unique per account and sharing group."""
    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry,
            unique_id=config_entry_unique_id(
                entry.data[CONF_USERNAME], entry.data[CONF_SSE_ID]
            ),
            version=2,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EdcConfigEntry) -> bool:
    """Spustit instanci; diagnostiku zpřístupnit ještě před prvním čtením.

    Neúspěšný start není důvod chybu ztratit. Interní odkazy se nikdy přímo
    neexportují; diagnostics.py z nich vrací whitelist bez config/options.
    Existující validní historie dovolí pouze nouzový diagnostický start.
    Automatické vedlejší účinky povolit až po skutečně úspěšném čtení.
    """
    startup = hass.data.setdefault(DOMAIN, {}).setdefault("startup_diagnostics", {})
    startup[entry.entry_id] = {}
    api = await async_get_api_client(
        hass,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = EdcSharingCoordinator(hass, entry, api)
    startup[entry.entry_id] = {"api": api, "coordinator": coordinator}
    await coordinator.async_initialize()
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        if not coordinator.async_restore_startup_cache():
            raise
    reporter = EdcReportManager(hass, entry, coordinator)
    await reporter.async_initialize_profiles()
    entry.runtime_data = EdcRuntimeData(api, coordinator, reporter)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    automatic_started = False

    @callback
    def async_start_after_verified_read() -> None:
        """Jednou spustit import/backfill/reporty; cache sama není potvrzení.

        Listener i plánovače se ruší standardním unloadem HA. Při souběhu
        aktualizací chrání duplicitu lokální příznak; žádný další časovač ani
        přihlášení zde nevzniká. Obnova nezpůsobí okamžité odeslání e-mailu.
        """
        nonlocal automatic_started
        if automatic_started or not coordinator.last_update_success or coordinator.cached_startup:
            return
        automatic_started = True
        coordinator.async_enable_history_import()
        coordinator.async_start_history_backfill(resume_only=True)
        reporter.async_start()

    entry.async_on_unload(coordinator.async_add_listener(async_start_after_verified_read))
    async_start_after_verified_read()
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EdcConfigEntry) -> bool:
    """Unload the integration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: EdcConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
