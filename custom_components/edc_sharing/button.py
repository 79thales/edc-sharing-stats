"""Buttons for sending EDC reports on demand."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EdcConfigEntry
from .const import CONF_SSE_ID, CONF_SSE_NAME, DOMAIN
from .coordinator import EdcSharingCoordinator
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
    """Set up report buttons."""
    async_add_entities(EdcReportButton(entry, description) for description in BUTTONS)


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
