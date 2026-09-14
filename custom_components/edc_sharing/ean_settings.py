"""Safe access to optional, user-defined EAN metadata."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from .const import CONF_EAN_SETTINGS


def _text(value: object, *, maximum: int = 120) -> str:
    """Return a compact user label, or an empty value when it is unusable."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:maximum]


def _price(value: object) -> Decimal | None:
    """Parse a non-negative finite per-EAN price without leaking bad options."""
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def configured_ean_settings(options: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return normalized EAN metadata from an options entry.

    Unknown fields are deliberately ignored here. This keeps runtime behavior
    safe when an older or manually edited options entry is encountered.
    """
    raw_settings = options.get(CONF_EAN_SETTINGS, {})
    if not isinstance(raw_settings, Mapping):
        return {}

    settings: dict[str, dict[str, Any]] = {}
    for raw_ean, raw_value in raw_settings.items():
        ean = _text(raw_ean, maximum=32)
        if not ean or not isinstance(raw_value, Mapping):
            continue
        item: dict[str, Any] = {}
        if name := _text(raw_value.get("name")):
            item["name"] = name
        if location := _text(raw_value.get("location")):
            item["location"] = location
        if (price := _price(raw_value.get("price"))) is not None:
            item["price"] = price
        if item:
            settings[ean] = item
    return settings


def ean_name(ean: str, options: Mapping[str, Any]) -> str:
    """Return the configured friendly name, falling back to the EAN itself."""
    return str(configured_ean_settings(options).get(ean, {}).get("name") or ean)


def ean_location(ean: str, options: Mapping[str, Any]) -> str | None:
    """Return an optional user-defined location."""
    location = configured_ean_settings(options).get(ean, {}).get("location")
    return str(location) if location else None


def target_sale_price(
    ean: str, options: Mapping[str, Any], fallback: Decimal
) -> Decimal:
    """Return a target-specific price, or preserve the existing group price."""
    price = configured_ean_settings(options).get(ean, {}).get("price")
    return price if isinstance(price, Decimal) else fallback
