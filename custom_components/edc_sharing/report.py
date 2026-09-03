"""Daily, weekly, monthly, yearly, and summary EDC email reports."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .api import EdcApiError, EdcAuthenticationError
from .calculation import (
    DailySharing,
    PeriodSummary,
    calculate_period_summary,
    completed_report_range,
    parse_daily_profile,
    profile_date_ranges,
)
from .const import (
    CONF_DAILY_REPORT,
    CONF_WEEKLY_REPORT,
    CONF_MONTHLY_REPORT,
    CONF_REPORT_DAY,
    CONF_REPORT_LANGUAGE,
    CONF_REPORT_TARGETS,
    CONF_REPORT_TIME,
    CONF_SALE_PRICE,
    CONF_SSE_ID,
    CONF_SSE_NAME,
    CONF_SUMMARY_REPORT,
    CONF_YEARLY_REPORT,
    DEFAULT_REPORT_DAY,
    DEFAULT_REPORT_TIME,
    DEFAULT_SALE_PRICE,
)

if TYPE_CHECKING:
    from . import EdcConfigEntry
    from .coordinator import EdcSharingCoordinator

_LOGGER = logging.getLogger(__name__)


class ReportPeriod(StrEnum):
    """Supported report periods."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    SUMMARY = "summary"


class EdcReportManager:
    """Build and send reports through Home Assistant notify entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: EdcConfigEntry,
        coordinator: EdcSharingCoordinator,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator

    @property
    def targets(self) -> tuple[str, ...]:
        """Return configured notify entity IDs."""
        value = self.entry.options.get(CONF_REPORT_TARGETS, [])
        if not value:
            return ()
        if isinstance(value, str):
            return (value,)
        return tuple(str(item) for item in value if item)

    @property
    def use_czech(self) -> bool:
        """Return the explicitly selected report language."""
        configured = self.entry.options.get(CONF_REPORT_LANGUAGE)
        if configured in ("cs", "en"):
            return configured == "cs"
        return (self.hass.config.language or "en").casefold().startswith("cs")

    @callback
    def async_start(self) -> None:
        """Start the configured report scheduler."""
        report_time = str(
            self.entry.options.get(CONF_REPORT_TIME, DEFAULT_REPORT_TIME)
        )
        try:
            parsed_time = time.fromisoformat(report_time)
        except ValueError:
            parsed_time = time.fromisoformat(DEFAULT_REPORT_TIME)
        self.entry.async_on_unload(
            async_track_time_change(
                self.hass,
                self._async_scheduled_reports,
                hour=parsed_time.hour,
                minute=parsed_time.minute,
                second=parsed_time.second,
            )
        )

    async def _async_scheduled_reports(self, now: datetime) -> None:
        """Send reports enabled for this local calendar day."""
        if not self.targets:
            return
        periods: list[ReportPeriod] = []
        if self.entry.options.get(CONF_SUMMARY_REPORT, False):
            periods.append(ReportPeriod.SUMMARY)
        if self.entry.options.get(CONF_DAILY_REPORT, False):
            periods.append(ReportPeriod.DAILY)
        if self.entry.options.get(CONF_WEEKLY_REPORT, False) and now.weekday() == 0:
            periods.append(ReportPeriod.WEEKLY)
        report_day = int(
            self.entry.options.get(CONF_REPORT_DAY, DEFAULT_REPORT_DAY)
        )
        if (
            self.entry.options.get(CONF_MONTHLY_REPORT, False)
            and now.day == report_day
        ):
            periods.append(ReportPeriod.MONTHLY)
        if (
            self.entry.options.get(CONF_YEARLY_REPORT, False)
            and now.month == 1
            and now.day == report_day
        ):
            periods.append(ReportPeriod.YEARLY)

        for period in periods:
            try:
                await self.async_send(period)
            except HomeAssistantError as err:
                _LOGGER.warning("Could not send EDC %s report: %s", period, err)

    async def async_send(self, period: ReportPeriod) -> None:
        """Build and send one report to every configured target."""
        if not self.targets:
            raise HomeAssistantError(
                "Nejsou vybráni příjemci reportů EDC."
            )
        if not self.hass.services.has_service("notify", "send_message"):
            raise HomeAssistantError(
                "Služba notify.send_message není v Home Assistantu dostupná."
            )

        if period is ReportPeriod.SUMMARY:
            await self.async_send_summary()
            return

        message = await self._async_build_report(period)
        await self._async_send_message(message, self._report_title(period))

    async def async_send_summary(self) -> None:
        """Send all supported periods together in one email."""
        if not self.targets:
            raise HomeAssistantError(
                "Nejsou vybráni příjemci reportů EDC."
            )

        reports: list[str] = []
        for period in (
            ReportPeriod.DAILY,
            ReportPeriod.WEEKLY,
            ReportPeriod.MONTHLY,
            ReportPeriod.YEARLY,
        ):
            try:
                reports.append(await self._async_build_report(period))
            except HomeAssistantError as err:
                _LOGGER.warning("Could not include EDC %s report: %s", period, err)
                reports.append(self._format_unavailable_report(period))
        await self._async_send_message(
            "\n\n--------------------\n\n".join(reports),
            self._report_title(ReportPeriod.SUMMARY),
        )

    async def _async_build_report(self, period: ReportPeriod) -> str:
        """Fetch and format one report period."""
        start, end, days = await self._async_report_days(period)
        if not days:
            raise HomeAssistantError(
                "EDC pro požadované období nevrátilo žádná data."
            )
        price = Decimal(
            str(
                self.entry.options.get(
                    CONF_SALE_PRICE,
                    self.entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE),
                )
            )
        )
        summary = calculate_period_summary(days, price)
        return self._format_report(period, start, end, summary)

    async def _async_send_message(self, message: str, title: str) -> None:
        """Send one message to every configured notification target."""
        if not self.hass.services.has_service("notify", "send_message"):
            raise HomeAssistantError(
                "Služba notify.send_message není v Home Assistantu dostupná."
            )
        await self.hass.services.async_call(
            "notify",
            "send_message",
            {"message": message, "title": title},
            target={"entity_id": list(self.targets)},
            blocking=True,
        )

    def _report_title(self, period: ReportPeriod) -> str:
        """Return a localized email subject."""
        czech = self.use_czech
        labels = {
            ReportPeriod.DAILY: ("Denní report", "Daily report"),
            ReportPeriod.WEEKLY: ("Týdenní report", "Weekly report"),
            ReportPeriod.MONTHLY: ("Měsíční report", "Monthly report"),
            ReportPeriod.YEARLY: ("Roční report", "Yearly report"),
            ReportPeriod.SUMMARY: ("Souhrnný report", "Summary report"),
        }
        label = labels[period][0 if czech else 1]
        return f"EDC – {label} – {self.entry.data[CONF_SSE_NAME]}"

    async def _async_report_days(
        self, period: ReportPeriod
    ) -> tuple[date, date, tuple[DailySharing, ...]]:
        """Return the half-open report range and its daily rows."""
        today = dt_util.now().date()
        if period is ReportPeriod.DAILY:
            latest_day = self.coordinator.data.latest_day
            if latest_day is None:
                return today, today + timedelta(days=1), ()
            return (
                latest_day,
                latest_day + timedelta(days=1),
                (self.coordinator.data.latest,),
            )
        if period is ReportPeriod.SUMMARY:
            raise HomeAssistantError("Souhrnný report nemá vlastní období.")
        start, end = completed_report_range(period.value, today)
        return start, end, await self._async_fetch_days(start, end)

    async def _async_fetch_days(
        self, date_from: date, date_to: date
    ) -> tuple[DailySharing, ...]:
        """Fetch and merge an arbitrary EDC report period."""
        local_tz = dt_util.now().tzinfo
        fetched: dict[date, DailySharing] = {}
        try:
            for chunk_from, chunk_to in profile_date_ranges(date_from, date_to):
                local_from = datetime.combine(chunk_from, time.min, tzinfo=local_tz)
                local_to = datetime.combine(chunk_to, time.min, tzinfo=local_tz)
                raw = await self.coordinator.api.async_get_daily_profile(
                    int(self.entry.data[CONF_SSE_ID]),
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
        except EdcAuthenticationError as err:
            raise HomeAssistantError(
                "Přihlášení k EDC již není platné."
            ) from err
        except (EdcApiError, ValueError, KeyError) as err:
            raise HomeAssistantError(str(err)) from err
        return tuple(fetched[day] for day in sorted(fetched))

    def _format_unavailable_report(self, period: ReportPeriod) -> str:
        """Format a visible placeholder for a missing summary section."""
        czech = self.use_czech
        labels = {
            ReportPeriod.DAILY: ("Denní report", "Daily report"),
            ReportPeriod.WEEKLY: ("Týdenní report", "Weekly report"),
            ReportPeriod.MONTHLY: ("Měsíční report", "Monthly report"),
            ReportPeriod.YEARLY: ("Roční report", "Yearly report"),
        }
        label = labels[period][0 if czech else 1]
        unavailable = (
            "Data pro toto období nejsou dostupná."
            if czech
            else "Data for this period are not available."
        )
        return f"EDC – {label}\n{unavailable}"

    def _format_report(
        self,
        period: ReportPeriod,
        start: date,
        end: date,
        summary: PeriodSummary,
    ) -> str:
        """Format a localized plain-text report."""
        czech = self.use_czech
        labels_cs = {
            ReportPeriod.DAILY: "Denní report",
            ReportPeriod.WEEKLY: "Týdenní report",
            ReportPeriod.MONTHLY: "Měsíční report",
            ReportPeriod.YEARLY: "Roční report",
            ReportPeriod.SUMMARY: "Souhrnný report",
        }
        labels_en = {
            ReportPeriod.DAILY: "Daily report",
            ReportPeriod.WEEKLY: "Weekly report",
            ReportPeriod.MONTHLY: "Monthly report",
            ReportPeriod.YEARLY: "Yearly report",
            ReportPeriod.SUMMARY: "Summary report",
        }
        period_text = (
            start.isoformat()
            if end == start + timedelta(days=1)
            else f"{start.isoformat()} – {(end - timedelta(days=1)).isoformat()}"
        )
        sharing_eans = ", ".join(
            item.ean for item in self.coordinator.eans if item.role == "sharing"
        ) or "–"
        target_eans = ", ".join(
            item.ean for item in self.coordinator.eans if item.role == "target"
        ) or "–"
        if czech:
            return "\n".join(
                (
                    f"EDC – {labels_cs[period]}",
                    f"Skupina: {self.entry.data[CONF_SSE_NAME]}",
                    f"Sdílející EAN: {sharing_eans}",
                    f"Cílové EAN: {target_eans}",
                    f"Období: {period_text}",
                    "",
                    f"Spotřeba: {summary.consumption:.2f} kWh",
                    f"Nasdíleno: {summary.shared:.2f} kWh",
                    f"Dokup ze sítě: {summary.grid_purchase:.2f} kWh",
                    f"Přetok výrobny: {summary.producer_overflow:.2f} kWh",
                    f"Nevyužitý přetok: {summary.unused_overflow:.2f} kWh",
                    f"Pokrytí sdílením: {summary.coverage:.1f} %",
                    f"Hodnota sdílení: {summary.revenue:.2f} Kč",
                )
            )
        return "\n".join(
            (
                f"EDC – {labels_en[period]}",
                f"Group: {self.entry.data[CONF_SSE_NAME]}",
                f"Sharing EAN: {sharing_eans}",
                f"Target EAN: {target_eans}",
                f"Period: {period_text}",
                "",
                f"Consumption: {summary.consumption:.2f} kWh",
                f"Shared: {summary.shared:.2f} kWh",
                f"Grid purchase: {summary.grid_purchase:.2f} kWh",
                f"Production surplus: {summary.producer_overflow:.2f} kWh",
                f"Unused surplus: {summary.unused_overflow:.2f} kWh",
                f"Sharing coverage: {summary.coverage:.1f} %",
                f"Sharing value: {summary.revenue:.2f} CZK",
            )
        )
