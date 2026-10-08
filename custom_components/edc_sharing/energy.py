"""Deterministic, dated totals for the Energy dashboard."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from decimal import Decimal
from hashlib import sha256
from typing import Any

from .calculation import TargetDailySharing
from .const import CONF_ENERGY_TARGETS, DOMAIN
from .ean_settings import target_sale_price


def energy_targets(options: Mapping[str, Any]) -> tuple[str, ...]:
    """Opt in explicitly; never silently charge newly discovered EANs."""
    value = options.get(CONF_ENERGY_TARGETS, [])
    if not isinstance(value, list):
        return ()
    return tuple(sorted({item for item in value if isinstance(item, str) and item}))


def energy_statistic_id(
    sse_id: str | int, targets: tuple[str, ...], metric: str
) -> str:
    """Keep each selection separate, without exposing full EANs in IDs.

    Changing the selection creates a new series so older totals from previously
    selected targets cannot remain in the active series.
    """
    digest = sha256("\0".join(sorted(set(targets))).encode()).hexdigest()[:16]
    return f"{DOMAIN}:{sse_id}_energy_{digest}_{metric}"


def target_hourly_statistic_id(sse_id: str | int, ean: str, metric: str) -> str:
    """Scope new interval series to a group; never rename existing statistics."""
    clean_ean = ean.replace("-", "_").lower()
    return f"{DOMAIN}:{sse_id}_{clean_ean}_{metric}_hourly"


def daily_energy_values(
    rows: Mapping[str, Mapping[date, TargetDailySharing]],
    targets: tuple[str, ...],
    options: Mapping[str, Any],
    fallback_price: Decimal,
    today: date,
) -> dict[date, tuple[Decimal, Decimal]]:
    """Use cached aggregates and only dates present for every selected target."""
    if not targets or any(not rows.get(ean) for ean in targets):
        return {}
    days = set.intersection(*(set(rows[ean]) for ean in targets))
    result = {}
    for day in sorted(days):
        if day >= today:
            continue
        values = [rows[ean][day].shared for ean in targets]
        if any(not value.is_finite() or value < 0 for value in values):
            continue
        energy = sum(values, Decimal(0))
        revenue = sum(
            (
                rows[ean][day].shared * target_sale_price(ean, options, fallback_price)
                for ean in targets
            ),
            Decimal(0),
        )
        if revenue.is_finite() and revenue >= 0:
            result[day] = energy, revenue
    return result


def cumulative_daily_points(
    values: Mapping[date, Decimal], local_tz: tzinfo
) -> list[dict[str, Any]]:
    """Rebuild the full series; never append to a previously imported sum.

    This exporter uses daily target totals, not hourly profiles. Book the daily amount
    in the final real UTC hour of its local day; do not invent hourly earnings.
    A zero baseline in the preceding hour preserves the very first day's delta.
    """
    if not values:
        return []
    total = Decimal(0)
    first = datetime.combine(min(values), time.min, tzinfo=local_tz).astimezone(UTC)
    points = [{"start": first - timedelta(hours=1), "state": 0.0, "sum": 0.0}]
    for day, value in sorted(values.items()):
        start = datetime.combine(day, time.min, tzinfo=local_tz).astimezone(UTC)
        end = datetime.combine(
            day + timedelta(days=1), time.min, tzinfo=local_tz
        ).astimezone(UTC)
        points.append({"start": start, "state": float(total), "sum": float(total)})
        total += value
        points.append(
            {
                "start": end - timedelta(hours=1),
                "state": float(total),
                "sum": float(total),
            }
        )
    return points
