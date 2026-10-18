"""Výběr aktuální revize EDC a anonymní diagnostika kvality profilů.

CURRENT je místní název režimu portálu, nikoli hodnota calculationType.
Čas snímku je UTC okamžik výběru revize; kalendářní meze zůstávají místní.
"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps

_PROFILE_AS_OF: ContextVar[tuple[object, datetime] | None] = ContextVar("edc_profile_as_of", default=None)


def profile_as_of() -> datetime:
    """Vrátit jeden UTC snímek průchodu, mimo průchod skutečný aktuální čas."""
    try:
        owner = asyncio.current_task()
    except RuntimeError:
        owner = None
    snapshot = _PROFILE_AS_OF.get()
    # Nová background task dědí ContextVar, ale musí mít vlastní snímek;
    # jinak by po čekání na zámek mohla načíst starší revizi než rodič.
    return snapshot[1] if snapshot is not None and snapshot[0] is owner else datetime.now(UTC)


def profile_read_snapshot(method):
    """Sdílet okamžik revize v asynchronním průchodu i jeho vnořených čteních.

    ContextVar odděluje souběžné úlohy a finally obnoví kontext také při chybě
    nebo zrušení. Dekorátor nepřihlašuje, nečte API a neobchází account lock.
    """
    @wraps(method)
    async def wrapped(*args, **kwargs):
        token = _PROFILE_AS_OF.set((asyncio.current_task(), profile_as_of()))
        try:
            return await method(*args, **kwargs)
        finally:
            _PROFILE_AS_OF.reset(token)
    return wrapped


def profile_quality(response: dict) -> dict:
    """Počítat kvalitu buněk měření, nikoli tvrdit konečnost celého měsíce.

    Portál čte values[].q; chybějící/neznámé kódy mají vlastní počítadlo.
    Jmenovatel je počet buněk všech EANů/směrů, ne počet časových intervalů.
    Nevracíme identity ani hodnoty kWh; Z46 není důkaz typu kalkulace.
    """
    counts = {key: 0 for key in ("Z46", "Z66", "Z99", "unknown")}
    for row in response.get("content", []):
        for value in row.get("values", []):
            quality = value.get("q") if isinstance(value, dict) else None
            counts[quality if isinstance(quality, str) and quality in counts else "unknown"] += 1
    total = sum(counts.values())
    return {"requested_selection": "CURRENT", "actual_calculation_type": "unknown",
            "quality_basis": "measurement_cells", "quality_counts": counts,
            "quality_cells": total,
            "provisional_quality_percent": (100 * (counts["Z66"] + counts["Z99"]) / total
                                            if total else None)}
