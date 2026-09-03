"""Data coordinator for EDC sharing."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EdcApiClient, EdcApiError, EdcAuthenticationError
from .calculation import (
    DailySharing,
    EanInfo,
    HourlySharing,
    SharingStatistics,
    calculate_statistics,
    extract_eans,
    parse_daily_profile,
    parse_hourly_profile,
    profile_date_ranges,
    two_calendar_month_start,
)
from .const import (
    CONF_SALE_PRICE,
    CONF_SSE_ID,
    CONF_SSE_NAME,
    DEFAULT_SALE_PRICE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .history import async_import_daily_history, async_import_hourly_history

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
        self.eans: tuple[EanInfo, ...] = ()
        self._days: dict[date, DailySharing] = {}
        self._hours: dict[datetime, HourlySharing] = {}
        self._history_refresh_date: date | None = None
        self._history_import_enabled = False
        self._history_import_signature: tuple[object, ...] | None = None
        self.last_attempt_at: datetime | None = None
        self.last_success_at: datetime | None = None
        self.next_attempt_at: datetime | None = None
        self.last_attempt_result = "never"
        self.last_attempt_error: str | None = None

    async def _async_update_data(self) -> SharingStatistics:
        now = dt_util.now()
        self.last_attempt_at = now
        self.next_attempt_at = None
        self.last_attempt_result = "running"
        self.last_attempt_error = None
        today = now.date()
        full_history_refresh = self._history_refresh_date != today
        date_from = (
            two_calendar_month_start(today)
            if full_history_refresh
            else today.replace(day=1)
        )
        date_to = today + timedelta(days=1)
        try:
            fetched: dict[date, DailySharing] = {}
            fetched_hours: dict[datetime, HourlySharing] = {}
            fetched_eans: set[EanInfo] = set()
            for chunk_from, chunk_to in profile_date_ranges(date_from, date_to):
                local_from = datetime.combine(chunk_from, time.min, tzinfo=now.tzinfo)
                local_to = datetime.combine(chunk_to, time.min, tzinfo=now.tzinfo)
                raw = await self.api.async_get_daily_profile(
                    int(self.config_entry.data[CONF_SSE_ID]),
                    dt_util.as_utc(local_from).isoformat().replace("+00:00", "Z"),
                    dt_util.as_utc(local_to).isoformat().replace("+00:00", "Z"),
                )
                fetched.update(
                    {
                        row.day: row
                        for row in parse_daily_profile(raw)
                        if date_from <= row.day < date_to
                    }
                )
                fetched_hours.update(
                    {
                        row.start: row
                        for row in parse_hourly_profile(raw)
                        if date_from <= row.start.date() < date_to
                    }
                )
                fetched_eans.update(extract_eans(raw))

            if full_history_refresh:
                self._days = {
                    day: row for day, row in self._days.items() if day >= date_from
                }
                self._hours = {
                    start: row
                    for start, row in self._hours.items()
                    if start.date() >= date_from
                }
                self._history_refresh_date = today
            self._days.update(fetched)
            self._hours.update(fetched_hours)
            if fetched_eans:
                self.eans = tuple(
                    sorted(fetched_eans, key=lambda item: (item.role, item.ean))
                )
            price = Decimal(str(self.config_entry.options.get(
                CONF_SALE_PRICE,
                self.config_entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE),
            )))
            result = calculate_statistics(tuple(self._days.values()), price, today)
            if self._history_import_enabled:
                self._async_import_history_if_changed(
                    result, tuple(self._hours.values()), now
                )
            completed_at = dt_util.now()
            self.last_success_at = completed_at
            self.next_attempt_at = completed_at + DEFAULT_SCAN_INTERVAL
            self.last_attempt_result = "success"
            return result
        except EdcAuthenticationError as err:
            self.last_attempt_result = "authentication_failed"
            self.last_attempt_error = "Přihlášení k EDC již není platné."
            self.next_attempt_at = None
            raise ConfigEntryAuthFailed from err
        except (EdcApiError, ValueError, KeyError) as err:
            self.last_attempt_result = "failed"
            self.last_attempt_error = str(err)
            self.next_attempt_at = dt_util.now() + DEFAULT_SCAN_INTERVAL
            raise UpdateFailed(str(err)) from err

    @callback
    def async_enable_history_import(self) -> None:
        """Enable imports after platforms have registered their entities."""
        self._history_import_enabled = True
        self._async_import_history_if_changed(
            self.data, tuple(self._hours.values()), dt_util.now()
        )

    def _async_import_history_if_changed(
        self,
        statistics: SharingStatistics,
        hours: tuple[HourlySharing, ...],
        now: datetime,
    ) -> None:
        finalized = tuple(row for row in statistics.days if row.day < now.date())
        current_hour = now.replace(tzinfo=None, minute=0, second=0, microsecond=0)
        finalized_hours = tuple(
            sorted(
                (row for row in hours if row.start < current_hour),
                key=lambda row: row.start,
            )
        )
        signature: tuple[object, ...] = (
            *finalized,
            *finalized_hours,
            statistics.sale_price,
        )
        if signature == self._history_import_signature:
            return
        try:
            imported_days = async_import_daily_history(
                self.hass,
                sse_id=int(self.config_entry.data[CONF_SSE_ID]),
                sse_name=str(self.config_entry.data[CONF_SSE_NAME]),
                days=statistics.days,
                sale_price=statistics.sale_price,
                today=now.date(),
                local_tz=now.tzinfo,
            )
            imported_hours = async_import_hourly_history(
                self.hass,
                sse_id=int(self.config_entry.data[CONF_SSE_ID]),
                sse_name=str(self.config_entry.data[CONF_SSE_NAME]),
                hours=hours,
                sale_price=statistics.sale_price,
                now=now,
                local_tz=now.tzinfo,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Could not import EDC history: %s", err)
            return
        self._history_import_signature = signature
        if imported_days:
            _LOGGER.debug(
                "Queued %s finalized EDC days for long-term statistics",
                imported_days,
            )
        if imported_hours:
            _LOGGER.debug(
                "Queued %s finalized EDC hours for long-term statistics",
                imported_hours,
            )
