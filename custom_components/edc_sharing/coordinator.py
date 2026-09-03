"""Data coordinator for EDC sharing."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from decimal import Decimal
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
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
    one_calendar_year_ago,
    parse_daily_profile,
    parse_hourly_profile,
    profile_date_ranges,
    profile_date_ranges_backwards,
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

_HISTORY_STORE_VERSION = 1
_BACKFILL_REQUEST_DELAY = 0.25


def _stored_date(value: object) -> date | None:
    """Parse a stored ISO date without failing integration setup."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _stored_datetime(value: object) -> datetime | None:
    """Parse a stored ISO timestamp without failing integration setup."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _stored_non_negative_int(value: object) -> int:
    """Return a safe non-negative counter loaded from storage."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


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
        self.history_backfill_status = "not_started"
        self.history_backfill_started_at: datetime | None = None
        self.history_backfill_completed_at: datetime | None = None
        self.history_backfill_scan_start: date | None = None
        self.history_backfill_cursor: date | None = None
        self.history_earliest_date: date | None = None
        self.history_backfill_processed_chunks = 0
        self.history_backfill_total_chunks = 0
        self.history_backfill_imported_days = 0
        self.history_backfill_imported_hours = 0
        self.history_backfill_error: str | None = None
        self._history_backfill_task: asyncio.Task[None] | None = None
        self._history_store: Store[dict[str, Any]] = Store(
            hass,
            _HISTORY_STORE_VERSION,
            (
                f"{DOMAIN}.history_backfill.{entry.entry_id}."
                f"{entry.data[CONF_SSE_ID]}"
            ),
        )

    async def async_initialize(self) -> None:
        """Restore persisted history-backfill progress."""
        stored = await self._history_store.async_load()
        if not isinstance(stored, dict):
            return
        stored_status = str(stored.get("status") or "not_started")
        self.history_backfill_status = (
            stored_status
            if stored_status
            in {"not_started", "running", "paused", "failed", "completed"}
            else "not_started"
        )
        self.history_backfill_started_at = _stored_datetime(stored.get("started_at"))
        self.history_backfill_completed_at = _stored_datetime(
            stored.get("completed_at")
        )
        self.history_backfill_scan_start = _stored_date(stored.get("scan_start"))
        self.history_backfill_cursor = _stored_date(stored.get("cursor"))
        self.history_earliest_date = _stored_date(stored.get("earliest_date"))
        self.history_backfill_processed_chunks = _stored_non_negative_int(
            stored.get("processed_chunks")
        )
        self.history_backfill_total_chunks = _stored_non_negative_int(
            stored.get("total_chunks")
        )
        self.history_backfill_imported_days = _stored_non_negative_int(
            stored.get("imported_days")
        )
        self.history_backfill_imported_hours = _stored_non_negative_int(
            stored.get("imported_hours")
        )
        error = stored.get("error")
        self.history_backfill_error = str(error) if error else None

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
    def async_start_history_backfill(self, *, resume_only: bool = False) -> bool:
        """Start or resume a background scan of all possible EDC history."""
        if (
            self._history_backfill_task is not None
            and not self._history_backfill_task.done()
        ):
            return False

        can_resume = (
            self.history_backfill_status in {"running", "paused", "failed"}
            and self.history_backfill_cursor is not None
        )
        if resume_only and not can_resume:
            return False

        now = dt_util.now()
        if not can_resume:
            scan_end = two_calendar_month_start(now.date())
            self.history_backfill_scan_start = one_calendar_year_ago(now.date())
            ranges = profile_date_ranges_backwards(
                self.history_backfill_scan_start,
                scan_end,
            )
            self.history_backfill_cursor = scan_end
            self.history_backfill_started_at = now
            self.history_backfill_completed_at = None
            self.history_earliest_date = min(self._days) if self._days else None
            self.history_backfill_processed_chunks = 0
            self.history_backfill_total_chunks = len(ranges)
            self.history_backfill_imported_days = 0
            self.history_backfill_imported_hours = 0
        else:
            scan_start = self.history_backfill_scan_start or one_calendar_year_ago(
                now.date()
            )
            self.history_backfill_scan_start = scan_start
            remaining = len(
                profile_date_ranges_backwards(
                    scan_start,
                    self.history_backfill_cursor,
                )
            )
            self.history_backfill_total_chunks = max(
                self.history_backfill_total_chunks,
                self.history_backfill_processed_chunks + remaining,
            )

        self.history_backfill_status = "running"
        self.history_backfill_error = None
        self.async_update_listeners()
        task = self.config_entry.async_create_background_task(
            self.hass,
            self._async_backfill_history(),
            f"{DOMAIN} history backfill {self.config_entry.entry_id}",
        )
        self._history_backfill_task = task
        task.add_done_callback(self._history_backfill_done)
        return True

    @callback
    def _history_backfill_done(self, task: asyncio.Task[None]) -> None:
        """Release the completed task reference."""
        if self._history_backfill_task is task:
            self._history_backfill_task = None

    async def _async_backfill_history(self) -> None:
        """Scan backwards and import every available EDC history block."""
        try:
            await self._async_save_history_backfill_state()
            cursor = self.history_backfill_cursor
            scan_start = self.history_backfill_scan_start
            if scan_start is None:
                scan_start = one_calendar_year_ago(dt_util.now().date())
                self.history_backfill_scan_start = scan_start
            if cursor is None or cursor <= scan_start:
                await self._async_finish_history_backfill()
                return

            ranges = profile_date_ranges_backwards(
                scan_start,
                cursor,
            )
            local_tz = dt_util.now().tzinfo
            price = Decimal(
                str(
                    self.config_entry.options.get(
                        CONF_SALE_PRICE,
                        self.config_entry.data.get(
                            CONF_SALE_PRICE, DEFAULT_SALE_PRICE
                        ),
                    )
                )
            )
            for chunk_from, chunk_to in ranges:
                local_from = datetime.combine(chunk_from, time.min, tzinfo=local_tz)
                local_to = datetime.combine(chunk_to, time.min, tzinfo=local_tz)
                raw = await self.api.async_get_daily_profile(
                    int(self.config_entry.data[CONF_SSE_ID]),
                    dt_util.as_utc(local_from).isoformat().replace("+00:00", "Z"),
                    dt_util.as_utc(local_to).isoformat().replace("+00:00", "Z"),
                )
                days = tuple(
                    row
                    for row in parse_daily_profile(raw)
                    if chunk_from <= row.day < chunk_to
                )
                hours = tuple(
                    row
                    for row in parse_hourly_profile(raw)
                    if chunk_from <= row.start.date() < chunk_to
                )
                now = dt_util.now()
                self.history_backfill_imported_days += async_import_daily_history(
                    self.hass,
                    sse_id=int(self.config_entry.data[CONF_SSE_ID]),
                    sse_name=str(self.config_entry.data[CONF_SSE_NAME]),
                    days=days,
                    sale_price=price,
                    today=now.date(),
                    local_tz=local_tz,
                )
                self.history_backfill_imported_hours += async_import_hourly_history(
                    self.hass,
                    sse_id=int(self.config_entry.data[CONF_SSE_ID]),
                    sse_name=str(self.config_entry.data[CONF_SSE_NAME]),
                    hours=hours,
                    sale_price=price,
                    now=now,
                    local_tz=local_tz,
                )
                if days:
                    earliest = min(row.day for row in days)
                    if (
                        self.history_earliest_date is None
                        or earliest < self.history_earliest_date
                    ):
                        self.history_earliest_date = earliest
                self.history_backfill_cursor = chunk_from
                self.history_backfill_processed_chunks += 1
                await self._async_save_history_backfill_state()
                self.async_update_listeners()
                await asyncio.sleep(_BACKFILL_REQUEST_DELAY)

            await self._async_finish_history_backfill()
        except asyncio.CancelledError:
            self.history_backfill_status = "paused"
            await self._async_save_history_backfill_state()
            self.async_update_listeners()
            raise
        except EdcAuthenticationError:
            await self._async_fail_history_backfill(
                "Přihlášení k EDC již není platné."
            )
        except (EdcApiError, HomeAssistantError, ValueError, KeyError) as err:
            await self._async_fail_history_backfill(str(err))
        except Exception as err:  # noqa: BLE001
            await self._async_fail_history_backfill(
                f"Neočekávaná chyba při doplňování historie: {err}"
            )

    async def _async_finish_history_backfill(self) -> None:
        """Persist successful completion and notify diagnostic entities."""
        self.history_backfill_status = "completed"
        self.history_backfill_cursor = self.history_backfill_scan_start
        self.history_backfill_processed_chunks = self.history_backfill_total_chunks
        self.history_backfill_completed_at = dt_util.now()
        self.history_backfill_error = None
        await self._async_save_history_backfill_state()
        self.async_update_listeners()

    async def _async_fail_history_backfill(self, error: str) -> None:
        """Persist a recoverable backfill failure."""
        self.history_backfill_status = "failed"
        self.history_backfill_error = error
        await self._async_save_history_backfill_state()
        self.async_update_listeners()
        _LOGGER.warning("Could not backfill all EDC history: %s", error)

    async def _async_save_history_backfill_state(self) -> None:
        """Persist progress so an interrupted scan can resume."""
        await self._history_store.async_save(
            {
                "status": self.history_backfill_status,
                "started_at": self.history_backfill_started_at.isoformat()
                if self.history_backfill_started_at is not None
                else None,
                "completed_at": self.history_backfill_completed_at.isoformat()
                if self.history_backfill_completed_at is not None
                else None,
                "scan_start": self.history_backfill_scan_start.isoformat()
                if self.history_backfill_scan_start is not None
                else None,
                "cursor": self.history_backfill_cursor.isoformat()
                if self.history_backfill_cursor is not None
                else None,
                "earliest_date": self.history_earliest_date.isoformat()
                if self.history_earliest_date is not None
                else None,
                "processed_chunks": self.history_backfill_processed_chunks,
                "total_chunks": self.history_backfill_total_chunks,
                "imported_days": self.history_backfill_imported_days,
                "imported_hours": self.history_backfill_imported_hours,
                "error": self.history_backfill_error,
            }
        )

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
