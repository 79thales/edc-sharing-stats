"""Sensors for EDC electricity sharing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, Platform, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EdcConfigEntry
from .calculation import SharingStatistics
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

SENSORS: tuple[EdcSensorDescription, ...] = (
    EdcSensorDescription(key="shared_today", translation_key="shared_today", value_fn=lambda x: x.today.shared, **ENERGY_TOTAL),
    EdcSensorDescription(key="consumption_today", translation_key="consumption_today", value_fn=lambda x: x.today.consumption, **ENERGY_TOTAL),
    EdcSensorDescription(key="grid_today", translation_key="grid_today", value_fn=lambda x: x.today.grid_purchase, **ENERGY_TOTAL),
    EdcSensorDescription(key="unused_today", translation_key="unused_today", value_fn=lambda x: x.today.unused_overflow, **ENERGY_TOTAL),
    EdcSensorDescription(
        key="coverage_today", translation_key="coverage_today", value_fn=lambda x: x.today.coverage,
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
    ),
    EdcSensorDescription(
        key="revenue_today", translation_key="revenue_today", value_fn=lambda x: x.today_revenue,
        device_class=SensorDeviceClass.MONETARY, native_unit_of_measurement="CZK", state_class=SensorStateClass.TOTAL, suggested_display_precision=2,
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EdcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up all EDC sensors."""
    await _async_refresh_existing_entity_names(hass, entry)
    async_add_entities(EdcSharingSensor(entry, description) for description in SENSORS)


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
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
