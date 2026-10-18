"""Data coordinator for EDC sharing."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, tzinfo
from decimal import Decimal, InvalidOperation
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EdcApiClient, EdcApiError, EdcAuthenticationError
from .calculation import (
    DailySharing,
    EanInfo,
    HourlySharing,
    IncompleteProfileLayoutError,
    SharingStatistics,
    TargetDailySharing,
    TargetHourlySharing,
    calculate_statistics,
    extract_eans,
    history_profile_gaps,
    missing_measurement_counts,
    one_calendar_year_ago,
    parse_daily_profile,
    parse_daily_target_profiles,
    parse_hourly_profile,
    parse_hourly_target_profiles,
    profile_date_ranges,
    profile_date_ranges_backwards,
    profile_resolution,
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
from .ean_settings import ean_name, target_sale_price
from .energy import energy_targets
from .history import (
    async_import_daily_history,
    async_import_energy_history,
    async_import_hourly_history,
    async_import_target_hourly_history,
)
from .profile_selection import profile_as_of, profile_quality, profile_read_snapshot

_LOGGER = logging.getLogger(__name__)

_HISTORY_STORE_VERSION = 1
_BACKFILL_REQUEST_DELAY = 0.25
_HISTORY_GAP_REASONS = {
    "missing_measurements", "missing_day", "incomplete_day", "unverified_validity",
}


def _history_gap_ranges(gaps: dict[date, str]) -> list[dict[str, str]]:
    """Sloučit sousední neověřené dny stejného důvodu do rozsahů [od, do).

    Rozsahy používá Store i diagnostika. Neobsahují EANy ani naměřené kWh;
    jejich existence znamená nevyřešené pokrytí, nikoli nulovou energii.
    """
    result: list[dict[str, str]] = []
    for day, reason in sorted(gaps.items()):
        end = (day + timedelta(days=1)).isoformat()
        if result and result[-1]["end"] == day.isoformat() and result[-1]["reason"] == reason:
            result[-1]["end"] = end
        else:
            result.append({"start": day.isoformat(), "end": end, "reason": reason})
    return result


def _stored_history_gaps(value: object) -> dict[date, str]:
    """Obnovit přídavnou evidenci mezer; starší Store bez pole je kompatibilní.

    Jeden rozsah může mít nejvýše 366 kalendářních dnů ročního backfillu.
    Poškozené datum či neznámý důvod neinterpretovat jako měření/platnost.
    """
    result: dict[date, str] = {}
    if value is None:
        return result
    if not isinstance(value, list):
        raise TypeError("Uložená evidence mezer historie je neplatná.")
    for item in value:
        if not isinstance(item, dict):
            raise TypeError("Uložená evidence mezer historie je neplatná.")
        start, end = _stored_date(item.get("start")), _stored_date(item.get("end"))
        reason = item.get("reason")
        if (start is None or end is None or not isinstance(reason, str)
                or reason not in _HISTORY_GAP_REASONS or not 0 < (end - start).days <= 366):
            raise ValueError("Uložená evidence mezer historie je neplatná.")
        for offset in range((end - start).days):
            result[start + timedelta(days=offset)] = reason
    return result


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


_DAILY_DECIMAL_FIELDS = (
    "consumption",
    "grid_purchase",
    "shared",
    "producer_overflow",
    "used_overflow",
    "unused_overflow",
    "coverage",
    "consistency_difference",
)

_TARGET_DAILY_DECIMAL_FIELDS = (
    "consumption",
    "grid_purchase",
    "shared",
    "coverage",
)


def _serialize_daily_row(row: DailySharing) -> dict[str, str]:
    """Serialize one aggregate without losing Decimal precision."""
    return {
        "day": row.day.isoformat(),
        **{field: str(getattr(row, field)) for field in _DAILY_DECIMAL_FIELDS},
    }


def _stored_daily_rows(value: object) -> dict[date, DailySharing]:
    """Restore valid cached daily aggregates and ignore malformed entries."""
    if not isinstance(value, list):
        return {}
    restored: dict[date, DailySharing] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        day = _stored_date(item.get("day"))
        if day is None:
            continue
        try:
            values = {
                field: Decimal(str(item[field])) for field in _DAILY_DECIMAL_FIELDS
            }
        except (InvalidOperation, KeyError, TypeError, ValueError):
            continue
        if not all(number.is_finite() for number in values.values()):
            continue
        restored[day] = DailySharing(day=day, **values)
    return restored


def _serialize_target_daily_row(row: TargetDailySharing) -> dict[str, str]:
    """Serialize one target EAN aggregate without losing Decimal precision."""
    return {
        "ean": row.ean,
        "day": row.day.isoformat(),
        **{
            field: str(getattr(row, field))
            for field in _TARGET_DAILY_DECIMAL_FIELDS
        },
    }


def _stored_target_daily_rows(
    value: object,
) -> dict[str, dict[date, TargetDailySharing]]:
    """Restore safe per-target daily cache entries from storage."""
    if not isinstance(value, list):
        return {}
    restored: dict[str, dict[date, TargetDailySharing]] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        ean = item.get("ean")
        day = _stored_date(item.get("day"))
        if (
            not isinstance(ean, str)
            or not ean.strip()
            or len(ean) > 32
            or day is None
        ):
            continue
        ean = ean.strip()
        try:
            values = {
                field: Decimal(str(item[field]))
                for field in _TARGET_DAILY_DECIMAL_FIELDS
            }
        except (InvalidOperation, KeyError, TypeError, ValueError):
            continue
        if not all(number.is_finite() for number in values.values()):
            continue
        row = TargetDailySharing(ean=ean, day=day, **values)
        restored.setdefault(ean, {})[day] = row
    return restored


def _hour_start_utc(value: datetime, local_tz: tzinfo) -> datetime:
    """Return an hourly profile timestamp as an aware UTC datetime."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=local_tz)
    return dt_util.as_utc(value)


def _hour_local_date(value: datetime, local_tz: tzinfo) -> date:
    """Return the local calendar date represented by an hourly timestamp."""
    return _hour_start_utc(value, local_tz).astimezone(local_tz).date()


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
        # Jediný zámek celé transakce čtení/výpočtu/zápisu brání tomu, aby
        # pomalejší odpověď backfillu přepsala novější revizi běžné obnovy.
        # Account lock klienta nadále samostatně řídí HTTP limity účtu.
        self._profile_read_lock = asyncio.Lock()
        self._profile_revision_task: asyncio.Task[None] | None = None
        self._current_profile_days: dict[date, str] = {}
        self._profile_revision_checks: dict[date, date] = {}
        self._profile_revision_attempts: dict[date, date] = {}
        self._profile_revision_pending_imports: set[date] = set()
        self.eans: tuple[EanInfo, ...] = ()
        self._days: dict[date, DailySharing] = {}
        self._history_days: dict[date, DailySharing] = {}
        self._target_days: dict[str, dict[date, TargetDailySharing]] = {}
        self._history_target_days: dict[str, dict[date, TargetDailySharing]] = {}
        self._hours: dict[datetime, HourlySharing] = {}
        self._target_hours: dict[str, dict[datetime, TargetHourlySharing]] = {}
        self._history_refresh_date: date | None = None
        self._history_import_enabled = False
        self._history_import_signature: tuple[object, ...] | None = None
        self._energy_import_signature: tuple[object, ...] | None = None
        self.last_attempt_at: datetime | None = None
        self.last_success_at: datetime | None = None
        self.next_attempt_at: datetime | None = None
        self.last_attempt_result = "never"
        self.last_attempt_error: str | None = None
        self.cached_startup = False
        self._awaiting_reauth = False
        self.data_quality: dict[str, Any] = {"resolution": "unknown", "incomplete_days": 0,
                                           "incomplete_hours": 0, "queued_hours": 0}
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
        # Kurzor vyjadřuje prohledání, mezery neověřené pokrytí. Sady klíčů
        # deduplikují počítadla i částečné hodiny při opakování po restartu.
        self._history_backfill_gaps: dict[date, str] = {}
        self._history_backfill_day_keys: set[date] = set()
        self._history_backfill_hour_keys: set[datetime] = set()
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
            in {"not_started", "running", "paused", "failed", "completed", "completed_with_gaps"}
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
        try:
            self._history_backfill_gaps = _stored_history_gaps(stored.get("pending_ranges"))
        except (TypeError, ValueError) as err:
            # Poškozená evidence nesmí vést k falešnému čistému dokončení.
            # Platnou denní cache níže přesto obnovíme; nový průchod vyžádá
            # znovu celý uchovaný vyhledávací rozsah.
            self.history_backfill_status = "failed"
            self.history_backfill_error = str(err)
            self.history_backfill_cursor = _stored_date(stored.get("scan_end")) or (
                two_calendar_month_start(self.history_backfill_started_at.date())
                if self.history_backfill_started_at else None
            )
            self.history_backfill_processed_chunks = 0
        self._history_backfill_day_keys = {
            day for value in stored.get("imported_day_keys", [])
            if (day := _stored_date(value)) is not None
        }
        self._history_backfill_hour_keys = {
            dt_util.as_utc(hour) for value in stored.get("imported_hour_keys", [])
            if (hour := _stored_datetime(value)) is not None and hour.tzinfo is not None
        }
        self._history_days = _stored_daily_rows(stored.get("daily_rows"))
        self._history_target_days = _stored_target_daily_rows(
            stored.get("target_daily_rows")
        )
        # Starý Store nemá provenienci: jeho hodnoty zachováme, ale kompletní
        # dny musíme znovu přečíst v CURRENT. Chybějící pole není důkaz opravy.
        revision = stored.get("current_profile", {})
        if isinstance(revision, dict) and revision.get("selection") == "CURRENT":
            queued = revision.get("pending_imports", [])
            if isinstance(queued, list):
                self._profile_revision_pending_imports = {
                    month for key in queued if (month := _stored_date(key)) is not None and month.day == 1}
            stamps = revision.get("days", {})
            if isinstance(stamps, dict):
                self._current_profile_days = {
                    day: stamp for key, stamp in stamps.items()
                    if (day := _stored_date(key)) in self._history_days
                    and (instant := _stored_datetime(stamp)) is not None
                    and instant.tzinfo is not None
                }
            for field, destination in (("checks", self._profile_revision_checks),
                                       ("attempts", self._profile_revision_attempts)):
                values = revision.get(field, {})
                if isinstance(values, dict):
                    for key, value in values.items():
                        month, checked = _stored_date(key), _stored_date(value)
                        if month is not None and month.day == 1 and checked is not None and checked <= dt_util.now().date():
                            destination[month] = checked
        # Metadata EAN nejsou živá měření. Po výpadku je obnovit z vlastní
        # cache a ze stávajícího registru stejné config entry, bez vytváření
        # nebo přejmenování entit. Starší soubory výrobní EAN neukládaly.
        known = {EanInfo(ean, "target") for ean in self._history_target_days}
        if isinstance(stored.get("eans"), list):
            for item in stored["eans"]:
                if (isinstance(item, dict) and item.get("role") in ("sharing", "target")
                        and isinstance(item.get("ean"), str) and 0 < len(item["ean"].strip()) <= 32):
                    known.add(EanInfo(item["ean"].strip(), item["role"]))
        registry = er.async_get(self.hass)
        for registered in er.async_entries_for_config_entry(registry, self.config_entry.entry_id):
            if registered.platform != DOMAIN or registered.domain != "sensor":
                continue
            for role in ("sharing", "target"):
                prefix = f"{self.config_entry.data[CONF_SSE_ID]}_{role}_ean_"
                if registered.unique_id.startswith(prefix):
                    ean = registered.unique_id[len(prefix):]
                    if 0 < len(ean.strip()) <= 32:
                        known.add(EanInfo(ean.strip(), role))
        self.eans = tuple(sorted(known, key=lambda item: (item.role, item.ean)))

    @property
    def has_available_history(self) -> bool:
        """Platné historické hodnoty jsou dostupné nezávisle na posledním HTTP.

        Existence objektu se součty nula nestačí: musí obsahovat skutečný
        datový den. Nevyžadovat včerejšek/dnešek, EDC publikuje se zpožděním.
        Tato podmínka nepovoluje síť, importy, platby ani automatické reporty.
        """
        return self.data is not None and self.data.latest_day is not None

    @callback
    def _refresh_retained_statistics(self) -> bool:
        """Přepočítat jen zobrazované kalendářní souhrny z existujících dnů.

        Vstupy jsou validní uložené denní kWh a nakonfigurované ceny CZK/kWh.
        Žádný den se nepřidává, nepřenáší na dnešek a nenahrazuje nulou; datum
        posledního dne i počty pokrytých dnů zůstávají skutečné. Při neplatné
        ceně se starý výsledek nepřepíše. Žádný zápis do Recorderu nebo dokladů.
        """
        if not self._history_days:
            return False
        try:
            price = Decimal(str(self.config_entry.options.get(
                CONF_SALE_PRICE, self.config_entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE))))
            if not price.is_finite() or price < 0:
                return False
        except (InvalidOperation, TypeError, ValueError):
            return False
        self.data = self._calculate_statistics(price, dt_util.now().date())
        return self.has_available_history

    @callback
    def async_restore_startup_cache(self) -> bool:
        """Umožnit start s dostupnými hodnotami existující platné historie.

        Neúspěšné HTTP nepředstírat jako úspěch, ale neodepřít platná data.
        Entity, hodnoty i atributy historie zůstávají dostupné pod stejnými ID.
        Cache je vstup pro paměťový přehled; nic nezapisovat do Recorderu,
        neobnovovat backfill a neposílat plánované reporty. Další síťový pokus
        naplánovat až po uložené lhůtě. Bez cache zůstává běžný setup_retry HA.
        """
        if not self._history_days or self.last_attempt_result not in ("failed", "authentication_failed"):
            return False
        now = dt_util.now()
        if not self._refresh_retained_statistics():
            return False
        self.cached_startup = True
        self.last_update_success = False
        self.data_quality.update(cached_only=True, latest_data_day=self.data.latest_day.isoformat()
                                 if self.data.latest_day else None)
        if self.next_attempt_at is not None:
            self.update_interval = max(timedelta(seconds=1), self.next_attempt_at - now)
        _LOGGER.warning("EDC zobrazuje uchovanou platnou historii; aktuální čtení selhalo a automatické importy/reporty čekají na obnovu")
        return True

    @callback
    def _async_refresh_finished(self) -> None:
        """Při opakované chybě aktualizovat diagnostiku i dostupné atributy.

        Základní koordinátor při dvou selháních za sebou listenery potlačuje.
        Zde dostupnost historie nesmí záviset na výsledku HTTP; chybový stav
        a termín musí být aktuální. Aktivační listener reportů nadále vyžaduje
        last_update_success, takže toto oznámení nic neposílá ani neimportuje.
        """
        if not self.last_update_success:
            self.async_update_listeners()

    def _target_prices(self, default_price: Decimal) -> dict[str, Decimal]:
        """Return safe per-target prices while preserving the group default."""
        return {
            ean: target_sale_price(ean, self.config_entry.options, default_price)
            for ean in self._history_target_days
        }

    def _calculate_statistics(
        self, sale_price: Decimal, today: date
    ) -> SharingStatistics:
        """Calculate group and optional individual-target values from one cache."""
        return calculate_statistics(
            tuple(self._history_days.values()),
            sale_price,
            today,
            target_days={
                ean: tuple(rows.values())
                for ean, rows in self._history_target_days.items()
            },
            target_prices=self._target_prices(sale_price),
        )

    @callback
    def target_days_for_range(
        self, date_from: date, date_to: date
    ) -> dict[str, tuple[TargetDailySharing, ...]]:
        """Return cached target rows for a half-open range without an API call."""
        return {
            ean: tuple(
                row
                for day, row in sorted(rows.items())
                if date_from <= day < date_to
            )
            for ean, rows in self._history_target_days.items()
        }

    async def _async_update_data(self) -> SharingStatistics:
        """Serializovat běžnou obnovu proti opravám revizí a starému backfillu."""
        async with self._profile_read_lock:
            return await self._async_update_profile_data()

    @profile_read_snapshot
    async def _async_update_profile_data(self) -> SharingStatistics:
        if getattr(self, "_awaiting_reauth", False):
            # Potvrzeně odmítnuté heslo neopakovat jen kvůli obnovení karty.
            # Nové credentials používají standardní reauth a nový koordinátor.
            raise ConfigEntryAuthFailed
        now = dt_util.now()
        self.last_attempt_at = now
        self.next_attempt_at = None
        self.last_attempt_result = "running"
        self.last_attempt_error = None
        today = now.date()
        local_tz = now.tzinfo or dt_util.get_default_time_zone()
        full_history_refresh = self._history_refresh_date != today
        date_from = (
            two_calendar_month_start(today)
            if full_history_refresh
            else today.replace(day=1)
        )
        date_to = today + timedelta(days=1)
        try:
            fetched: dict[date, DailySharing] = {}
            fetched_target_days: dict[str, dict[date, TargetDailySharing]] = {}
            fetched_hours: dict[datetime, HourlySharing] = {}
            fetched_target_hours: dict[str, dict[datetime, TargetHourlySharing]] = {}
            fetched_eans: set[EanInfo] = set()
            resolutions: set[str] = set()
            incomplete_days = 0
            incomplete_hours = 0
            incomplete_blocks = 0
            missing_days = 0
            missing_intervals = 0
            profile_failures: list[EdcApiError] = []
            # Nejnovější blok zkusit první: stará lokální chyba schématu
            # nemá zastavit platné současné období. Serverový/account blok
            # se neskáče a dál zastaví celý pokus bez dalšího HTTP volání.
            for chunk_from, chunk_to in reversed(profile_date_ranges(date_from, date_to)):
                # Zachovat kalendářní interval [od, do). API klient převede
                # poslední den na včetně; UTC patří až k hodinovým statistikám.
                try:
                    raw = await self.api.async_get_daily_profile(
                        int(self.config_entry.data[CONF_SSE_ID]), chunk_from, chunk_to)
                except EdcApiError as error:
                    if error.category != "contract" or error.phase != "profile_validation":
                        raise
                    profile_failures.append(error)
                    incomplete_blocks += 1
                    continue
                self.data_quality.update(profile_quality(raw))
                self.data_quality["profile_as_of"] = profile_as_of().isoformat()
                self.data_quality.update(profile_date_from=chunk_from.isoformat(),
                                         profile_date_to_exclusive=chunk_to.isoformat())
                resolutions.add(profile_resolution(raw))
                block_missing_days, block_missing_intervals = missing_measurement_counts(raw)
                missing_days += block_missing_days
                missing_intervals += block_missing_intervals
                try:
                    parsed_days = parse_daily_profile(raw)
                    parsed_hours = parse_hourly_profile(raw, local_tz=local_tz)
                    incomplete_days += sum(not row.complete for row in parsed_days)
                    incomplete_hours += sum(not row.complete for row in parsed_hours)
                    fetched.update(
                        {
                            row.day: row
                            for row in parsed_days
                            if row.complete and date_from <= row.day < date_to
                        }
                    )
                    for row in parse_daily_target_profiles(raw):
                        if row.complete and date_from <= row.day < date_to:
                            fetched_target_days.setdefault(row.ean, {})[row.day] = row
                    fetched_hours.update(
                        {
                            row.start: row
                            for row in parsed_hours
                            if row.complete and date_from
                            <= _hour_local_date(row.start, local_tz)
                            < date_to
                        }
                    )
                    for row in parse_hourly_target_profiles(raw, local_tz=local_tz):
                        if (
                            row.complete and date_from
                            <= _hour_local_date(row.start, local_tz)
                            < date_to
                        ):
                            fetched_target_hours.setdefault(row.ean, {})[row.start] = row
                    fetched_eans.update(extract_eans(raw))
                except IncompleteProfileLayoutError as err:
                    # Before both EAN roles joined the sharing group, EDC can
                    # return a valid profile containing only one side. This
                    # historical block must not prevent the integration from
                    # starting with the complete, more recent data.
                    _LOGGER.debug(
                        "Skipping incomplete EDC coordinator block %s to %s: %s",
                        chunk_from,
                        chunk_to,
                        err,
                    )
                    incomplete_blocks += 1

            if profile_failures and not fetched and not fetched_hours:
                # Samotná stará cache není důkaz obnovy API; aktivuje pouze
                # samostatně popsaný diagnostický start, nikoli import/report.
                raise profile_failures[0]
            if missing_intervals and not fetched and not fetched_hours:
                raise EdcApiError("EDC vrátilo chybějící měřenou hodnotu.", category="unknown", status=200)

            if full_history_refresh:
                self._days = {
                    day: row for day, row in self._days.items() if day >= date_from
                }
                self._hours = {
                    start: row
                    for start, row in self._hours.items()
                    if _hour_local_date(start, local_tz) >= date_from
                }
                self._target_days = {
                    ean: {
                        day: row for day, row in rows.items() if day >= date_from
                    }
                    for ean, rows in self._target_days.items()
                    if any(day >= date_from for day in rows)
                }
                self._target_hours = {
                    ean: {
                        start: row
                        for start, row in rows.items()
                        if _hour_local_date(start, local_tz) >= date_from
                    }
                    for ean, rows in self._target_hours.items()
                    if any(_hour_local_date(start, local_tz) >= date_from for start in rows)
                }
                self._history_refresh_date = today
            self._days.update(fetched)
            self._hours.update(fetched_hours)
            for ean, rows in fetched_target_days.items():
                self._target_days.setdefault(ean, {}).update(rows)
            for ean, rows in fetched_target_hours.items():
                self._target_hours.setdefault(ean, {}).update(rows)
            history_changed = any(
                self._history_days.get(day) != row for day, row in fetched.items()
            )
            history_changed = history_changed or any(
                self._history_target_days.get(ean, {}).get(day) != row
                for ean, rows in fetched_target_days.items()
                for day, row in rows.items()
            )
            self._history_days.update(fetched)
            for ean, rows in fetched_target_days.items():
                self._history_target_days.setdefault(ean, {}).update(rows)
            hourly_days = {_hour_local_date(row.start, local_tz) for row in fetched_hours.values()}
            self._record_current_profile(
                {day: row for day, row in fetched.items() if day in hourly_days}, fetched_target_days)
            if self._history_days:
                earliest_known = min(self._history_days)
                if (
                    self.history_earliest_date is None
                    or earliest_known < self.history_earliest_date
                ):
                    self.history_earliest_date = earliest_known
            eans_changed = False
            if fetched_eans:
                eans_changed = set(self.eans) != fetched_eans
                self.eans = tuple(
                    sorted(fetched_eans, key=lambda item: (item.role, item.ean))
                )
            price = Decimal(str(self.config_entry.options.get(
                CONF_SALE_PRICE,
                self.config_entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE),
            )))
            result = self._calculate_statistics(price, today)
            if self._history_import_enabled:
                self._async_import_energy_history(now)
                self._async_import_history_if_changed(
                    result, tuple(self._hours.values()), now
                )
            completed_at = dt_util.now()
            self.last_success_at = completed_at
            self.next_attempt_at = completed_at + DEFAULT_SCAN_INTERVAL
            self.last_attempt_result = "success"
            self.cached_startup = False
            self.update_interval = DEFAULT_SCAN_INTERVAL
            self.data_quality.pop("failure_category", None)
            self.data_quality.update(
                cached_only=False, missing_measurement_days=missing_days,
                missing_measurement_intervals=missing_intervals,
                resolution=next(iter(resolutions)) if len(resolutions) == 1 else "mixed",
                incomplete_days=incomplete_days, incomplete_hours=incomplete_hours, incomplete_blocks=incomplete_blocks,
                latest_data_day=result.latest_day.isoformat() if result.latest_day else None,
                hourly_reason=("unknown_resolution" if "unknown" in resolutions else
                               "daily_only" if resolutions == {"daily"} else
                               "incomplete" if incomplete_hours or incomplete_blocks or missing_intervals else "available" if fetched_hours else "empty"),
            )
            if history_changed or eans_changed or fetched:
                await self._async_save_history_backfill_state()
            self.async_start_profile_revisions()
            return result
        except EdcAuthenticationError as err:
            self._refresh_retained_statistics()
            self._awaiting_reauth = True
            self.update_interval = None
            self.last_attempt_result = "authentication_failed"
            self.last_attempt_error = "Přihlášení k EDC již není platné."
            self.next_attempt_at = None
            self.data_quality["cached_only"] = True
            raise ConfigEntryAuthFailed from err
        except (EdcApiError, ValueError, KeyError) as err:
            self._refresh_retained_statistics()
            self.last_attempt_result = "failed"
            self.last_attempt_error = str(err)
            self.next_attempt_at = getattr(err, "retry_at", None) or dt_util.now() + DEFAULT_SCAN_INTERVAL
            self.data_quality["failure_category"] = getattr(err, "category", "contract")
            self.data_quality["cached_only"] = True
            state = getattr(self.api, "account_state", None)
            if state is not None and (not isinstance(err, EdcApiError) or err.retry_at is None):
                failure = err if isinstance(err, EdcApiError) else EdcApiError(
                    "EDC profil nelze bezpečně spočítat.", category="contract", phase="profile_validation",
                    status=getattr(self.api, "last_status", None))
                failure.retry_at = self.next_attempt_at
                async with state.lock:
                    await state.note_failure(failure)
                self.api.last_failure_category = failure.category
                self.api.last_status = failure.status
            retry_seconds = max(0, (self.next_attempt_at - dt_util.now()).total_seconds())
            raise UpdateFailed(str(err), retry_after=retry_seconds) from err

    def _profile_cached_days(self) -> set[date]:
        """Sjednotit dny skupiny i cílových EANů, včetně jednostranné staré cache."""
        return set(self._history_days) | {
            day for rows in self._history_target_days.values() for day in rows}

    @property
    def profile_revision_pending_days(self) -> set[date]:
        """Dny původní cache bez potvrzeného úplného CURRENT čtení.

        Nejde o chybějící energii. Množina odděleně brání vydávání starých
        DAILY podkladů za opravené při náhledu vyúčtování.
        """
        return {day for day in self._profile_cached_days() if day not in self._current_profile_days}

    def _record_current_profile(
        self, days: dict[date, DailySharing],
        targets: dict[str, dict[date, TargetDailySharing]], *,
        mark_month_checked: bool = True,
    ) -> None:
        """Označit pouze konzistentní den skupiny i všech známých cílových EANů.

        Vstupy jsou úplné denní kWh ze stejné odpovědi, výstup je UTC čas
        načtení, nikoli příznak konečné kalkulace. Chybějící cíl nebo nesoulad
        nesmí certifikovat starou smíšenou cache. Ceny ani doklady neměníme.
        """
        for day, row in days.items():
            expected = {ean for ean, rows in self._history_target_days.items() if day in rows}
            actual = {ean: rows[day] for ean, rows in targets.items() if day in rows}
            if (not expected <= actual.keys() or not actual
                    or abs(sum((item.shared for item in actual.values()), Decimal(0))
                           - row.shared) > Decimal("0.000001")):
                continue
            self._current_profile_days[day] = profile_as_of().isoformat()
        today = dt_util.now().date()
        pending = self.profile_revision_pending_days
        # Běžná obnova už načítá celý předchozí měsíc. Zbytečný druhý request
        # nevytvářet, pokud byly všechny jeho uchované dny právě ověřené.
        touched = {day.replace(day=1) for day in days}
        for month in touched:
            known = {day for day in self._profile_cached_days() if day.replace(day=1) == month}
            if (mark_month_checked and known and known <= days.keys()
                    and not known & pending and month < today.replace(day=1)):
                self._profile_revision_checks[month] = today

    def _profile_revision_due_months(self) -> list[date]:
        """Opravit legacy měsíce a po sedmi dnech prověřit i pozdější korekce.

        Jeden měsíc se zkusí nejvýše jednou za místní den. Chybějící data
        zůstávají pending i při timeoutu/HTTP chybě; server Retry-After má
        stále přednost. Sedm dní je interval našeho ověřování, ne lhůta EDC.
        """
        today = dt_util.now().date()
        pending = self.profile_revision_pending_days
        months = {day.replace(day=1) for day in self._profile_cached_days()
                  if day < today.replace(day=1)}
        return sorted((month for month in months
                       if self._profile_revision_attempts.get(month) != today
                       and (month in self._profile_revision_pending_imports
                            or any(day.replace(day=1) == month for day in pending)
                            or self._profile_revision_checks.get(month, date.min)
                            <= today - timedelta(days=7))), reverse=True)

    @property
    def profile_revision_diagnostics(self) -> dict:
        """Veřejný stav bez EANů, kWh nebo textu vzdálené chyby."""
        pending = self.profile_revision_pending_days
        today = dt_util.now().date()
        months = {day.replace(day=1) for day in self._profile_cached_days() if day < today.replace(day=1)}
        stale = {month for month in months
                 if self._profile_revision_checks.get(month, date.min) <= today - timedelta(days=7)
                 or month in self._profile_revision_pending_imports
                 or any(day.replace(day=1) == month for day in pending)}
        return {"selection": "CURRENT", "actual_calculation_type": "unknown",
                "pending_months": [month.isoformat() for month in sorted(stale)],
                "last_checked": {month.isoformat(): checked.isoformat()
                                 for month, checked in self._profile_revision_checks.items()},
                "pending_days": len(pending),
                "pending_import_months": [month.isoformat() for month in sorted(self._profile_revision_pending_imports)],
                "running": self._profile_revision_task is not None
                and not self._profile_revision_task.done(),
                "due_months": [month.isoformat() for month in self._profile_revision_due_months()],
                "statistics_write": "queued_not_read_verified"}

    @callback
    def async_start_profile_revisions(self) -> bool:
        """Spustit jednu frontu až po ověřeném připojení a povolení importů.

        Běžná hodinová obnova je spouštěč; nevzniká nový časovač ani účet.
        Entry spravuje background task a jeho zrušení při unloadu. Druhý
        start nic nevytváří; po restartu se stav obnoví ze stejného Store.
        """
        if (not self._history_import_enabled or self.cached_startup or self._awaiting_reauth
                or (self._profile_revision_task is not None and not self._profile_revision_task.done())
                or not self._profile_revision_due_months()):
            return False
        task = self.config_entry.async_create_background_task(
            self.hass, self._async_refresh_profile_revisions(),
            f"{DOMAIN} current profile revisions {self.config_entry.entry_id}")
        self._profile_revision_task = task
        task.add_done_callback(self._profile_revisions_done)
        return True

    @callback
    def _profile_revisions_done(self, task: asyncio.Task[None]) -> None:
        """Uvolnit referenci dokončené či zrušené úlohy."""
        if self._profile_revision_task is task:
            self._profile_revision_task = None

    async def _async_refresh_profile_revisions(self) -> None:
        """Zpracovat snímek fronty, mezi měsíci pustit běžnou aktualizaci.

        Pokus i úspěch ukládáme odděleně. Při zrušení právě rozpracovaného
        měsíce dovolíme pokračování po restartu; dokončené měsíce neopakujeme.
        Neúplný profil nesmaže původní hodnoty a není nahrazen nulou.
        """
        for month in self._profile_revision_due_months():
            try:
                async with self._profile_read_lock:
                    self._profile_revision_attempts[month] = dt_util.now().date()
                    await self._async_save_history_backfill_state()
                    await self._async_refresh_profile_month(month)
            except asyncio.CancelledError:
                self._profile_revision_attempts.pop(month, None)
                await self._async_save_history_backfill_state()
                raise
            except (EdcApiError, ValueError, KeyError, HomeAssistantError, OSError):
                # Chyba účtu/transportu nemá vyvolat další požadavky téže fronty.
                # Podrobnosti již sanitizuje klient; log neobsahuje měření.
                _LOGGER.warning("EDC: obnova aktuálních revizí nedokončena; uložená data zachována")
                return
            await asyncio.sleep(_BACKFILL_REQUEST_DELAY)

    @profile_read_snapshot
    async def _async_refresh_profile_month(self, month: date) -> None:
        """Nahradit konzistentní úplné dny a jejich reálné hodinové profily.

        Jeden požadavek má nejvýše 31 dnů. Po kontrole jednotek, úplnosti
        a shody EANů připravíme celé dny; staré hodinové body téhož dne
        nahradíme, nikoli přičteme. Cumulative Energy se obnoví z celé cache.
        Záznam o opravě ukládáme se stejnými denními podklady. Recorder zápis
        je fronta; skutečný výsledek ověřují funkční testy a health čtení.
        """
        end = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        raw = await self.api.async_get_daily_profile(
            int(self.config_entry.data[CONF_SSE_ID]), month, end)
        tz = dt_util.get_default_time_zone()
        days = {row.day: row for row in parse_daily_profile(raw)
                if row.complete and month <= row.day < end}
        targets: dict[str, dict[date, TargetDailySharing]] = {}
        for row in parse_daily_target_profiles(raw):
            if row.complete:
                targets.setdefault(row.ean, {})[row.day] = row
        hours = tuple(row for row in parse_hourly_profile(raw, local_tz=tz) if row.complete)
        target_hours = tuple(row for row in parse_hourly_target_profiles(raw, local_tz=tz) if row.complete)
        valid = set()
        response_targets = {column["ean"] for column in raw.get("valueColumns", [])
                            if column.get("type") == "O"}
        for day, row in days.items():
            expected = response_targets | {ean for ean, rows in self._history_target_days.items()
                                           if day in rows}
            actual = {ean: rows[day] for ean, rows in targets.items() if day in rows}
            # U legacy měsíců musíme opravit i existující hodinové řady.
            # Denní odpověď nemůže jejich profil rekonstruovat.
            if (expected and expected <= actual.keys()
                    and any(_hour_local_date(hour.start, tz) == day for hour in hours)
                    and abs(sum((item.shared for item in actual.values()), Decimal(0))
                            - row.shared) <= Decimal("0.000001")):
                valid.add(day)
        accepted = {day: row for day, row in days.items() if day in valid}
        accepted_targets = {ean: {day: row for day, row in rows.items() if day in valid}
                            for ean, rows in targets.items()}
        self._history_days.update(accepted)
        self._days.update(accepted)
        for ean, rows in accepted_targets.items():
            self._history_target_days.setdefault(ean, {}).update(rows)
            self._target_days.setdefault(ean, {}).update(rows)
        # Ověřený úplný den je jedinou jednotkou náhrady; neponechat směs
        # jeho starých a nových hodin ani cílových EANů.
        self._hours = {start: row for start, row in self._hours.items()
                       if _hour_local_date(start, tz) not in valid}
        self._hours.update({row.start: row for row in hours if _hour_local_date(row.start, tz) in valid})
        for ean in set(self._target_hours) | set(accepted_targets):
            retained = {start: row for start, row in self._target_hours.get(ean, {}).items()
                        if _hour_local_date(start, tz) not in valid}
            retained.update({row.start: row for row in target_hours
                             if row.ean == ean and _hour_local_date(row.start, tz) in valid})
            self._target_hours[ean] = retained
        self._record_current_profile(accepted, accepted_targets, mark_month_checked=False)
        self.data_quality.update(profile_quality(raw))
        self.data_quality["profile_as_of"] = profile_as_of().isoformat()
        self.data_quality.update(profile_date_from=month.isoformat(),
                                 profile_date_to_exclusive=end.isoformat())
        now = dt_util.now()
        price = Decimal(str(self.config_entry.options.get(
            CONF_SALE_PRICE, self.config_entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE))))
        result = self._calculate_statistics(price, now.date())
        energy_queued = self._async_import_energy_history(now)
        history_queued = self._async_import_history_if_changed(result, tuple(self._hours.values()), now)
        if energy_queued and history_queued:
            self._profile_revision_pending_imports.discard(month)
        else:
            # Platná cache již může obsahovat CURRENT, ale neúspěšné zařazení
            # Recorderu je samostatná trvalá práce, nikoli dokončená oprava.
            self._profile_revision_pending_imports.add(month)
        # Periodická kontrola čeká další týden jen po pokrytí všech dříve
        # uchovaných dnů, nikoli po libovolné HTTP 200 nebo prázdném profilu.
        expected_days = {day for day in self._profile_cached_days() if month <= day < end}
        if expected_days and expected_days <= valid and energy_queued and history_queued:
            self._profile_revision_checks[month] = now.date()
        await self._async_save_history_backfill_state()
        self.async_set_updated_data(result)

    @callback
    def async_start_history_backfill(self, *, resume_only: bool = False) -> bool:
        """Spustit jeden roční průchod nebo ruční opakování uložených mezer.

        Tlačítko po dokončení s mezerami opakuje jen mezery. Automatický
        start po úspěšné obnově API obnovuje pouze přerušený/selhaný běh,
        nikoli terminální varování: restart nesmí opakovaně zatěžovat EDC.
        Souběžný start odmítnout; zrušení uloží paused a zachová další práci.
        """
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
        retry_gaps = self.history_backfill_status == "completed_with_gaps" and bool(
            self._history_backfill_gaps
        )
        if not can_resume and not retry_gaps:
            scan_end = two_calendar_month_start(now.date())
            self.history_backfill_scan_start = one_calendar_year_ago(now.date())
            ranges = profile_date_ranges_backwards(
                self.history_backfill_scan_start,
                scan_end,
            )
            self.history_backfill_cursor = scan_end
            self.history_backfill_started_at = now
            self.history_backfill_completed_at = None
            self.history_earliest_date = (
                min(self._history_days) if self._history_days else None
            )
            self.history_backfill_processed_chunks = 0
            self.history_backfill_total_chunks = len(ranges)
            self.history_backfill_imported_days = 0
            self.history_backfill_imported_hours = 0
            self._history_backfill_gaps.clear()
            self._history_backfill_day_keys.clear()
            self._history_backfill_hour_keys.clear()
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
        self.history_backfill_completed_at = None
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
        """Backfill a běžnou obnovu neprovádět nad stejnou cache současně.

        Zrušení čekající úlohy mění stav stejně jako zrušení běžícího importu.
        Zámek se uvolní také při výjimce; HTTP account policy zůstává aktivní.
        """
        try:
            async with self._profile_read_lock:
                await self._async_backfill_profile_data()
        except asyncio.CancelledError:
            self.history_backfill_status = "paused"
            await self._async_save_history_backfill_state()
            raise

    @profile_read_snapshot
    async def _async_backfill_profile_data(self) -> None:
        """Importovat úplná data, neověřené úseky uchovat a pokračovat zpět.

        Denní hranice zůstávají místní [od, do), hodinové klíče jsou UTC.
        Mezery existující na začátku běhu se zkusí jednou po zbývajícím
        průchodu; nově nalezené čekají na další ruční spuštění. Mezi čteními
        platí stejná prodleva i politika API jako dosud. Chyba transportu,
        přihlášení nebo neznámého schématu zastaví běh bez ztráty další práce.
        """
        try:
            await self._async_save_history_backfill_state()
            cursor = self.history_backfill_cursor
            scan_start = self.history_backfill_scan_start
            if scan_start is None:
                scan_start = one_calendar_year_ago(dt_util.now().date())
                self.history_backfill_scan_start = scan_start
            # Snímek zabrání nekonečnému opakování nově nalezené mezery.
            # Dny pod kurzorem patří zbývajícímu průchodu, nesmějí se číst
            # podruhé. Při opakování po dokončení je kurzor na scan_start.
            pending = _history_gap_ranges({
                day: reason for day, reason in self._history_backfill_gaps.items()
                if cursor is not None and day >= cursor
            })
            ranges = [
                (start, end, True)
                for start, end in profile_date_ranges_backwards(scan_start, cursor)
            ] if cursor is not None and cursor > scan_start else []
            ranges.extend(
                (start, end, False)
                for item in reversed(pending)
                for start, end in profile_date_ranges_backwards(
                    date.fromisoformat(item["start"]), date.fromisoformat(item["end"])
                )
            )
            local_tz = dt_util.now().tzinfo or dt_util.get_default_time_zone()
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
            for chunk_from, chunk_to, scanning in ranges:
                raw = await self.api.async_get_daily_profile(
                    int(self.config_entry.data[CONF_SSE_ID]),
                    chunk_from,
                    chunk_to,
                )
                try:
                    parsed_days = parse_daily_profile(raw)
                    gaps = history_profile_gaps(raw, chunk_from, chunk_to, parsed_days)
                    days = tuple(
                        row
                        for row in parsed_days
                        if row.complete and row.day not in gaps and chunk_from <= row.day < chunk_to
                    )
                    hours = tuple(
                        row
                        for row in parse_hourly_profile(raw, local_tz=local_tz)
                        if row.complete and chunk_from
                        <= _hour_local_date(row.start, local_tz)
                        < chunk_to
                    )
                    target_days = tuple(
                        row
                        for row in parse_daily_target_profiles(raw)
                        if row.complete and row.day not in gaps and chunk_from <= row.day < chunk_to
                    )
                    target_hours = tuple(
                        row
                        for row in parse_hourly_target_profiles(raw, local_tz=local_tz)
                        if row.complete and chunk_from
                        <= _hour_local_date(row.start, local_tz)
                        < chunk_to
                    )
                except IncompleteProfileLayoutError:
                    # Známá jednostranná odpověď je neověřená platnost, nikoli
                    # důkaz počátku sdílení. Neimportovat nuly ani ji nezahodit.
                    days, hours, target_days, target_hours = (), (), (), ()
                    gaps = {
                        chunk_from + timedelta(days=offset): "unverified_validity"
                        for offset in range((chunk_to - chunk_from).days)
                    }
                now = dt_util.now()
                async_import_daily_history(
                    self.hass,
                    sse_id=int(self.config_entry.data[CONF_SSE_ID]),
                    sse_name=str(self.config_entry.data[CONF_SSE_NAME]),
                    days=days,
                    sale_price=price,
                    today=now.date(),
                    local_tz=local_tz,
                )
                async_import_hourly_history(
                    self.hass,
                    sse_id=int(self.config_entry.data[CONF_SSE_ID]),
                    sse_name=str(self.config_entry.data[CONF_SSE_NAME]),
                    hours=hours,
                    sale_price=price,
                    now=now,
                    local_tz=local_tz,
                )
                for ean in {row.ean for row in target_hours}:
                    target_name = ean_name(ean, self.config_entry.options)
                    ean_hours = tuple(row for row in target_hours if row.ean == ean)
                    async_import_target_hourly_history(
                        self.hass,
                        sse_id=self.config_entry.data[CONF_SSE_ID],
                        sse_name=str(self.config_entry.data[CONF_SSE_NAME]),
                        ean=ean,
                        target_name=target_name,
                        hours=ean_hours,
                        now=now,
                        local_tz=local_tz,
                    )
                if days:
                    self._history_days.update({row.day: row for row in days})
                    earliest = min(row.day for row in days)
                    if (
                        self.history_earliest_date is None
                        or earliest < self.history_earliest_date
                    ):
                        self.history_earliest_date = earliest
                for row in target_days:
                    self._history_target_days.setdefault(row.ean, {})[row.day] = row
                self._record_current_profile(
                    {row.day: row for row in days
                     if any(_hour_local_date(hour.start, local_tz) == row.day for hour in hours)},
                    {ean: {row.day: row for row in target_days if row.ean == ean}
                     for ean in {row.ean for row in target_days}},
                )
                self.data_quality.update(profile_quality(raw))
                self.data_quality["profile_as_of"] = profile_as_of().isoformat()
                self.data_quality.update(profile_date_from=chunk_from.isoformat(),
                                         profile_date_to_exclusive=chunk_to.isoformat())
                if self._history_import_enabled:
                    self._async_import_energy_history(now)
                # Import nahrazuje stejné časové body. Počítadla počítají
                # jedinečné zařazené dny/hodiny tohoto průchodu, i po restartu;
                # historická počítadla starého Store ponecháváme jako základ.
                day_keys = {row.day for row in days if row.day < now.date()}
                hour_keys = {
                    _hour_start_utc(row.start, local_tz) for row in hours
                    if _hour_start_utc(row.start, local_tz) < dt_util.as_utc(
                        now.replace(minute=0, second=0, microsecond=0)
                    )
                }
                self.history_backfill_imported_days += len(day_keys - self._history_backfill_day_keys)
                self.history_backfill_imported_hours += len(hour_keys - self._history_backfill_hour_keys)
                self._history_backfill_day_keys.update(day_keys)
                self._history_backfill_hour_keys.update(hour_keys)
                self._history_backfill_gaps = {
                    day: reason for day, reason in self._history_backfill_gaps.items()
                    if not chunk_from <= day < chunk_to
                } | gaps
                if scanning:
                    self.history_backfill_cursor = chunk_from
                    self.history_backfill_processed_chunks += 1
                # Kurzor, mezery, klíče i cache patří do jednoho Store zápisu.
                await self._async_save_history_backfill_state()
                self.async_set_updated_data(self._calculate_statistics(price, now.date()))
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
        """Ukončit prohledání; úplný import deklarovat jen bez uložených mezer."""
        self.history_backfill_status = (
            "completed_with_gaps" if self._history_backfill_gaps else "completed"
        )
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
        """Uložit pokrytí i kurzor společně; přídavná pole zachovají Store v1.

        Klíče UTC zabraňují zdvojení počítadel při opakování částečných dnů.
        Nejstarší agregace zůstává skutečný nalezený den, nikoli platnost SSE.
        """
        await self._history_store.async_save(
            {
                "current_profile": {
                    "selection": "CURRENT",
                    "pending_imports": [month.isoformat() for month in sorted(self._profile_revision_pending_imports)],
                    "days": {day.isoformat(): stamp for day, stamp in self._current_profile_days.items()},
                    "checks": {day.isoformat(): checked.isoformat()
                               for day, checked in self._profile_revision_checks.items()},
                    "attempts": {day.isoformat(): attempted.isoformat()
                                 for day, attempted in self._profile_revision_attempts.items()},
                },
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
                "scan_end": two_calendar_month_start(
                    self.history_backfill_started_at.date()
                ).isoformat() if self.history_backfill_started_at else None,
                "pending_ranges": self.history_backfill_pending_ranges,
                "imported_day_keys": [day.isoformat() for day in sorted(self._history_backfill_day_keys)],
                "imported_hour_keys": [hour.isoformat() for hour in sorted(self._history_backfill_hour_keys)],
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
                "eans": [{"ean": item.ean, "role": item.role} for item in self.eans],
                "daily_rows": [
                    _serialize_daily_row(row)
                    for row in sorted(
                        self._history_days.values(), key=lambda item: item.day
                    )
                ],
                "target_daily_rows": [
                    _serialize_target_daily_row(row)
                    for ean in sorted(self._history_target_days)
                    for row in sorted(
                        self._history_target_days[ean].values(),
                        key=lambda item: item.day,
                    )
                ],
            }
        )

    @property
    def history_backfill_pending_ranges(self) -> list[dict[str, str]]:
        """Vrátit kopii neověřených rozsahů pro uložení a diagnostické entity."""
        return _history_gap_ranges(self._history_backfill_gaps)

    @callback
    def async_enable_history_import(self) -> None:
        """Enable imports after platforms have registered their entities."""
        self._history_import_enabled = True
        self._async_import_energy_history(dt_util.now())
        self._async_import_history_if_changed(
            self.data, tuple(self._hours.values()), dt_util.now()
        )
        self.async_start_profile_revisions()

    @callback
    def _async_import_energy_history(self, now: datetime) -> bool:
        """Zařadit celé kumulativní Energy; bool potvrzuje frontu, nikoli DB zápis.

        Prázdný výběr nebo totožný otisk není chyba. Při odmítnutí zařazení
        vracíme False, aby migrace revize zůstala uložená k opakování.
        """
        selected = energy_targets(self.config_entry.options)
        if not selected:
            return True
        price = Decimal(str(self.config_entry.options.get(
            CONF_SALE_PRICE, self.config_entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE)
        )))
        signature = (
            selected, now.date(), price,
            tuple((ean, target_sale_price(ean, self.config_entry.options, price),
                   ean_name(ean, self.config_entry.options),
                   tuple(sorted(self._history_target_days.get(ean, {}).items())))
                  for ean in selected),
        )
        if signature == self._energy_import_signature:
            return True
        try:
            async_import_energy_history(
                self.hass,
                sse_id=int(self.config_entry.data[CONF_SSE_ID]),
                sse_name=str(self.config_entry.data[CONF_SSE_NAME]),
                target_days=self._history_target_days,
                options=self.config_entry.options,
                sale_price=price,
                today=now.date(),
                local_tz=now.tzinfo or dt_util.get_default_time_zone(),
            )
        except HomeAssistantError:
            _LOGGER.warning("Could not queue EDC Energy statistics")
            return False
        self._energy_import_signature = signature
        return True

    def _async_import_history_if_changed(
        self,
        statistics: SharingStatistics,
        hours: tuple[HourlySharing, ...],
        now: datetime,
    ) -> bool:
        """Zařadit změněné denní/hodinové řady; bool je úspěch fronty.

        Stejný otisk se neopakuje. Chyba zařazení otisk neposune, takže
        další obnova může opravit i již kompletní CURRENT denní cache.
        """
        finalized = tuple(row for row in statistics.days if row.day < now.date())
        local_tz = now.tzinfo or dt_util.get_default_time_zone()
        current_hour = dt_util.as_utc(
            now.replace(minute=0, second=0, microsecond=0)
        )
        finalized_hours = tuple(
            sorted(
                (
                    row
                    for row in hours
                    if _hour_start_utc(row.start, local_tz) < current_hour
                ),
                key=lambda row: row.start,
            )
        )
        target_finalized_hours = tuple(
            row
            for ean in sorted(self._target_hours)
            for row in sorted(self._target_hours[ean].values(), key=lambda r: r.start)
            if _hour_start_utc(row.start, local_tz) < current_hour
        )
        signature: tuple[object, ...] = (
            *finalized,
            *finalized_hours,
            *target_finalized_hours,
            statistics.sale_price,
        )
        if signature == self._history_import_signature:
            return True
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
            imported_target_hours = 0
            for ean, ean_hours in self._target_hours.items():
                target_name = ean_name(ean, self.config_entry.options)
                imported_target_hours += async_import_target_hourly_history(
                    self.hass,
                    sse_id=self.config_entry.data[CONF_SSE_ID],
                    sse_name=str(self.config_entry.data[CONF_SSE_NAME]),
                    ean=ean,
                    target_name=target_name,
                    hours=tuple(ean_hours.values()),
                    now=now,
                    local_tz=now.tzinfo,
                )
        except HomeAssistantError as err:
            _LOGGER.warning("Could not import EDC history: %s", err)
            return False
        self._history_import_signature = signature
        self.data_quality["queued_hours"] = imported_hours
        self.data_quality["queued_target_hours"] = imported_target_hours
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
        if imported_target_hours:
            _LOGGER.debug(
                "Queued %s finalized EDC target hours for long-term statistics",
                imported_target_hours,
            )
        return True
