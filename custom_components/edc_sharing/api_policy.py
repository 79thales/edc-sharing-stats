"""Sdílené omezení čtecích požadavků EDC a sanitizované kategorie chyb."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

_LOGGER = logging.getLogger(__name__)
# Výhradně vlastní pevné texty: nikdy neukládat vzdálenou zprávu, payload,
# URL s tokenem, EAN nebo heslo. Kód zůstává čitelný i po změně překladu.
FAILURE_REASONS = {
    "profile_lists": "EDC změnilo strukturu profilových seznamů.",
    "profile_column": "EDC vrátilo neplatný popis sloupce.",
    "profile_unit": "EDC změnilo jednotku profilových hodnot.",
    "profile_identity": "EDC změnilo identifikaci nebo role sloupců.",
    "profile_duplicate": "EDC vrátilo duplicitní sloupec.",
    "profile_directions": "EDC vrátilo neúplné směry měření.",
    "profile_description": "EDC nevrátilo popis profilových dat.",
    "profile_rows": "EDC změnilo strukturu časových řádků.",
    "profile_date": "EDC vrátilo neplatný den profilu.",
    "profile_vector": "EDC vrátilo neúplný vektor hodnot.",
    "profile_missing": "EDC vrátilo chybějící měřenou hodnotu.",
    "profile_infinite": "EDC vrátilo nekonečnou měřenou hodnotu.",
    "profile_number": "EDC vrátilo neplatnou číselnou hodnotu.",
    "profile_resolution": "EDC vrátilo nerozpoznané časové rozlišení.",
    "profile_range": "EDC vrátilo data mimo požadovaný interval.",
    "profile_calculation": "EDC profil nelze bezpečně spočítat.",
    "credentials": "Neplatné jméno nebo heslo EDC.",
    "access_expired": "Platnost přihlášení EDC skončila.",
    "groups": "EDC vrátilo neplatný seznam skupin.",
    "json": "EDC vrátilo neplatnou JSON odpověď.",
    "read_target": "EDC změnilo adresu čtecího API.",
    "login_target": "EDC změnilo cíl přihlašování.",
    "login_state": "EDC vrátilo neplatný stav přihlášení.",
    "login_form": "Přihlašovací stránka EDC neobsahuje adresu loginAction.",
    "login_redirect": "EDC přihlášení nedokončilo přesměrováním.",
    "login_manual": "Přihlášení EDC vyžaduje ruční ověření MFA/CAPTCHA.",
    "login_transport": "Spojení s přihlášením EDC selhalo.",
    "token_transport": "Obnova přihlášení EDC selhala.",
    "token": "EDC vrátilo neplatnou tokenovou odpověď.",
    "transport": "Spojení s EDC selhalo.",
    "http": "EDC odmítlo HTTP požadavek.",
    "unknown": "Konkrétní důvod není dostupný; viz bezpečná kategorie a HTTP status.",
    "legacy": "Starší verze neuložila konkrétní důvod ani původ čekání.",
}
_CATEGORIES = frozenset(
    {
        "validation",
        "permission",
        "contract",
        "rate_limit",
        "unavailable",
        "unknown",
        "user_action",
        "authentication",
    }
)
_PHASES = frozenset({"read", "authentication", "profile_validation"})
SAFE_ERROR_CODES = frozenset(
    {
        "INVALID_DATE",
        "INVALID_ENTERED_DATE",
        "MAX_PERIOD_RANGE",
        "MAX_PERIOD_RANGE_FOR_EXPORT",
        "MISSING_DATA_FOR_PERIOD",
        "NOT_EMPTY",
        "NOT_FOUND",
        "MAX_LENGTH",
        "MIN_LENGTH",
        "NUMBER_BETWEEN",
        "INTERNAL_ERROR",
        "TIME_INTERVAL_EXCEEDS_LIMIT",
        "PRODUCER_IS_NOT_VALID_WHOLE_PERIOD",
    }
)
SAFE_ERROR_FIELDS = frozenset(
    {
        "sseId",
        "eans",
        "dateFrom",
        "dateTo",
        "calculationType",
        "inputData",
        "outputData",
        "fileName",
        "currentEnteredDateTime",
    }
)


def _safe_details(value: object) -> str:
    """Zachovat jen známé validační kódy/pole, nikoli hodnoty nebo volný text."""
    if not isinstance(value, str) or len(value) > 1024:
        return ""
    parts = value.split("; ")
    if len(parts) > 5:
        return ""
    for part in parts:
        match = re.fullmatch(r"([A-Z_]+)(?: \(([A-Za-z]+)\))?", part)
        if (
            match is None
            or match[1] not in SAFE_ERROR_CODES
            or (match[2] and match[2] not in SAFE_ERROR_FIELDS)
        ):
            return ""
    return value


def _safe_context(value: object) -> str:
    """Povolit pouze vlastní čtecí endpoint a platná kalendářní data bez ID."""
    if not isinstance(value, str):
        return ""
    match = re.fullmatch(
        r" \((?:GET|POST) /profiles-data/(?:get-sse|standard/overview)\)(?:; období (\d{4}-\d{2}-\d{2}) až (\d{4}-\d{2}-\d{2}))?",
        value,
    )
    if match is None:
        return ""
    try:
        for bound in match.groups():
            if bound is not None:
                datetime.fromisoformat(bound)
    except ValueError:
        return ""
    return value


def safe_failure_record(error: EdcApiError) -> dict:
    """Vytvořit whitelist pro log, Store a sdílitelnou diagnostiku.

    Vstup může obsahovat libovolný text výjimky, výstup pouze pevný kód/text,
    kategorii, fázi a celočíselný HTTP status. Termíny doplní účetní politika.
    """
    code = next(
        (key for key, value in FAILURE_REASONS.items() if value == str(error)),
        "unknown",
    )
    if code == "unknown" and type(error.status) is int and 300 <= error.status <= 599:
        code = "http"
    return {
        "reason_code": code,
        "reason": FAILURE_REASONS[code],
        "category": error.category if error.category in _CATEGORIES else "unknown",
        "phase": error.phase if error.phase in _PHASES else "read",
        "http_status": error.status
        if type(error.status) is int and 100 <= error.status <= 599
        else None,
        "request_context": _safe_context(error.request_context),
        "validation_details": _safe_details(error.validation_details),
    }


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
        waiting: bool = False,
        request_context: str = "",
        validation_details: str = "",
    ) -> None:
        super().__init__(message)
        self.category = category
        self.status = status
        self.retry_at = retry_at
        self.phase = phase
        self.waiting = waiting
        self.request_context = request_context
        self.validation_details = validation_details


class EdcAuthenticationError(EdcApiError):
    """Potvrzené neplatné přihlášení; technická změna login stránky sem nepatří."""

    def __init__(self, message: str) -> None:
        super().__init__(message, category="authentication", phase="authentication")


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
    danou skupinu a cestu, aby nevyřadil jiné platné skupiny. Lokální validace
    odpovědi má navíc přesný rozsah dat a patnáctiminutovou ochranu. Klíče jsou
    hash; ukládají se termíny, kódy příčin, statusy a whitelisted kontext bez
    identit. Po restartu nejprve načíst stav, pak umožnit požadavek. Callback
    ukládání patří HA Store. Neznámý původ staré lhůty se nesmí domýšlet.
    """

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.loaded = False
        self.persistence_failed = False
        self.blocks: dict[str, tuple[datetime, str]] = {}
        self.deadlines: dict[str, float] = {}
        self.persist: Callable[[dict], Awaitable[None]] | None = None
        self.failures: dict[str, dict] = {}
        self.last_failure: dict | None = None
        self._legacy_logged: set[str] = set()

    @staticmethod
    def scope(path: str, payload: dict | None, *, period: bool = False) -> str:
        value = f"{path}|{payload.get('sseId') if payload else ''}"
        if period and payload:
            # Lokální odmítnutí schématu jednoho období neblokuje ostatní
            # období. HTTP omezení serveru má nadále původní širší klíč.
            value += f"|{payload.get('dateFrom')}|{payload.get('dateTo')}|validation"
        return hashlib.sha256(value.encode()).hexdigest()

    def diagnostic_failure(self) -> dict | None:
        """Vrátit nezávislý whitelist posledního důvodu, bez interních klíčů."""
        return self._restore_failure(self.last_failure)

    @staticmethod
    def _restore_failure(value: object) -> dict | None:
        """Z diskového záznamu obnovit jen whitelist; jeho volný text ignorovat."""
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("category"), str)
            or value.get("category") not in _CATEGORIES
        ):
            return None
        code = value.get("reason_code")
        code = code if isinstance(code, str) and code in FAILURE_REASONS else "legacy"
        phase = value.get("phase")
        status = value.get("http_status")
        result = {
            "reason_code": code,
            "reason": FAILURE_REASONS[code],
            "category": value["category"],
            "phase": phase if isinstance(phase, str) and phase in _PHASES else "read",
            "http_status": status
            if type(status) is int and 100 <= status <= 599
            else None,
            "wait_source": value.get("wait_source")
            if value.get("wait_source")
            in ("local_policy", "server_retry_after", "not_scheduled")
            else "legacy_unknown",
        }
        result.update(
            request_context=_safe_context(value.get("request_context")),
            validation_details=_safe_details(value.get("validation_details")),
        )
        for key in ("failed_at", "retry_at", "recovered_at"):
            try:
                parsed = datetime.fromisoformat(value[key])
                if parsed.tzinfo is not None:
                    result[key] = parsed.astimezone(UTC).isoformat()
            except (KeyError, TypeError, ValueError, OverflowError):
                pass
        return result

    def restore(self, data: object) -> None:
        """Přijmout jen vlastní typy/kategorie; neobnovovat libovolné zprávy."""
        if not isinstance(data, dict):
            return
        self.last_failure = self._restore_failure(data.get("last_failure"))
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
                or value.get("category") not in _CATEGORIES
            ):
                continue
            try:
                until = datetime.fromisoformat(value["until"])
                record = self._restore_failure(value)
                if until.tzinfo is not None and record is not None:
                    record["retry_at"] = until.astimezone(UTC).isoformat()
                    self.failures[key] = record
                if until.tzinfo is not None and until > datetime.now(UTC):
                    self.blocks[key] = (until.astimezone(UTC), value["category"])
                    self.deadlines[key] = (
                        time.monotonic() + (until - datetime.now(UTC)).total_seconds()
                    )
            except (KeyError, TypeError, ValueError, OverflowError):
                continue

    def check(self, scope: str, *additional_scopes: str) -> None:
        """Ruční načtení, report i backfill respektují stejný termín."""
        now = datetime.now(UTC)
        active = [
            (self.remaining(key, now), key)
            for key in ("account", scope, *additional_scopes)
            if key in self.blocks and self.remaining(key, now) > 0
        ]
        if active:
            seconds, key = max(active)
            category = self.blocks[key][1]
            until = now + timedelta(seconds=seconds)
            record = self.failures.get(key) or self._restore_failure(
                {"category": category}
            )
            assert record is not None
            self.last_failure = record.copy()
            self.last_failure["retry_at"] = until.isoformat()
            if record["reason_code"] == "legacy" and key not in self._legacy_logged:
                self._legacy_logged.add(key)
                _LOGGER.warning(
                    "EDC čeká po dřívějším selhání: %s; kategorie=%s; další pokus UTC=%s",
                    record["reason"],
                    category,
                    until.isoformat(),
                )
            raise EdcApiError(
                f"{record['reason']} Kategorie: {category}; HTTP: {record['http_status'] or 'nezjištěno'}. "
                f"{record['request_context']} {record['validation_details']} "
                f"Další pokus UTC: {until.replace(microsecond=0).isoformat()}.",
                category=category,
                status=record["http_status"],
                phase=record["phase"],
                retry_at=until,
                waiting=True,
                request_context=record["request_context"],
                validation_details=record["validation_details"],
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
            900
            if error.phase == "profile_validation"
            else 21600
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
        record = safe_failure_record(error)
        record.update(
            failed_at=now.isoformat(),
            retry_at=until.isoformat(),
            wait_source="server_retry_after"
            if server_until is not None and server_until > now
            else "local_policy",
        )
        previous = self.failures.get(key)
        self.failures[key] = record
        self.last_failure = record.copy()
        if (
            previous is None
            or any(
                previous.get(field) != record[field]
                for field in ("reason_code", "category", "phase", "http_status")
            )
            or previous.get("recovered_at")
        ):
            # Záznam vznikne i při prvním refreshi, který HA sám neloguje.
            # Opakované check() nezapisuje tentýž záznam a neposouvá lhůtu.
            _LOGGER.warning(
                "EDC čtení selhalo: %s%s %s; kategorie=%s; HTTP=%s; fáze=%s; čekání=%s; další pokus UTC=%s",
                record["reason"],
                record["request_context"],
                record["validation_details"],
                record["category"],
                record["http_status"],
                record["phase"],
                record["wait_source"],
                until.isoformat(),
            )
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
        await self._save()

    async def note_failure(self, error: EdcApiError) -> None:
        """Uložit původní chybu bez vytvoření či prodloužení síťového bloku.

        Potvrzené odmítnutí hesla přechází na reauth, nikoli periodický login.
        Lokální výpočet/chybějící měření používají normální interval obnovy.
        Čekací výjimka zde nikdy nesmí přepsat původní důvod selhání.
        """
        if error.waiting:
            return
        record = safe_failure_record(error)
        previous = self.last_failure
        fields = ("reason_code", "category", "phase", "http_status")
        changed = (
            previous is None
            or previous.get("recovered_at")
            or any(previous.get(key) != record[key] for key in fields)
        )
        record["failed_at"] = (
            datetime.now(UTC).isoformat()
            if changed
            else previous.get("failed_at", datetime.now(UTC).isoformat())
        )
        record["wait_source"] = "not_scheduled"
        if error.retry_at is not None:
            record["retry_at"] = error.retry_at.isoformat()
        self.last_failure = record
        if changed:
            _LOGGER.warning(
                "EDC selhalo bez nového síťového bloku: %s; kategorie=%s; HTTP=%s; fáze=%s",
                record["reason"],
                record["category"],
                record["http_status"],
                record["phase"],
            )
        await self._save()

    async def _save(self) -> None:
        """Uložit termíny i poslední důvod; selhání disku nezruší ochranu účtu."""
        if self.persist is not None:
            try:
                await self.persist(
                    {
                        **{
                            key: {
                                **self.failures.get(key, {}),
                                "until": value[0].isoformat(),
                                "category": value[1],
                            }
                            for key, value in self.blocks.items()
                        },
                        "last_failure": self.last_failure,
                    }
                )
                self.persistence_failed = False
            except (OSError, RuntimeError):
                # Nezastřít původní HTTP status; paměťové čekání zůstává aktivní.
                if not self.persistence_failed:
                    _LOGGER.warning(
                        "EDC důvod chyby nelze uložit na disk; čekání v paměti zůstává aktivní"
                    )
                self.persistence_failed = True

    async def recovered(self, scope: str, *additional_scopes: str) -> None:
        """Zapsat obnovu až po doménové validaci, nikoli po samotném HTTP 200.

        Nezkracovat jiný dosud aktivní blok. Uchovat poslední příčinu a čas
        obnovy pro diagnostiku i po restartu; nevypsat žádné identifikátory.
        """
        changed = False
        for key in ("account", scope, *additional_scopes):
            record = self.failures.get(key)
            if record is None or record.get("recovered_at"):
                continue
            if key in self.blocks and self.remaining(key, datetime.now(UTC)) > 0:
                continue
            record["recovered_at"] = datetime.now(UTC).isoformat()
            self.last_failure = record.copy()
            changed = True
        if (
            not changed
            and self.last_failure is not None
            and self.last_failure.get("wait_source") == "not_scheduled"
            and self.last_failure.get("phase") == "authentication"
            and not self.last_failure.get("recovered_at")
        ):
            # Úspěšné autorizované čtení je důkaz obnovených credentials,
            # nikoli důkaz opravy měření; netýká se chybějících profilů.
            self.last_failure["recovered_at"] = datetime.now(UTC).isoformat()
            changed = True
        if changed:
            _LOGGER.info("EDC čtení se obnovilo po ověřené platné odpovědi")
            await self._save()
