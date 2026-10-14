"""Sdílené omezení čtecích požadavků EDC a sanitizované kategorie chyb."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime


class EdcApiError(Exception):
    """Bezpečná chyba; status/kategorie/termín slouží plánovači i diagnostice.

    Text musí vytvořit pouze integrace, nikdy vzdálená volná zpráva. Termín
    retry je UTC a nezkracuje serverový Retry-After. Staré volání s jediným
    textovým argumentem zůstává podporované.
    """

    def __init__(
        self,
        message: str,
        *,
        category: str = "unknown",
        status: int | None = None,
        retry_at: datetime | None = None,
        phase: str = "read",
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status = status
        self.retry_at = retry_at
        self.phase = phase


class EdcAuthenticationError(EdcApiError):
    """Potvrzené neplatné přihlášení; technická změna login stránky sem nepatří."""

    def __init__(self, message: str) -> None:
        super().__init__(message, category="authentication")


class EdcAccessExpiredError(EdcAuthenticationError):
    """401 čtecího API lze jednou obnovit; odmítnuté heslo se neopakuje."""


def classify_api_failure(status: int) -> str:
    """Kategorizovat HTTP bez hádání konkrétní příčiny validace."""
    if status in (400, 422):
        return "validation"
    if status == 401:
        return "authentication"
    if status == 403:
        return "permission"
    if status in (404, 405, 410):
        return "contract"
    if status == 429:
        return "rate_limit"
    if status >= 500:
        return "unavailable"
    return "unknown"


def retry_after(value: str | None, now: datetime) -> datetime | None:
    """Převést sekundy/HTTP datum do UTC; neplatný nebo minulý termín ignorovat.

    Záměrně není horní limit, který by zkrátil dlouhý serverový zákaz. Dlouhé
    čekání se ukládá a naplánuje, nedrží HTTP spojení ani spící úlohu.
    """
    if not isinstance(value, str) or len(value) > 128:
        return None
    try:
        if value.strip().isdigit():
            result = now + timedelta(seconds=int(value.strip()))
        else:
            result = parsedate_to_datetime(value)
            if result.tzinfo is None:
                result = result.replace(tzinfo=UTC)
            result = result.astimezone(UTC)
        return result if result > now else None
    except (OverflowError, TypeError, ValueError):
        return None


class ApiAccountState:
    """Jeden zámek a uložené čekání pro všechny skupiny stejného účtu.

    Omezení serveru/transportu platí pro celý účet. Odmítnutý profil blokuje
    danou skupinu a cestu, aby nevyřadil jiné platné skupiny. Klíče jsou hash,
    ukládají se jen termíny a bezpečné kategorie. Po restartu nejprve načíst
    stav, pak umožnit požadavek. Callback ukládání patří HA Store.
    """

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.loaded = False
        self.persistence_failed = False
        self.blocks: dict[str, tuple[datetime, str]] = {}
        self.deadlines: dict[str, float] = {}
        self.persist: Callable[[dict], Awaitable[None]] | None = None

    @staticmethod
    def scope(path: str, payload: dict | None) -> str:
        value = f"{path}|{payload.get('sseId') if payload else ''}"
        return hashlib.sha256(value.encode()).hexdigest()

    def restore(self, data: object) -> None:
        """Přijmout jen vlastní typy/kategorie; neobnovovat libovolné zprávy."""
        if not isinstance(data, dict):
            return
        allowed = {
            "validation",
            "permission",
            "contract",
            "rate_limit",
            "unavailable",
            "unknown",
            "user_action",
        }
        for key, value in data.items():
            if (
                not isinstance(key, str)
                or (
                    key != "account"
                    and (
                        len(key) != 64
                        or any(char not in "0123456789abcdef" for char in key)
                    )
                )
                or not isinstance(value, dict)
                or not isinstance(value.get("category"), str)
                or value.get("category") not in allowed
            ):
                continue
            try:
                until = datetime.fromisoformat(value["until"])
                if until.tzinfo is not None and until > datetime.now(UTC):
                    self.blocks[key] = (until.astimezone(UTC), value["category"])
                    self.deadlines[key] = (
                        time.monotonic() + (until - datetime.now(UTC)).total_seconds()
                    )
            except (KeyError, TypeError, ValueError, OverflowError):
                continue

    def check(self, scope: str) -> None:
        """Ruční načtení, report i backfill respektují stejný termín."""
        now = datetime.now(UTC)
        active = [
            (self.remaining(key, now), self.blocks[key][1])
            for key in ("account", scope)
            if key in self.blocks and self.remaining(key, now) > 0
        ]
        if active:
            seconds, category = max(active)
            until = now + timedelta(seconds=seconds)
            raise EdcApiError(
                f"Další pokus o EDC je povolen od {until.isoformat()}.",
                category=category,
                retry_at=until,
            )

    def remaining(self, key: str, now: datetime) -> float:
        """Posun systémových hodin nesmí předčasně ukončit běžící čekání."""
        return max(
            0,
            (self.blocks[key][0] - now).total_seconds(),
            self.deadlines.get(key, 0) - time.monotonic(),
        )

    async def block(
        self, scope: str, error: EdcApiError, server_until: datetime | None = None
    ) -> None:
        """Uložit čekání před vrácením chyby; případná delší stará lhůta platí."""
        now = datetime.now(UTC)
        seconds = (
            21600
            if error.category in ("contract", "permission", "user_action")
            else 3600
        )
        until = (
            server_until
            if server_until is not None and server_until > now
            else now + timedelta(seconds=seconds)
        )
        key = (
            "account"
            if error.category in ("rate_limit", "unavailable")
            or error.phase == "authentication"
            else scope
        )
        if key in self.blocks:
            until = max(until, now + timedelta(seconds=self.remaining(key, now)))
        self.blocks[key] = (until, error.category)
        self.deadlines[key] = time.monotonic() + (until - now).total_seconds()
        error.retry_at = until
        self.blocks = {
            key: (now + timedelta(seconds=self.remaining(key, now)), value[1])
            for key, value in self.blocks.items()
            if self.remaining(key, now) > 0
        }
        self.deadlines = {
            key: value for key, value in self.deadlines.items() if key in self.blocks
        }
        if self.persist is not None:
            try:
                await self.persist(
                    {
                        key: {"until": value[0].isoformat(), "category": value[1]}
                        for key, value in self.blocks.items()
                    }
                )
                self.persistence_failed = False
            except (OSError, RuntimeError):
                # Nezastřít původní HTTP status; paměťové čekání zůstává aktivní.
                self.persistence_failed = True
