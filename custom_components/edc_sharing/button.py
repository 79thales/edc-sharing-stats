"""Buttons for sending EDC reports on demand."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EdcConfigEntry
from .const import CONF_SSE_ID, CONF_SSE_NAME, DOMAIN
from .coordinator import EdcSharingCoordinator
from .dashboard import PANEL_PATH
from .report import ReportPeriod


@dataclass(frozen=True, kw_only=True)
class EdcReportButtonDescription(ButtonEntityDescription):
    """Describe one report button."""

    period: ReportPeriod


BUTTONS = (
    EdcReportButtonDescription(
        key="send_daily_report",
        translation_key="send_daily_report",
        icon="mdi:email-fast-outline",
        period=ReportPeriod.DAILY,
    ),
    EdcReportButtonDescription(
        key="send_weekly_report",
        translation_key="send_weekly_report",
        icon="mdi:email-sync-outline",
        period=ReportPeriod.WEEKLY,
    ),
    EdcReportButtonDescription(
        key="send_monthly_report",
        translation_key="send_monthly_report",
        icon="mdi:email-arrow-right-outline",
        period=ReportPeriod.MONTHLY,
    ),
    EdcReportButtonDescription(
        key="send_yearly_report",
        translation_key="send_yearly_report",
        icon="mdi:email-newsletter",
        period=ReportPeriod.YEARLY,
    ),
    EdcReportButtonDescription(
        key="send_summary_report",
        translation_key="send_summary_report",
        icon="mdi:email-multiple-outline",
        period=ReportPeriod.SUMMARY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EdcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up report and manual data refresh buttons."""
    async_add_entities(
        [EdcReportButton(entry, description) for description in BUTTONS]
        + [EdcRefreshButton(entry), EdcHistoryBackfillButton(entry), EdcDashboardButton(entry)]
    )


class EdcReportButton(CoordinatorEntity[EdcSharingCoordinator], ButtonEntity):
    """Send one EDC report."""

    _attr_has_entity_name = True

    def __init__(
        self, entry: EdcConfigEntry, description: EdcReportButtonDescription
    ) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.data[CONF_SSE_ID]}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.data[CONF_SSE_ID]))},
            name=str(entry.data[CONF_SSE_NAME]),
            manufacturer="Elektroenergetické datové centrum, a. s.",
            model="Skupina sdílení elektřiny",
            configuration_url="https://portal.edc-cr.cz/sprava-dat/zobrazeni-dat",
        )

    @property
    def available(self) -> bool:
        """Only enable sending after at least one target is selected."""
        return super().available and bool(self._entry.runtime_data.reporter.targets)

    async def async_press(self) -> None:
        """Send the selected report."""
        await self._entry.runtime_data.reporter.async_send(
            self.entity_description.period
        )


class EdcRefreshButton(ButtonEntity):
    """Request an immediate EDC data download."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh_data"
    _attr_icon = "mdi:cloud-refresh"

    def __init__(self, entry: EdcConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.data[CONF_SSE_ID]}_refresh_data"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.data[CONF_SSE_ID]))},
            name=str(entry.data[CONF_SSE_NAME]),
            manufacturer="Elektroenergetické datové centrum, a. s.",
            model="Skupina sdílení elektřiny",
            configuration_url="https://portal.edc-cr.cz/sprava-dat/zobrazeni-dat",
        )

    async def async_press(self) -> None:
        """Request a refresh and surface a failed attempt to the user."""
        coordinator = self._entry.runtime_data.coordinator
        await coordinator.async_request_refresh()
        if coordinator.last_attempt_result != "success":
            raise HomeAssistantError(
                coordinator.last_attempt_error
                or "Stažení dat EDC se nezdařilo."
            )


class EdcHistoryBackfillButton(ButtonEntity):
    """Start discovery and import of all available EDC history."""

    _attr_has_entity_name = True
    _attr_translation_key = "backfill_history"
    _attr_icon = "mdi:database-clock-outline"

    def __init__(self, entry: EdcConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.data[CONF_SSE_ID]}_backfill_history"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.data[CONF_SSE_ID]))},
            name=str(entry.data[CONF_SSE_NAME]),
            manufacturer="Elektroenergetické datové centrum, a. s.",
            model="Skupina sdílení elektřiny",
            configuration_url="https://portal.edc-cr.cz/sprava-dat/zobrazeni-dat",
        )

    async def async_press(self) -> None:
        """Start or resume the one-time background history scan."""
        coordinator = self._entry.runtime_data.coordinator
        if not coordinator.async_start_history_backfill():
            raise HomeAssistantError(
                "Doplňování historie EDC již probíhá."
            )


class EdcDashboardButton(ButtonEntity):
    """Offer an authenticated configuration link, not an automatic dashboard write."""

    _attr_has_entity_name = True
    _attr_translation_key = "generate_dashboard"
    _attr_icon = "mdi:view-dashboard-plus-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: EdcConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.data[CONF_SSE_ID]}_generate_dashboard"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.data[CONF_SSE_ID]))},
            name=str(entry.data[CONF_SSE_NAME]),
            manufacturer="Elektroenergetické datové centrum, a. s.",
            model="Skupina sdílení elektřiny",
        )

    async def async_press(self) -> None:
        """A backend button cannot open a browser dialog; provide a safe link."""
        czech = self.hass.config.language.casefold().startswith("cs")
        url = f"/{PANEL_PATH}?entry_id={self._entry.entry_id}"
        persistent_notification.async_create(
            self.hass,
            (f"[Otevřít generátor dashboardu]({url})\n\nZadejte název a vyberte YAML "
             "nebo založení nového dashboardu. Existující dashboardy se nepřepisují.")
            if czech else (f"[Open the dashboard generator]({url})\n\nEnter a name and choose YAML "
                           "or create a new dashboard. Existing dashboards are never overwritten."),
            title="EDC – dashboard",
            notification_id=f"{DOMAIN}_dashboard_{self._entry.entry_id}",
        )
