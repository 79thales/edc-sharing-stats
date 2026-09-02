"""Import EDC daily and hourly history into long-term statistics."""

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

from .calculation import DailySharing, HourlySharing
from .const import DOMAIN


@dataclass(frozen=True, slots=True)
class HistorySeries:
    """Description of one imported sharing statistic."""

    key: str
    name_cs: str
    name_en: str
    unit: str
    unit_class: str | None
    value_fn: Callable[[DailySharing | HourlySharing, Decimal], Decimal]


HISTORY_SERIES: tuple[HistorySeries, ...] = (
    HistorySeries(
        "shared",
        "Nasdíleno",
        "Shared",
        UnitOfEnergy.KILO_WATT_HOUR,
        EnergyConverter.UNIT_CLASS,
        lambda row, _price: row.shared,
    ),
    HistorySeries(
        "consumption",
        "Spotřeba",
        "Consumption",
        UnitOfEnergy.KILO_WATT_HOUR,
        EnergyConverter.UNIT_CLASS,
        lambda row, _price: row.consumption,
    ),
    HistorySeries(
        "grid",
        "Dokup ze sítě",
        "Grid purchase",
        UnitOfEnergy.KILO_WATT_HOUR,
        EnergyConverter.UNIT_CLASS,
        lambda row, _price: row.grid_purchase,
    ),
    HistorySeries(
        "unused",
        "Nevyužitý přetok",
        "Unused surplus",
        UnitOfEnergy.KILO_WATT_HOUR,
        EnergyConverter.UNIT_CLASS,
        lambda row, _price: row.unused_overflow,
    ),
    HistorySeries(
        "coverage",
        "Pokrytí sdílením",
        "Sharing coverage",
        PERCENTAGE,
        UnitlessRatioConverter.UNIT_CLASS,
        lambda row, _price: row.coverage,
    ),
    HistorySeries(
        "revenue",
        "Tržba",
        "Revenue",
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
            name=(
                f"{sse_name} – {series.name_cs if czech else series.name_en} – "
                f"{'denní historie' if czech else 'daily history'}"
            ),
            source=DOMAIN,
            statistic_id=f"{DOMAIN}:{sse_id}_{series.key}_daily",
            unit_class=series.unit_class,
            unit_of_measurement=series.unit,
        )
        async_add_external_statistics(hass, metadata, statistics)
    return len(finalized)


@callback
def async_import_hourly_history(
    hass: HomeAssistant,
    *,
    sse_id: int,
    sse_name: str,
    hours: tuple[HourlySharing, ...],
    sale_price: Decimal,
    now: datetime,
    local_tz: tzinfo,
) -> int:
    """Queue completed EDC hours as idempotent external statistics."""
    current_hour = now.replace(tzinfo=None, minute=0, second=0, microsecond=0)
    finalized = tuple(row for row in hours if row.start < current_hour)
    if not finalized:
        return 0

    czech = hass.config.language.casefold().startswith("cs")
    for series in HISTORY_SERIES:
        statistics: list[StatisticData] = []
        for row in finalized:
            value = float(series.value_fn(row, sale_price))
            statistics.append(
                StatisticData(
                    start=row.start.replace(tzinfo=local_tz),
                    mean=value,
                    min=value,
                    max=value,
                )
            )
        metadata = StatisticMetaData(
            mean_type=StatisticMeanType.ARITHMETIC,
            has_sum=False,
            name=(
                f"{sse_name} – {series.name_cs if czech else series.name_en} – "
                f"{'hodinová historie' if czech else 'hourly history'}"
            ),
            source=DOMAIN,
            statistic_id=f"{DOMAIN}:{sse_id}_{series.key}_hourly",
            unit_class=series.unit_class,
            unit_of_measurement=series.unit,
        )
        async_add_external_statistics(hass, metadata, statistics)
    return len(finalized)
