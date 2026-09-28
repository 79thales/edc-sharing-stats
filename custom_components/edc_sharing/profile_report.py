"""Independent report schedules and per-recipient delivery bookkeeping."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from html import escape
from hashlib import sha256

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .calculation import TargetDailySharing, calculate_period_summary, calculate_target_period_summary
from .const import (
    CONF_PAYMENT_ACCOUNT_NUMBER,
    CONF_PAYMENT_BANK_CODE,
    CONF_SALE_PRICE,
    CONF_SSE_ID,
    CONF_SSE_NAME,
    DEFAULT_SALE_PRICE,
)
from .ean_settings import ean_location, ean_name, target_sale_price
from .payment import (
    CzechBankAccount,
    PaymentRequest,
    parse_czech_account,
    payment_amount,
    payment_message,
    payment_qr_data_uri,
)
from .report import EdcReportManager, ReportPeriod
from .report_profiles import configured_profiles, due_on, next_run, period_range


class ProfileRenderer(EdcReportManager):
    """Render a profile without mutating shared entry options or language."""

    def __init__(self, reporter: EdcReportManager, profile: dict) -> None:
        super().__init__(reporter.hass, reporter.entry, reporter.coordinator)
        self.profile = profile
        self.today = dt_util.now().date()
        self._ranges: dict[tuple[date, date], tuple] = {}
        self._target_ranges: dict[
            tuple[date, date], dict[str, tuple[TargetDailySharing, ...]]
        ] = {}
        self.fingerprints: list[str] = []
        self.payment_requests: list[tuple[PaymentRequest, ...]] = []
        self._payment_account: CzechBankAccount | None = None
        if self.profile.get("payment_qr", False):
            self._payment_account = parse_czech_account(
                self.entry.options.get(CONF_PAYMENT_ACCOUNT_NUMBER),
                self.entry.options.get(CONF_PAYMENT_BANK_CODE),
            )

    @property
    def use_czech(self) -> bool:
        return self.profile["language"] == "cs"

    async def _async_report_days(self, period: ReportPeriod) -> tuple:
        if period == ReportPeriod.DAILY:
            return await super()._async_report_days(period)
        start, end = period_range(period.value, self.profile["period_mode"], self.today)
        key = (start, end)
        if key not in self._ranges:
            self._ranges[key] = await self._async_fetch_days(start, end)
        return start, end, self._ranges[key]

    async def _async_target_report_days(
        self, period: ReportPeriod
    ) -> tuple[date, date, dict[str, tuple[TargetDailySharing, ...]]]:
        """Return report rows separated by target EAN for a selected period."""
        if period == ReportPeriod.DAILY:
            if (self.profile.get("report_scope") == "target"
                    and self.profile.get("target_daily_mode") == "per_ean_day"):
                cached = self.coordinator.target_days_for_range(
                    date.min, self.today + timedelta(days=1)
                )
                latest = {
                    ean: (max(rows, key=lambda row: row.day),)
                    for ean, rows in cached.items()
                    if rows and ean in self.profile["target_eans"]
                }
                dates = [rows[0].day for rows in latest.values()]
                return (
                    min(dates) if dates else self.today,
                    (max(dates) if dates else self.today) + timedelta(days=1),
                    latest,
                )
            latest_day = self.coordinator.data.latest_day
            if latest_day is None:
                return self.today, self.today + timedelta(days=1), {}
            start, end = latest_day, latest_day + timedelta(days=1)
            cached = getattr(self.coordinator, "target_days_for_range", None)
            if callable(cached):
                return start, end, cached(start, end)
        else:
            start, end = period_range(
                period.value, self.profile["period_mode"], self.today
            )
        key = (start, end)
        if key not in self._target_ranges:
            self._target_ranges[key] = await self._async_fetch_target_days(start, end)
        return start, end, self._target_ranges[key]

    def _target_ean_text(self, ean: str) -> str | None:
        """Return the configured privacy representation of one target EAN."""
        mode = self.profile["ean_mode"]
        if mode == "hidden":
            return None
        return ean if mode == "full" else "…" + ean[-4:]

    def _target_display_name(self, ean: str) -> str:
        """Use an alias, or honor EAN visibility when no alias exists."""
        configured_name = ean_name(ean, self.entry.options)
        if configured_name != ean:
            return configured_name
        if self.profile["ean_mode"] == "full":
            return ean
        if self.profile["ean_mode"] == "masked":
            return "…" + ean[-4:]
        return "Cílové odběrné místo" if self.use_czech else "Target supply point"

    def _profile_subject(self, label: str) -> str:
        """Build a single-line subject respecting EAN visibility."""
        scope = str(self.entry.data[CONF_SSE_NAME])
        if self.profile.get("report_scope") == "target":
            eans = self.profile["target_eans"]
            scope = (self._target_display_name(eans[0]) if len(eans) == 1 else
                     f"{len(eans)} {'odběrná místa' if self.use_czech else 'supply points'}")
        parts = ("EDC", self.profile["name"], scope, label)
        return " | ".join(" ".join(str(part).split()) for part in parts)

    def _period_subject(self, period: ReportPeriod, start: date, end: date) -> str:
        labels = {
            "daily": ("Denní", "Daily"), "weekly": ("Týdenní", "Weekly"),
            "monthly": ("Měsíční", "Monthly"), "yearly": ("Roční", "Yearly"),
        }
        label = labels[period.value][0 if self.use_czech else 1]
        last = end - timedelta(days=1)
        date_text = str(start) if start == last else f"{start} – {last}"
        return self._profile_subject(f"{label}: {date_text}")

    def _summary_subject(self) -> str:
        labels = {"daily": ("denní", "daily"), "weekly": ("týdenní", "weekly"),
                  "monthly": ("měsíční", "monthly"), "yearly": ("roční", "yearly")}
        periods = ", ".join(labels[p][0 if self.use_czech else 1] for p in self.profile["periods"])
        return self._profile_subject(f"{'Souhrn' if self.use_czech else 'Summary'}: {periods}")

    @staticmethod
    def _complete_period(days: tuple, start: date, end: date) -> bool:
        """Payment requests need every calendar day of their requested range."""
        return {row.day for row in days} == {
            start + timedelta(days=offset) for offset in range((end - start).days)
        }

    def _payment_request(
        self,
        period: ReportPeriod,
        start: date,
        end: date,
        days: tuple,
        value: Decimal,
    ) -> PaymentRequest | None:
        """Return a safe payment request only for complete monthly/yearly data."""
        if (
            self._payment_account is None
            or period not in (ReportPeriod.MONTHLY, ReportPeriod.YEARLY)
            or not self._complete_period(days, start, end)
            or (amount := payment_amount(value)) is None
        ):
            return None
        period_text = (
            f"mesic {start:%Y-%m}"
            if period == ReportPeriod.MONTHLY
            else f"rok {start:%Y}"
        )
        return PaymentRequest(
            account=self._payment_account,
            amount=amount,
            message=payment_message(self.entry.data[CONF_SSE_NAME], period_text),
        )

    def _payment_lines(self, request: PaymentRequest) -> list[str]:
        """Keep the payment transparent in both previews and text-only mail."""
        if self.use_czech:
            return [
                "",
                "Platba QR:",
                f"Částka k úhradě: {request.amount:.2f} CZK",
                f"Účet: {request.account.domestic}",
                f"Zpráva pro příjemce: {request.message}",
                "QR kód bude součástí HTML obsahu e-mailu.",
            ]
        return [
            "",
            "QR payment:",
            f"Amount due: {request.amount:.2f} CZK",
            f"Account: {request.account.domestic}",
            f"Recipient message: {request.message}",
            "The QR code is included directly in the HTML email body.",
        ]

    async def _render_target_reports(self) -> list[tuple[str, str]]:
        """Render individual recipient reports without changing group reports."""
        reports: list[tuple[str, str]] = []
        fingerprints: list[str] = []
        report_payments: list[tuple[PaymentRequest, ...]] = []
        default_price = Decimal(
            str(
                self.entry.options.get(
                    CONF_SALE_PRICE,
                    self.entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE),
                )
            )
        )
        selected_eans = tuple(self.profile["target_eans"])
        cs = self.use_czech
        for value in self.profile["periods"]:
            period = ReportPeriod(value)
            start, end, all_rows = await self._async_target_report_days(period)
            prices = {
                ean: target_sale_price(ean, self.entry.options, default_price)
                for ean in selected_eans
            }
            content_key = (
                "target",
                period.value,
                start,
                tuple((ean, all_rows.get(ean, ()), prices[ean]) for ean in selected_eans),
                tuple(
                    (
                        ean,
                        ean_name(ean, self.entry.options),
                        ean_location(ean, self.entry.options),
                    )
                    for ean in selected_eans
                ),
                self.profile["language"],
                self.profile["energy"],
                self.profile["finance"],
                self.profile.get("payment_qr", False),
                self.profile["ean_mode"],
                self.entry.data[CONF_SSE_ID],
                self._payment_account.iban if self._payment_account else None,
            )
            fingerprints.append(sha256(repr(content_key).encode()).hexdigest())
            title = self._period_subject(period, start, end)
            lines = [
                title,
                f"{'Skupina' if cs else 'Group'}: {self.entry.data[CONF_SSE_NAME]}",
                f"{'Období' if cs else 'Period'}: {start} – {end - timedelta(days=1)}",
            ]
            payments: list[PaymentRequest] = []
            for ean in selected_eans:
                days = all_rows.get(ean, ())
                name = self._target_display_name(ean)
                lines.extend(
                    (
                        "",
                        f"{'Cílové odběrné místo' if cs else 'Target supply point'}: {name}",
                    )
                )
                if location := ean_location(ean, self.entry.options):
                    lines.append(f"{'Lokalita' if cs else 'Location'}: {location}")
                if visible_ean := self._target_ean_text(ean):
                    lines.append(f"{'Cílový EAN' if cs else 'Target EAN'}: {visible_ean}")
                if not days:
                    lines.append(
                        "Data pro toto odběrné místo nejsou v období dostupná."
                        if cs
                        else "Data for this supply point are not available for this period."
                    )
                    continue
                actual_start, actual_end = min(d.day for d in days), max(
                    d.day for d in days
                )
                individual_day = period == ReportPeriod.DAILY and self.profile.get("target_daily_mode") == "per_ean_day"
                count, expected = len({d.day for d in days}), 1 if individual_day else (end - start).days
                if individual_day:
                    lines.append(f"{'Datum dat' if cs else 'Data date'}: {actual_end}")
                lines.append(
                    f"{'Dostupná denní data' if cs else 'Available daily data'}: {actual_start} – {actual_end} ({count}/{expected})"
                )
                if count < expected:
                    lines.append(
                        "Neúplné období: součet pouze dostupných denních dat."
                        if cs
                        else "Incomplete period: totals include available daily data only."
                    )
                summary = calculate_target_period_summary(days, prices[ean])
                if self.profile["energy"]:
                    for label_cs, label_en, field in (
                        ("Spotřeba", "Consumption", "consumption"),
                        ("Nasdíleno", "Shared electricity", "shared"),
                        ("Dokup ze sítě", "Grid import", "grid_purchase"),
                    ):
                        lines.append(
                            f"{label_cs if cs else label_en}: {getattr(summary, field):.2f} kWh"
                        )
                    lines.append(
                        f"{'Pokrytí sdílením' if cs else 'Sharing coverage'}: {summary.coverage:.1f} %"
                    )
                if self.profile["finance"]:
                    lines.extend(
                        (
                            f"{'Cena' if cs else 'Price'}: {prices[ean]:.2f} CZK/kWh",
                            f"{'Hodnota sdílení' if cs else 'Sharing value'}: {summary.revenue:.2f} CZK",
                        )
                    )
                    if request := self._payment_request(
                        period, start, end, days, summary.revenue
                    ):
                        lines.extend(self._payment_lines(request))
                        payments.append(request)
            reports.append((title, "\n".join(lines)))
            report_payments.append(tuple(payments))
        if self.profile["combined"]:
            self.fingerprints = [sha256("".join(fingerprints).encode()).hexdigest()]
            self.payment_requests = [
                tuple(payment for payments in report_payments for payment in payments)
            ]
            return [
                (
                    reports[0][0] if len(reports) == 1 else self._summary_subject(),
                    "\n\n--------------------\n\n".join(
                        message for _, message in reports
                    ),
                )
            ]
        self.fingerprints = fingerprints
        self.payment_requests = report_payments
        return reports

    async def _group_ean_finance(self, period, days):
        """Value each target separately and verify coverage against group days."""
        _, _, all_rows = await self._async_target_report_days(period)
        default_price = Decimal(str(self.entry.options.get(
            CONF_SALE_PRICE, self.entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE)
        )))
        dates = {row.day for row in days}
        cs = self.use_czech
        lines = ["Rozpis podle odběrných míst:" if cs else "Breakdown by supply point:"]
        total = Decimal("0")
        by_day = {}
        evidence = []
        for ean, rows in sorted(all_rows.items()):
            rows = tuple(row for row in rows if row.day in dates)
            if not rows:
                continue
            price = target_sale_price(ean, self.entry.options, default_price)
            summary = calculate_target_period_summary(rows, price)
            name = self._target_display_name(ean)
            location = ean_location(ean, self.entry.options)
            if location:
                name += f" — {location}"
            lines.append(f"{name}: {summary.shared:.2f} kWh × {price:.2f} CZK/kWh = {summary.revenue:.2f} CZK")
            total += summary.revenue
            for row in rows:
                by_day[row.day] = by_day.get(row.day, Decimal("0")) + row.shared
            evidence.append((ean, rows, price, name))
        complete = bool(days) and all(
            row.day in by_day and abs(by_day[row.day] - row.shared) <= Decimal("0.000001")
            for row in days
        )
        if complete:
            lines.append(f"{'Hodnota sdílení celkem' if cs else 'Total sharing value'}: {total:.2f} CZK")
        else:
            lines.append(
                "Celkovou hodnotu nelze potvrdit: individuální data nejsou dostupná nebo nesouhlasí se skupinou. Rozpis je pouze částečný."
                if cs else "The total cannot be confirmed: individual data is unavailable or does not match group data. The breakdown is partial."
            )
        return lines, (tuple(evidence), complete, total)

    async def render(self) -> list[tuple[str, str]]:
        """Build selected sections once, then reuse them for all recipients."""
        if self.profile.get("report_scope") == "target":
            return await self._render_target_reports()
        reports = []
        fingerprints = []
        report_payments: list[tuple[PaymentRequest, ...]] = []
        for value in self.profile["periods"]:
            period = ReportPeriod(value)
            start, end, days = await self._async_report_days(period)
            ean_finance = None
            finance_evidence = None
            if self.profile["finance"] and self.profile.get("group_finance_mode") == "ean_prices":
                ean_finance, finance_evidence = await self._group_ean_finance(period, days)
            # Base change detection on data, not the moving end date of a
            # current-period heading. Revised EDC values still trigger sending.
            content_key = (
                period.value,
                start,
                days,
                finance_evidence,
                self.profile["language"],
                self.profile["energy"],
                self.profile["finance"],
                self.profile.get("payment_qr", False),
                self.profile["ean_mode"],
                self.entry.data[CONF_SSE_ID],
                self._payment_account.iban if self._payment_account else None,
                self.entry.options.get(
                    CONF_SALE_PRICE,
                    self.entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE),
                ),
            )
            fingerprints.append(sha256(repr(content_key).encode()).hexdigest())
            cs = self.use_czech
            title = self._period_subject(period, start, end)
            lines = [
                title,
                f"{'Období' if cs else 'Period'}: {start} – {end - timedelta(days=1)}",
            ]
            payments: list[PaymentRequest] = []
            if not days:
                lines.append(
                    "Data pro toto období nejsou dostupná."
                    if cs
                    else "Data for this period are not available."
                )
            else:
                actual_start, actual_end = (
                    min(d.day for d in days),
                    max(d.day for d in days),
                )
                count, expected = len({d.day for d in days}), (end - start).days
                lines.append(
                    f"{'Dostupná denní data' if cs else 'Available daily data'}: {actual_start} – {actual_end} ({count}/{expected})"
                )
                if count < expected:
                    lines.append(
                        "Neúplné období: součet pouze dostupných denních dat."
                        if cs
                        else "Incomplete period: totals include available daily data only."
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
                lines.append("")
                if self.profile["energy"]:
                    for label_cs, label_en, field in (
                        ("Spotřeba", "Consumption", "consumption"),
                        ("Nasdíleno", "Shared electricity", "shared"),
                        ("Dokup ze sítě", "Grid import", "grid_purchase"),
                        ("Přetok výrobny", "Production surplus", "producer_overflow"),
                        ("Nevyužitý přetok", "Unused surplus", "unused_overflow"),
                    ):
                        lines.append(
                            f"{label_cs if cs else label_en}: {getattr(summary, field):.2f} kWh"
                        )
                    lines.append(
                        f"{'Pokrytí sdílením' if cs else 'Sharing coverage'}: {summary.coverage:.1f} %"
                    )
                if ean_finance is not None:
                    lines.extend(ean_finance)
                    _evidence, complete, total = finance_evidence
                    if complete and (
                        request := self._payment_request(
                            period, start, end, days, total
                        )
                    ):
                        lines.extend(self._payment_lines(request))
                        payments.append(request)
                elif self.profile["finance"]:
                    lines.extend(
                        (
                            f"{'Cena' if cs else 'Price'}: {price:.2f} CZK/kWh",
                            f"{'Hodnota sdílení' if cs else 'Sharing value'}: {summary.revenue:.2f} CZK",
                        )
                    )
                    if request := self._payment_request(
                        period, start, end, days, summary.revenue
                    ):
                        lines.extend(self._payment_lines(request))
                        payments.append(request)
                if self.profile["ean_mode"] != "hidden":
                    for role, label in (
                        ("sharing", "Sdílející EAN" if cs else "Sharing EAN"),
                        ("target", "Cílové EAN" if cs else "Target EAN"),
                    ):
                        eans = [
                            item.ean
                            if self.profile["ean_mode"] == "full"
                            else "…" + item.ean[-4:]
                            for item in self.coordinator.eans
                            if item.role == role
                        ]
                        lines.append(f"{label}: {', '.join(eans) or '–'}")
            reports.append((title, "\n".join(lines)))
            report_payments.append(tuple(payments))
        if self.profile["combined"]:
            self.fingerprints = [sha256("".join(fingerprints).encode()).hexdigest()]
            self.payment_requests = [
                tuple(payment for payments in report_payments for payment in payments)
            ]
            return [
                (
                    reports[0][0] if len(reports) == 1 else self._summary_subject(),
                    "\n\n--------------------\n\n".join(
                        message for _, message in reports
                    ),
                )
            ]
        self.fingerprints = fingerprints
        self.payment_requests = report_payments
        return reports


class ProfileReportManager:
    """Schedule profiles and persist only delivery metadata, never email bodies."""

    def __init__(self, reporter: EdcReportManager) -> None:
        self.reporter = reporter
        self.hass = reporter.hass
        self.entry = reporter.entry
        language = "cs" if reporter.use_czech else "en"
        self.profiles = configured_profiles(self.entry.options, language)
        self.store = Store(self.hass, 1, f"edc_sharing_reports.{self.entry.entry_id}")
        self.state: dict = {}
        self.lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()
        self.closed = False

    async def async_initialize(self) -> None:
        self.state = await self.store.async_load() or {}
        # A process interrupted after a successful recipient handoff can have
        # persisted intermediate progress. It is no longer actively sending.
        interrupted = False
        for record in self.state.values():
            if record.get("result") == "sending":
                record["result"] = "interrupted"
                interrupted = True
        if interrupted:
            await self.store.async_save(self.state)

    def start(self) -> None:
        self.entry.async_on_unload(self.close)
        for profile in self.profiles:
            if not profile["enabled"] or not profile["targets"]:
                continue
            parsed = time.fromisoformat(profile["time"])

            async def scheduled(now: datetime, selected: dict = profile) -> None:
                if due_on(selected, dt_util.as_local(now).date()):
                    await self.async_send(selected, scheduled=True)

            self.entry.async_on_unload(
                async_track_time_change(
                    self.hass,
                    scheduled,
                    hour=parsed.hour,
                    minute=parsed.minute,
                    second=parsed.second,
                )
            )

    def close(self) -> None:
        """Stop in-flight profile sends when settings reload or HA unloads us."""
        self.closed = True
        for task in self.tasks:
            task.cancel()

    def status(self, profile: dict) -> dict:
        state = self.state.get(profile["id"], {})
        upcoming = next_run(profile, dt_util.now())
        return {
            "result": state.get("result", "not_sent"),
            "last_attempt": state.get("last_attempt", "–"),
            "last_success": state.get("last_success", "–"),
            "next_attempt": upcoming.isoformat() if upcoming else "–",
        }

    async def preview(self, profile: dict) -> list[tuple[str, str]]:
        async with self.lock:
            return await ProfileRenderer(self.reporter, profile).render()

    @staticmethod
    def _payment_html(
        body: str,
        requests: tuple[PaymentRequest, ...],
        images: tuple[str, ...],
        *,
        czech: bool,
    ) -> str:
        """Render report content with in-memory QR images for SMTP HTML."""
        sections = ["<html><body><pre>", escape(body), "</pre>"]
        payment_label = "Platba QR" if czech else "QR payment"
        account_label = "Účet" if czech else "Account"
        message_label = "Zpráva pro příjemce" if czech else "Recipient message"
        for index, (request, image) in enumerate(zip(requests, images), start=1):
            sections.extend(
                (
                    "<hr>",
                    f"<p><strong>{payment_label}: {request.amount:.2f} CZK</strong><br>",
                    f"{account_label}: {escape(request.account.domestic)}<br>",
                    f"{message_label}: {escape(request.message)}</p>",
                    f'<img src="{image}" '
                    f'alt="QR payment {index}">',
                )
            )
        sections.append("</body></html>")
        return "".join(sections)

    async def _async_send_to_recipient(
        self,
        target: str,
        title: str,
        body: str,
        requests: tuple[PaymentRequest, ...],
        *,
        czech: bool,
    ) -> None:
        """Use generic notify delivery unless an inline SMTP QR is requested."""
        if not requests:
            await self.hass.services.async_call(
                "notify",
                "send_message",
                {"title": title, "message": body},
                target={"entity_id": target},
                blocking=True,
            )
            return
        has_service = getattr(self.hass.services, "has_service", None)
        if callable(has_service) and not has_service("smtp", "send_message"):
            raise HomeAssistantError("The SMTP send_message action is unavailable")
        images: list[str] = []
        for request in requests:
            images.append(
                await self.hass.async_add_executor_job(
                    payment_qr_data_uri, request.spd
                )
            )
        await self.hass.services.async_call(
            "smtp",
            "send_message",
            {
                "title": title,
                "message": body,
                "html": self._payment_html(
                    body, requests, tuple(images), czech=czech
                ),
            },
            target={"entity_id": target},
            blocking=True,
        )

    async def async_send(self, profile: dict, *, scheduled: bool = False) -> None:
        if self.closed:
            raise HomeAssistantError("Report settings are reloading. Try again.")
        task = asyncio.current_task()
        self.tasks.add(task)
        try:
            await self._async_send(profile, scheduled=scheduled)
        finally:
            self.tasks.discard(task)

    async def _async_send(self, profile: dict, *, scheduled: bool) -> None:
        async with self.lock:
            record = self.state.setdefault(profile["id"], {})
            now = dt_util.now()
            # One local calendar occurrence, including both folds at autumn DST.
            slot = f"{now.date()}T{profile['time']}:{self.entry.data[CONF_SSE_ID]}"
            sent = record.setdefault("sent", {})
            record["last_attempt"] = now.isoformat()
            record["result"] = "sending"
            try:
                renderer = ProfileRenderer(self.reporter, profile)
                messages = await renderer.render()
                failures, delivered = 0, 0
                for index, (title, body) in enumerate(messages):
                    fingerprint = renderer.fingerprints[index]
                    for target in profile["targets"]:
                        # Hash routing identifiers in runtime storage; no names/addresses.
                        key = sha256(f"{target}:{index}".encode()).hexdigest()
                        previous = sent.get(key, {})
                        if scheduled and (
                            previous.get("slot") == slot
                            or profile["only_new"]
                            and previous.get("fingerprint") == fingerprint
                        ):
                            continue
                        try:
                            await self._async_send_to_recipient(
                                target,
                                title,
                                body,
                                renderer.payment_requests[index],
                                czech=renderer.use_czech,
                            )
                        except Exception:  # noqa: BLE001 -- isolate arbitrary notify integrations and redact their errors
                            # SMTP exceptions may include addresses or credentials.
                            failures += 1
                            continue
                        delivered += 1
                        sent[key] = {"slot": slot, "fingerprint": fingerprint}
                        record["last_success"] = dt_util.now().isoformat()
                        await self.store.async_save(self.state)
                record["result"] = (
                    "partial_failure"
                    if failures and delivered
                    else "failed"
                    if failures
                    else "sent"
                    if delivered
                    else "no_new_data"
                )
                record["failed_deliveries"] = failures
                record["successful_deliveries"] = delivered
            except (HomeAssistantError, ValueError, KeyError, TypeError, OSError):
                record["result"] = "failed"
            await self.store.async_save(self.state)
            if not scheduled and record["result"] in ("failed", "partial_failure"):
                raise HomeAssistantError(
                    "Report could not be sent to all recipients. Check EDC availability and SMTP settings."
                ) from None
