"""Import EDC daily history into Home Assistant long-term statistics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, tzinfo
from decimal import Decimal

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.const import PERCENTAGE, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.util.unit_conversion import EnergyConverter, UnitlessRatioConverter

from .calculation import DailySharing
from .const import DOMAIN


@dataclass(frozen=True, slots=True)
class HistorySeries:
    """Description of one imported daily statistic."""

    key: str
    name_cs: str
    name_en: str
    unit: str
    unit_class: str | None
    value_fn: Callable[[DailySharing, Decimal], Decimal]


HISTORY_SERIES: tuple[HistorySeries, ...] = (
    HistorySeries(
        "shared_daily",
        "Nasdíleno – denní historie",
        "Shared – daily history",
        UnitOfEnergy.KILO_WATT_HOUR,
        EnergyConverter.UNIT_CLASS,
        lambda row, _price: row.shared,
    ),
    HistorySeries(
        "consumption_daily",
        "Spotřeba – denní historie",
        "Consumption – daily history",
        UnitOfEnergy.KILO_WATT_HOUR,
        EnergyConverter.UNIT_CLASS,
        lambda row, _price: row.consumption,
    ),
    HistorySeries(
        "grid_daily",
        "Dokup ze sítě – denní historie",
        "Grid purchase – daily history",
        UnitOfEnergy.KILO_WATT_HOUR,
        EnergyConverter.UNIT_CLASS,
        lambda row, _price: row.grid_purchase,
    ),
    HistorySeries(
        "unused_daily",
        "Nevyužitý přetok – denní historie",
        "Unused surplus – daily history",
        UnitOfEnergy.KILO_WATT_HOUR,
        EnergyConverter.UNIT_CLASS,
        lambda row, _price: row.unused_overflow,
    ),
    HistorySeries(
        "coverage_daily",
        "Pokrytí sdílením – denní historie",
        "Sharing coverage – daily history",
        PERCENTAGE,
        UnitlessRatioConverter.UNIT_CLASS,
        lambda row, _price: row.coverage,
    ),
    HistorySeries(
        "revenue_daily",
        "Tržba – denní historie",
        "Revenue – daily history",
        "CZK",
        None,
        lambda row, price: row.shared * price,
    ),
)


@callback
def async_import_daily_history(
    hass: HomeAssistant,
    *,
    sse_id: int,
    sse_name: str,
    days: tuple[DailySharing, ...],
    sale_price: Decimal,
    today: date,
    local_tz: tzinfo,
) -> int:
    """Queue finalized EDC days as idempotent external statistics."""
    finalized = tuple(row for row in days if row.day < today)
    if not finalized:
        return 0

    czech = hass.config.language.casefold().startswith("cs")
    for series in HISTORY_SERIES:
        statistics: list[StatisticData] = []
        for row in finalized:
            value = float(series.value_fn(row, sale_price))
            statistics.append(
                StatisticData(
                    start=datetime.combine(row.day, time.min, tzinfo=local_tz),
                    mean=value,
                    min=value,
                    max=value,
                )
            )
        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.ARITHMETIC,
            has_sum=False,
            name=f"{sse_name} – {series.name_cs if czech else series.name_en}",
            source=DOMAIN,
            statistic_id=f"{DOMAIN}:{sse_id}_{series.key}",
            unit_class=series.unit_class,
            unit_of_measurement=series.unit,
        )
        async_add_external_statistics(hass, metadata, statistics)
    return len(finalized)
