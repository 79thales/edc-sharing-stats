"""Sensors for EDC electricity sharing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import EntityCategory, PERCENTAGE, Platform, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EdcConfigEntry
from .calculation import EanInfo, SharingStatistics
from .const import CONF_SSE_ID, CONF_SSE_NAME, DOMAIN
from .coordinator import EdcSharingCoordinator


@dataclass(frozen=True, kw_only=True)
class EdcSensorDescription(SensorEntityDescription):
    value_fn: Callable[[SharingStatistics], Decimal]
    attributes_fn: Callable[[SharingStatistics], dict[str, Any]] | None = None


ENERGY_TOTAL = dict(
    device_class=SensorDeviceClass.ENERGY,
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    state_class=SensorStateClass.TOTAL,
    suggested_display_precision=2,
)


def _latest_attributes(statistics: SharingStatistics) -> dict[str, Any]:
    """Describe which delayed EDC day is represented by the current value."""
    return {
        "data_date": statistics.latest_day.isoformat()
        if statistics.latest_day is not None
        else None
    }


SENSORS: tuple[EdcSensorDescription, ...] = (
    EdcSensorDescription(key="shared_today", translation_key="shared_today", value_fn=lambda x: x.latest.shared, attributes_fn=_latest_attributes, **ENERGY_TOTAL),
    EdcSensorDescription(key="consumption_today", translation_key="consumption_today", value_fn=lambda x: x.latest.consumption, attributes_fn=_latest_attributes, **ENERGY_TOTAL),
    EdcSensorDescription(key="grid_today", translation_key="grid_today", value_fn=lambda x: x.latest.grid_purchase, attributes_fn=_latest_attributes, **ENERGY_TOTAL),
    EdcSensorDescription(key="unused_today", translation_key="unused_today", value_fn=lambda x: x.latest.unused_overflow, attributes_fn=_latest_attributes, **ENERGY_TOTAL),
    EdcSensorDescription(
        key="coverage_today", translation_key="coverage_today", value_fn=lambda x: x.latest.coverage,
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
        attributes_fn=_latest_attributes,
    ),
    EdcSensorDescription(
        key="revenue_today", translation_key="revenue_today", value_fn=lambda x: x.latest.shared * x.sale_price,
        device_class=SensorDeviceClass.MONETARY, native_unit_of_measurement="CZK", state_class=SensorStateClass.TOTAL, suggested_display_precision=2,
        attributes_fn=_latest_attributes,
    ),
    EdcSensorDescription(key="shared_month", translation_key="shared_month", value_fn=lambda x: x.month_shared, **ENERGY_TOTAL),
    EdcSensorDescription(key="consumption_month", translation_key="consumption_month", value_fn=lambda x: x.month_consumption, **ENERGY_TOTAL),
    EdcSensorDescription(key="grid_month", translation_key="grid_month", value_fn=lambda x: x.month_grid_purchase, **ENERGY_TOTAL),
    EdcSensorDescription(key="overflow_month", translation_key="overflow_month", value_fn=lambda x: x.month_overflow, **ENERGY_TOTAL),
    EdcSensorDescription(key="unused_month", translation_key="unused_month", value_fn=lambda x: x.month_unused, **ENERGY_TOTAL),
    EdcSensorDescription(
        key="coverage_month", translation_key="coverage_month", value_fn=lambda x: x.month_coverage,
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
    ),
    EdcSensorDescription(
        key="production_profit_month", translation_key="production_profit_month", value_fn=lambda x: x.month_revenue,
        device_class=SensorDeviceClass.MONETARY, native_unit_of_measurement="CZK", state_class=SensorStateClass.TOTAL, suggested_display_precision=2,
        attributes_fn=lambda x: {"sale_price_czk_per_kwh": float(x.sale_price)},
    ),
    EdcSensorDescription(
        key="sale_price", translation_key="sale_price", value_fn=lambda x: x.sale_price,
        native_unit_of_measurement="CZK/kWh", state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=2,
    ),
)

HISTORY_KEYS: dict[str, str] = {
    "shared_today": "shared",
    "consumption_today": "consumption",
    "grid_today": "grid",
    "unused_today": "unused",
    "coverage_today": "coverage",
    "revenue_today": "revenue",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EdcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up all EDC sensors."""
    await _async_refresh_existing_entity_names(hass, entry)
    async_add_entities(
        [EdcSharingSensor(entry, description) for description in SENSORS]
        + [EdcUpdateAttemptSensor(entry)]
    )
    known_eans: set[tuple[str, str]] = set()

    @callback
    def async_add_new_eans() -> None:
        new_eans = [
            ean_info
            for ean_info in entry.runtime_data.coordinator.eans
            if (ean_info.role, ean_info.ean) not in known_eans
        ]
        if not new_eans:
            return
        known_eans.update((item.role, item.ean) for item in new_eans)
        async_add_entities([EdcEanSensor(entry, item) for item in new_eans])

    async_add_new_eans()
    entry.async_on_unload(
        entry.runtime_data.coordinator.async_add_listener(async_add_new_eans)
    )


async def _async_refresh_existing_entity_names(
    hass: HomeAssistant, entry: EdcConfigEntry
) -> None:
    """Replace generic legacy names without touching user customizations."""
    translations = await async_get_translations(
        hass, hass.config.language, "entity", {DOMAIN}
    )
    registry = er.async_get(hass)
    for description in SENSORS:
        entity_id = registry.async_get_entity_id(
            Platform.SENSOR,
            DOMAIN,
            f"{entry.data[CONF_SSE_ID]}_{description.key}",
        )
        if entity_id is None:
            continue
        registry_entry = registry.async_get(entity_id)
        if registry_entry is None or registry_entry.name is not None:
            continue
        name = translations.get(
            f"component.{DOMAIN}.entity.sensor.{description.translation_key}.name"
        )
        if name and registry_entry.original_name != name:
            registry.async_update_entity(entity_id, original_name=name)


class EdcSharingSensor(CoordinatorEntity[EdcSharingCoordinator], SensorEntity):
    """One calculated EDC sensor."""

    _attr_has_entity_name = True

    def __init__(self, entry: EdcConfigEntry, description: EdcSensorDescription) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.data[CONF_SSE_ID]}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.data[CONF_SSE_ID]))},
            name=str(entry.data[CONF_SSE_NAME]),
            manufacturer="Elektroenergetické datové centrum, a. s.",
            model="Skupina sdílení elektřiny",
            configuration_url="https://portal.edc-cr.cz/sprava-dat/zobrazeni-dat",
        )

    @property
    def native_value(self) -> Decimal:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        attributes = (
            self.entity_description.attributes_fn(self.coordinator.data)
            if self.entity_description.attributes_fn is not None
            else {}
        )
        history_key = HISTORY_KEYS.get(self.entity_description.key)
        if history_key is not None:
            sse_id = self.coordinator.config_entry.data[CONF_SSE_ID]
            attributes.update(
                {
                    "daily_statistic_id": f"{DOMAIN}:{sse_id}_{history_key}_daily",
                    "hourly_statistic_id": f"{DOMAIN}:{sse_id}_{history_key}_hourly",
                }
            )
        return attributes or None


class EdcEanSensor(CoordinatorEntity[EdcSharingCoordinator], SensorEntity):
    """Diagnostic entity representing one EAN in the sharing group."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: EdcConfigEntry, ean_info: EanInfo) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._ean_info = ean_info
        self._attr_unique_id = (
            f"{entry.data[CONF_SSE_ID]}_{ean_info.role}_ean_{ean_info.ean}"
        )
        self._attr_translation_key = f"{ean_info.role}_ean"
        self._attr_translation_placeholders = {"ean": ean_info.ean}
        self._attr_icon = (
            "mdi:transmission-tower-export"
            if ean_info.role == "sharing"
            else "mdi:transmission-tower-import"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.data[CONF_SSE_ID]))},
            name=str(entry.data[CONF_SSE_NAME]),
            manufacturer="Elektroenergetické datové centrum, a. s.",
            model="Skupina sdílení elektřiny",
            configuration_url="https://portal.edc-cr.cz/sprava-dat/zobrazeni-dat",
        )

    @property
    def native_value(self) -> str:
        """Return the complete EAN without numeric conversion."""
        return self._ean_info.ean

    @property
    def available(self) -> bool:
        """Mark an EAN unavailable if EDC removes it from the group."""
        return super().available and self._ean_info in self.coordinator.eans

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Expose a stable machine-readable role."""
        return {"role": self._ean_info.role}


class EdcUpdateAttemptSensor(
    CoordinatorEntity[EdcSharingCoordinator], SensorEntity
):
    """Show when EDC data were last requested and when retry is expected."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "last_update_attempt"

    def __init__(self, entry: EdcConfigEntry) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.data[CONF_SSE_ID]}_last_update_attempt"
        self._attr_icon = "mdi:cloud-clock-outline"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.data[CONF_SSE_ID]))},
            name=str(entry.data[CONF_SSE_NAME]),
            manufacturer="Elektroenergetické datové centrum, a. s.",
            model="Skupina sdílení elektřiny",
            configuration_url="https://portal.edc-cr.cz/sprava-dat/zobrazeni-dat",
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the most recent attempt."""
        return self.coordinator.last_attempt_at

    @property
    def available(self) -> bool:
        """Keep diagnostics visible after a failed coordinator update."""
        return self.coordinator.last_attempt_at is not None

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        """Expose regular updates and full-history backfill progress."""
        total_chunks = self.coordinator.history_backfill_total_chunks
        processed_chunks = self.coordinator.history_backfill_processed_chunks
        progress = (
            round(processed_chunks / total_chunks * 100)
            if total_chunks
            else 0
        )
        return {
            "result": self.coordinator.last_attempt_result,
            "last_success": self.coordinator.last_success_at.isoformat()
            if self.coordinator.last_success_at is not None
            else None,
            "next_attempt": self.coordinator.next_attempt_at.isoformat()
            if self.coordinator.next_attempt_at is not None
            else None,
            "error": self.coordinator.last_attempt_error,
            "history_backfill_status": self.coordinator.history_backfill_status,
            "history_backfill_progress": progress,
            "history_backfill_processed_chunks": processed_chunks,
            "history_backfill_total_chunks": total_chunks,
            "history_backfill_scanned_to": (
                self.coordinator.history_backfill_cursor.isoformat()
                if self.coordinator.history_backfill_cursor is not None
                else None
            ),
            "history_earliest_data": (
                self.coordinator.history_earliest_date.isoformat()
                if self.coordinator.history_earliest_date is not None
                else None
            ),
            "history_backfill_imported_days": (
                self.coordinator.history_backfill_imported_days
            ),
            "history_backfill_imported_hours": (
                self.coordinator.history_backfill_imported_hours
            ),
            "history_backfill_started": (
                self.coordinator.history_backfill_started_at.isoformat()
                if self.coordinator.history_backfill_started_at is not None
                else None
            ),
            "history_backfill_completed": (
                self.coordinator.history_backfill_completed_at.isoformat()
                if self.coordinator.history_backfill_completed_at is not None
                else None
            ),
            "history_backfill_error": self.coordinator.history_backfill_error,
        }
