"""Data coordinator for EDC sharing."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EdcApiClient, EdcApiError, EdcAuthenticationError
from .calculation import SharingStatistics, calculate_profile
from .const import CONF_SALE_PRICE, CONF_SSE_ID, DEFAULT_SALE_PRICE, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class EdcSharingCoordinator(DataUpdateCoordinator[SharingStatistics]):
    """Fetch and calculate EDC statistics."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: EdcApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.api = api

    async def _async_update_data(self) -> SharingStatistics:
        now = dt_util.now()
        local_from = datetime.combine(now.date().replace(day=1), time.min, tzinfo=now.tzinfo)
        local_to = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=now.tzinfo)
        try:
            raw = await self.api.async_get_daily_profile(
                int(self.config_entry.data[CONF_SSE_ID]),
                dt_util.as_utc(local_from).isoformat().replace("+00:00", "Z"),
                dt_util.as_utc(local_to).isoformat().replace("+00:00", "Z"),
            )
            price = Decimal(str(self.config_entry.options.get(
                CONF_SALE_PRICE,
                self.config_entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE),
            )))
            return calculate_profile(raw, price, now.date())
        except EdcAuthenticationError as err:
            raise ConfigEntryAuthFailed from err
        except (EdcApiError, ValueError, KeyError) as err:
            raise UpdateFailed(str(err)) from err
