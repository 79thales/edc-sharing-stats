"""Pure calculation helpers for EDC profile data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class DailySharing:
    """Calculated values for one day."""

    day: date
    consumption: Decimal
    grid_purchase: Decimal
    shared: Decimal
    producer_overflow: Decimal
    used_overflow: Decimal
    unused_overflow: Decimal
    coverage: Decimal
    consistency_difference: Decimal


@dataclass(frozen=True, slots=True)
class SharingStatistics:
    """Statistics exposed by the integration."""

    days: tuple[DailySharing, ...]
    today: DailySharing
    month_consumption: Decimal
    month_grid_purchase: Decimal
    month_shared: Decimal
    month_overflow: Decimal
    month_unused: Decimal
    month_coverage: Decimal
    month_revenue: Decimal
    today_revenue: Decimal
    sale_price: Decimal


def _decimal(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value))


def calculate_profile(response: dict[str, Any], sale_price: Decimal, today: date) -> SharingStatistics:
    """Calculate sharing from the standard profile overview response."""
    columns = response.get("valueColumns") or []
    content = response.get("content") or []
    if not columns or not content:
        raise ValueError("EDC nevrátilo profilová data.")

    producers: dict[str, dict[str, int]] = {}
    consumers: dict[str, dict[str, int]] = {}
    for index, column in enumerate(columns):
        ean = str(column.get("ean", ""))
        direction = str(column.get("dir", "")).upper()
        role = str(column.get("type", "")).upper()
        target = producers if role == "D" else consumers if role == "O" else None
        if target is not None and direction in ("IN", "OUT"):
            target.setdefault(ean, {})[direction] = index
    if not producers or not consumers:
        raise ValueError("V odpovědi EDC nebyl rozpoznán výrobní a odběrný EAN.")

    daily: list[DailySharing] = []
    for item in content:
        item_date = date.fromisoformat(str(item["date"])[:10])
        values = item.get("values") or []

        def value(index: int | None) -> Decimal:
            if index is None or index >= len(values):
                return ZERO
            raw = values[index]
            return _decimal(raw.get("v") if isinstance(raw, dict) else raw)

        producer_in = sum((value(pair.get("IN")) for pair in producers.values()), ZERO)
        producer_out = sum((value(pair.get("OUT")) for pair in producers.values()), ZERO)
        consumer_in = sum((abs(value(pair.get("IN"))) for pair in consumers.values()), ZERO)
        consumer_out = sum((abs(value(pair.get("OUT"))) for pair in consumers.values()), ZERO)
        shared_consumer = consumer_in - consumer_out
        shared_producer = producer_in - producer_out
        coverage = shared_consumer / consumer_in * Decimal("100") if consumer_in else ZERO
        daily.append(
            DailySharing(
                day=item_date,
                consumption=consumer_in,
                grid_purchase=consumer_out,
                shared=shared_consumer,
                producer_overflow=producer_in,
                used_overflow=shared_producer,
                unused_overflow=producer_out,
                coverage=coverage,
                consistency_difference=abs(shared_consumer - shared_producer),
            )
        )

    daily.sort(key=lambda row: row.day)
    empty_today = DailySharing(today, ZERO, ZERO, ZERO, ZERO, ZERO, ZERO, ZERO, ZERO)
    today_row = next((row for row in daily if row.day == today), empty_today)
    month_rows = [row for row in daily if row.day.year == today.year and row.day.month == today.month]
    month_consumption = sum((row.consumption for row in month_rows), ZERO)
    month_shared = sum((row.shared for row in month_rows), ZERO)
    month_coverage = month_shared / month_consumption * Decimal("100") if month_consumption else ZERO
    return SharingStatistics(
        days=tuple(daily),
        today=today_row,
        month_consumption=month_consumption,
        month_grid_purchase=sum((row.grid_purchase for row in month_rows), ZERO),
        month_shared=month_shared,
        month_overflow=sum((row.producer_overflow for row in month_rows), ZERO),
        month_unused=sum((row.unused_overflow for row in month_rows), ZERO),
        month_coverage=month_coverage,
        month_revenue=month_shared * sale_price,
        today_revenue=today_row.shared * sale_price,
        sale_price=sale_price,
    )
