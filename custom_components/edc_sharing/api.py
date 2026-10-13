"""Asynchronous OIDC and API client for the EDC portal."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import os
import re
import time
import uuid
from datetime import date, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from aiohttp import ClientError, ClientSession, ClientTimeout

from .calculation import MAX_PROFILE_DAYS
from .const import API_BASE_URL, AUTHORITY_URL, CLIENT_ID, REDIRECT_URI

REQUEST_TIMEOUT = ClientTimeout(total=30)
ERROR_BODY_LIMIT = 16 * 1024
# Diagnostika smí zobrazit jen pevně známé kódy a názvy polí. Volné zprávy,
# hodnoty, identifikátory skupin/EANů ani přihlašovací údaje se nikdy nevypisují.
SAFE_ERROR_CODES = frozenset({
    "INVALID_DATE", "INVALID_ENTERED_DATE", "MAX_PERIOD_RANGE",
    "MAX_PERIOD_RANGE_FOR_EXPORT", "MISSING_DATA_FOR_PERIOD", "NOT_EMPTY",
    "NOT_FOUND", "MAX_LENGTH", "MIN_LENGTH", "NUMBER_BETWEEN",
    "INTERNAL_ERROR", "TIME_INTERVAL_EXCEEDS_LIMIT",
    "PRODUCER_IS_NOT_VALID_WHOLE_PERIOD",
})
SAFE_ERROR_FIELDS = frozenset({
    "sseId", "eans", "dateFrom", "dateTo", "calculationType", "inputData",
    "outputData", "fileName", "currentEnteredDateTime",
})
SAFE_API_PATHS = frozenset({
    "/profiles-data/get-sse", "/profiles-data/standard/overview",
})


class EdcApiError(Exception):
    """Base EDC API error."""


class EdcAuthenticationError(EdcApiError):
    """Authentication failed."""


class _LoginFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self._in_form = False
        self._target_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "form" and (attributes.get("id") == "kc-form-login" or self.action is None):
            if attributes.get("id") == "kc-form-login":
                self.fields.clear()
                self._target_form = True
            self._in_form = True
            self.action = html.unescape(attributes.get("action") or "")
        elif tag == "input" and self._in_form and attributes.get("name"):
            self.fields[attributes["name"]] = attributes.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._in_form:
            self._in_form = False


class EdcApiClient:
    """Client using the same public OIDC PKCE flow as portal.edc-cr.cz."""

    def __init__(self, session: ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at = 0.0
        self._request_lock = asyncio.Lock()

    async def async_login(self) -> None:
        verifier = _base64url(os.urandom(48))
        challenge = _base64url(hashlib.sha256(verifier.encode()).digest())
        state = _base64url(os.urandom(24))
        params = {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "openid",
            "prompt": "login",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "nonce": _base64url(os.urandom(24)),
        }
        try:
            response = await self._session.get(
                f"{AUTHORITY_URL}/protocol/openid-connect/auth?{urlencode(params)}",
                allow_redirects=False,
                timeout=REQUEST_TIMEOUT,
            )
            response, location = await self._async_follow_login_redirects(response)
            redirect_query = parse_qs(urlparse(location).query)
            code = redirect_query.get("code", [None])[0]
            if code:
                self._validate_authorization_redirect(redirect_query, state)
                await self._async_exchange_code(code, verifier)
                return
            if response.status >= 400:
                raise EdcApiError(f"Přihlašovací stránka EDC vrátila HTTP {response.status}.")
            response_text = await response.text()
            parser = _LoginFormParser()
            parser.feed(response_text)
            login_action = parser.action or _extract_keycloak_value(response_text, "loginAction")
            if not login_action:
                raise EdcApiError(
                    "Přihlašovací stránka EDC neobsahuje adresu loginAction."
                )
            form = parser.fields | {
                "username": self._username,
                "password": self._password,
                "credentialId": "",
            }
            login_response = await self._session.post(
                urljoin(str(response.url), login_action),
                data=form,
                allow_redirects=False,
                timeout=REQUEST_TIMEOUT,
            )
            login_response, location = await self._async_follow_login_redirects(login_response)
            redirect_query = parse_qs(urlparse(location).query)
            code = redirect_query.get("code", [None])[0]
            if not code:
                login_error = _extract_keycloak_error(await login_response.text())
                if login_error and _is_invalid_credentials_error(login_error):
                    raise EdcAuthenticationError(login_error)
                if login_response.status >= 400:
                    raise EdcApiError(
                        f"Přihlášení EDC vrátilo HTTP {login_response.status}."
                    )
                raise EdcApiError(
                    login_error or "EDC přihlášení nedokončilo přesměrováním."
                )
            self._validate_authorization_redirect(redirect_query, state)
            await self._async_exchange_code(code, verifier)
        except EdcApiError:
            raise
        except (ClientError, TimeoutError, ValueError):
            raise EdcApiError("Spojení s EDC selhalo.") from None

    async def _async_follow_login_redirects(
        self, response: Any
    ) -> tuple[Any, str]:
        """Follow Keycloak redirects while preserving the authorization callback."""
        location = response.headers.get("Location", "")
        for _ in range(5):
            if parse_qs(urlparse(location).query).get("code"):
                break
            if response.status not in (301, 302, 303, 307, 308) or not location:
                break
            response = await self._session.get(
                urljoin(str(response.url), location),
                allow_redirects=False,
                timeout=REQUEST_TIMEOUT,
            )
            location = response.headers.get("Location", "")
        return response, location

    @staticmethod
    def _validate_authorization_redirect(
        redirect_query: dict[str, list[str]], expected_state: str
    ) -> None:
        if redirect_query.get("state", [None])[0] != expected_state:
            raise EdcAuthenticationError("EDC vrátilo neplatný stav přihlášení.")

    async def _async_exchange_code(self, code: str, verifier: str) -> None:
        token_response = await self._session.post(
            f"{AUTHORITY_URL}/protocol/openid-connect/token",
            data={
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
            },
            timeout=REQUEST_TIMEOUT,
        )
        if token_response.status != 200:
            raise EdcAuthenticationError("Přihlášení EDC se nepodařilo dokončit.")
        self._store_tokens(await token_response.json())

    async def async_get_groups(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/profiles-data/get-sse")
        if not isinstance(data, list) or not all(
            isinstance(item, dict) for item in data
        ):
            raise EdcApiError("EDC vrátilo neplatný seznam skupin.")
        return data

    async def async_get_daily_profile(
        self, sse_id: int, date_from: date, date_to: date
    ) -> dict[str, Any]:
        """Načíst 1–31 kalendářních dnů z interního intervalu [od, do).

        Vstupy jsou místní kalendářní data EDC, nikoli UTC okamžiky. Portál
        používá YYYY-MM-DD a oba krajní dny včetně; koncovou mez proto snížíme
        o jeden den právě zde, společně pro obnovu, historii i reporty. Převod
        přes UTC by v létě posunul datum na předchozí den. Neplatný interval
        odmítneme před přihlášením/HTTP, odpověď profilu vracíme beze změny.
        """
        if type(date_from) is not date or type(date_to) is not date:
            raise ValueError("Profil EDC vyžaduje kalendářní data bez času.")
        if not 1 <= (date_to - date_from).days <= MAX_PROFILE_DAYS:
            raise ValueError("Profil EDC vyžaduje rozsah 1 až 31 kalendářních dnů.")
        payload = {
            "sseId": sse_id,
            "calculationType": "DAILY",
            "inputData": True,
            "outputData": True,
            "dateFrom": date_from.isoformat(),
            "dateTo": (date_to - timedelta(days=1)).isoformat(),
            "fileName": "_",
        }
        data = await self._request("POST", "/profiles-data/standard/overview", payload)
        if not isinstance(data, dict):
            raise EdcApiError("EDC vrátilo neplatná profilová data.")
        return data

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        async with self._request_lock:
            try:
                await self._async_ensure_token()
                response = await self._session.request(
                    method,
                    f"{API_BASE_URL}{path}",
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self._access_token}",
                        "Edc-Contract-Type": "STANDARD",
                        "X-Correlation-ID": str(uuid.uuid4()),
                    },
                )
                try:
                    if response.status == 401:
                        self._access_token = None
                        raise EdcAuthenticationError(
                            "Platnost přihlášení EDC skončila."
                        )
                    if response.status >= 400:
                        details = await _async_safe_error_details(response)
                        context = _safe_request_context(method, path, payload)
                        raise EdcApiError(
                            f"EDC API vrátilo HTTP {response.status}{context}."
                            + (f" {details}" if details else "")
                        )
                    return await response.json()
                finally:
                    # Uvolnit spojení i při 401, chybě JSONu nebo velkém těle
                    # chyby; diagnostika nesmí zadržovat HTTP pool při retry.
                    response.release()
            except EdcApiError:
                raise
            except (ClientError, TimeoutError, ValueError):
                raise EdcApiError("Spojení s EDC selhalo.") from None

    async def _async_ensure_token(self) -> None:
        if self._access_token and time.monotonic() < self._expires_at - 30:
            return
        if self._refresh_token:
            response = await self._session.post(
                f"{AUTHORITY_URL}/protocol/openid-connect/token",
                data={
                    "client_id": CLIENT_ID,
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                timeout=REQUEST_TIMEOUT,
            )
            if response.status == 200:
                self._store_tokens(await response.json())
                return
        await self.async_login()

    def _store_tokens(self, data: dict[str, Any]) -> None:
        try:
            access_token = data["access_token"]
            expires_in = int(data.get("expires_in", 300))
        except (KeyError, TypeError, ValueError) as err:
            raise EdcApiError("EDC vrátilo neplatnou tokenovou odpověď.") from err
        if not isinstance(access_token, str) or not access_token:
            raise EdcApiError("EDC vrátilo neplatnou tokenovou odpověď.")
        refresh_token = data.get("refresh_token")
        self._access_token = access_token
        self._refresh_token = (
            refresh_token if isinstance(refresh_token, str) and refresh_token else None
        )
        self._expires_at = time.monotonic() + max(0, expires_in)


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _safe_request_context(
    method: str, path: str, payload: dict[str, Any] | None
) -> str:
    """Doplnit jen známý endpoint a ověřená kalendářní data, nikdy celý JSON."""
    if method not in ("GET", "POST") or path not in SAFE_API_PATHS:
        return ""
    context = f" ({method} {path})"
    if isinstance(payload, dict):
        bounds = [payload.get("dateFrom"), payload.get("dateTo")]
        try:
            if all(isinstance(value, str) and len(value) == 10 for value in bounds):
                parsed = [date.fromisoformat(value) for value in bounds]
                context += f"; období {parsed[0].isoformat()} až {parsed[1].isoformat()}"
        except ValueError:
            pass
    return context


async def _async_safe_error_details(response: Any) -> str:
    """Přečíst nejvýše 16 KiB chyby; ponechat pouze povolené kódy/pole.

    Čtení respektuje timeout původního požadavku. HTML, neplatné JSON/UTF-8,
    velké tělo či chyba čtení nesmí překrýt původní HTTP status. Neznámé kódy
    a volné zprávy se nevracejí do logu ani do atributů diagnostických entit.
    """
    try:
        try:
            body = await response.content.readexactly(ERROR_BODY_LIMIT + 1)
        except asyncio.IncompleteReadError as err:
            body = err.partial
        if len(body) > ERROR_BODY_LIMIT:
            return ""
        data = json.loads(body)
    except (ClientError, TimeoutError, ValueError, RecursionError):
        return ""
    if not isinstance(data, dict):
        return ""
    errors = data.get("validationErrors")
    candidates = errors[:5] if isinstance(errors, list) else []
    generic = data.get("genericError")
    if isinstance(generic, dict):
        candidates = [*candidates, generic]
    details: list[str] = []
    for error in candidates:
        if not isinstance(error, dict):
            continue
        code = error.get("code")
        field = error.get("field")
        if not isinstance(code, str) or code not in SAFE_ERROR_CODES:
            continue
        detail = code
        if isinstance(field, str) and field in SAFE_ERROR_FIELDS:
            detail += f" ({field})"
        if detail not in details:
            details.append(detail)
    return "; ".join(details)


def _extract_keycloak_value(page: str, name: str) -> str | None:
    """Extract a JSON string property embedded in the Keycloakify kcContext."""
    match = re.search(
        rf'"{re.escape(name)}"\s*:\s*("(?:\\.|[^"\\])*")',
        page,
    )
    if match is None:
        return None
    try:
        return html.unescape(str(json.loads(match.group(1))))
    except (json.JSONDecodeError, TypeError):
        return None


def _extract_keycloak_error(page: str) -> str | None:
    """Return the Keycloakify error summary, if the response contains one."""
    message = re.search(r'"message"\s*:\s*\{(.*?)\}', page, re.DOTALL)
    if message is None or not re.search(r'"type"\s*:\s*"error"', message.group(1)):
        return None
    return _extract_keycloak_value(message.group(1), "summary")


def _is_invalid_credentials_error(message: str) -> bool:
    normalized = message.casefold()
    return (
        "neplatné jméno nebo heslo" in normalized
        or "invalid username or password" in normalized
    )
