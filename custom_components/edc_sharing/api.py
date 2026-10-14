"""Asynchronous OIDC and API client for the EDC portal."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import logging
import math
import os
import random
import re
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from aiohttp import ClientError, ClientSession, ClientTimeout

from .api_policy import (
    SAFE_ERROR_CODES,
    SAFE_ERROR_FIELDS,
    ApiAccountState,
    EdcAccessExpiredError,
    EdcApiError,
    EdcAuthenticationError,
    classify_api_failure,
    retry_after,
)
from .calculation import MAX_PROFILE_DAYS, profile_resolution, validate_profile_response
from .const import API_BASE_URL, AUTHORITY_URL, CLIENT_ID, REDIRECT_URI

REQUEST_TIMEOUT = ClientTimeout(total=30)
LOGGER = logging.getLogger(__name__)
ERROR_BODY_LIMIT = 16 * 1024
# Diagnostika smí zobrazit jen pevně známé kódy a názvy polí. Volné zprávy,
# hodnoty, identifikátory skupin/EANů ani přihlašovací údaje se nikdy nevypisují.
SAFE_API_PATHS = frozenset(
    {
        "/profiles-data/get-sse",
        "/profiles-data/standard/overview",
    }
)


def _safe_profile_time_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Zachytit příčinu neznámého rozlišení bez obsahu měření a identit.

    Volá se pouze po ověření schématu a při odmítnutí časového rozlišení.
    Nejvýše 4096 řádků rozdělí podle samostatného rozlišení; šest vzorků
    obsahuje jen pořadí a start/end. Přesný text je dovolen výhradně pro
    syntaktický čas, případně ISO datum s časem. Jiný obsah se nahradí
    pevnou značkou typu. Čísla energie, sloupce, EANy, hlavičky, účet,
    přihlášení a celé odpovědi se nelogují. Jednotkou hranic je místní
    čas EDC; diagnostika ho nepřevádí ani nezaokrouhluje. Neprovádí síť,
    neobchází kontrolu a nemění odpověď, cache ani čekací lhůtu.
    """
    content = data["content"]
    counts: dict[str, int] = {}
    indices = [0, len(content) - 1] if content else []
    for index, row in enumerate(content[:4096]):
        resolution = profile_resolution({"content": [row]})
        counts[resolution] = counts.get(resolution, 0) + 1
        if resolution == "unknown" and len(indices) < 6 and index not in indices:
            indices.append(index)

    def clock(value: Any) -> str:
        if isinstance(value, str) and re.fullmatch(
            r"(?:[0-9]{4}-[0-9]{2}-[0-9]{2}[T ])?[0-9]{1,2}:[0-9]{2}"
            r"(?::[0-9]{2}(?:[.,][0-9]{1,9})?)?(?:Z|[+-][0-9]{2}:[0-9]{2})?",
            value,
        ):
            return value
        kind = {str: "str", int: "int", float: "float", bool: "bool",
                list: "list", dict: "dict", type(None): "missing"}.get(type(value), "unsupported")
        return f"<{kind}>"

    return {
        "rows": len(content),
        "inspected_rows": min(len(content), 4096),
        "row_resolutions": counts,
        "samples": [{"row_index": index, "start": clock(content[index].get("start")),
                     "end": clock(content[index].get("end"))}
                    for index in dict.fromkeys(indices)],
    }


def build_profile_request(
    sse_id: int, date_from: date, date_to: date
) -> dict[str, Any]:
    """Jediný builder pro místní [od, do); bez přihlášení a vedlejších účinků."""
    if type(sse_id) is not int or sse_id <= 0:
        raise ValueError("Profil EDC vyžaduje kladné celočíselné ID skupiny.")
    if type(date_from) is not date or type(date_to) is not date:
        raise ValueError("Profil EDC vyžaduje kalendářní data bez času.")
    if not 1 <= (date_to - date_from).days <= MAX_PROFILE_DAYS:
        raise ValueError("Profil EDC vyžaduje rozsah 1 až 31 kalendářních dnů.")
    return {
        "sseId": sse_id,
        "calculationType": "DAILY",
        "inputData": True,
        "outputData": True,
        "dateFrom": date_from.isoformat(),
        "dateTo": (date_to - timedelta(days=1)).isoformat(),
        "fileName": "_",
    }


class _LoginFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self._in_form = False
        self._target_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "form" and attributes.get("id") == "kc-form-login":
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

    def __init__(
        self,
        session: ClientSession,
        username: str,
        password: str,
        account_state: ApiAccountState | None = None,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at = 0.0
        self.account_state = account_state or ApiAccountState()
        self._request_lock = self.account_state.lock
        self.last_failure_category: str | None = None
        self.last_status: int | None = None

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
        response = None
        login_response = None
        # Krok zůstává lokální pro tento pokus. Mění se těsně před HTTP
        # operací, takže i timeout označí skutečně rozpracovaný požadavek.
        # Neobsahuje URL ani údaje účtu; nesmí vyvolat další login/retry.
        authentication_step = "authorization_get"
        try:
            response = await self._session.get(
                f"{AUTHORITY_URL}/protocol/openid-connect/auth?{urlencode(params)}",
                allow_redirects=False,
                timeout=REQUEST_TIMEOUT,
            )
            response, location, authentication_step = await self._async_follow_login_redirects(
                response, authentication_step
            )
            redirect_query = parse_qs(urlparse(location).query)
            code = redirect_query.get("code", [None])[0]
            if code:
                self._validate_authorization_redirect(redirect_query, state)
                authentication_step = "code_exchange_post"
                await self._async_exchange_code(code, verifier)
                return
            if response.status >= 400:
                raise self._login_http_error(response, authentication_step)
            response_text = await response.text()
            response.release()
            self._require_supported_login_page(response_text)
            parser = _LoginFormParser()
            parser.feed(response_text)
            login_action = parser.action or _extract_keycloak_value(
                response_text, "loginAction"
            )
            if not login_action:
                raise EdcApiError(
                    "Přihlašovací stránka EDC neobsahuje adresu loginAction.",
                    category="contract",
                )
            form = parser.fields | {
                "username": self._username,
                "password": self._password,
                "credentialId": "",
            }
            login_target = urljoin(str(response.url), login_action)
            self._validate_login_target(login_target)
            authentication_step = "credentials_post"
            login_response = await self._session.post(
                login_target,
                data=form,
                allow_redirects=False,
                timeout=REQUEST_TIMEOUT,
            )
            login_response, location, authentication_step = await self._async_follow_login_redirects(
                login_response, authentication_step
            )
            redirect_query = parse_qs(urlparse(location).query)
            code = redirect_query.get("code", [None])[0]
            if not code:
                login_text = await login_response.text()
                login_error = _extract_keycloak_error(login_text)
                login_response.release()
                if login_error and _is_invalid_credentials_error(login_error):
                    raise EdcAuthenticationError("Neplatné jméno nebo heslo EDC.")
                if login_response.status >= 400:
                    raise self._login_http_error(login_response, authentication_step)
                self._require_supported_login_page(login_text)
                raise EdcApiError(
                    "EDC přihlášení nedokončilo přesměrováním.", category="contract"
                )
            self._validate_authorization_redirect(redirect_query, state)
            authentication_step = "code_exchange_post"
            await self._async_exchange_code(code, verifier)
        except EdcApiError as error:
            error.phase = "authentication"
            if error.authentication_step is None:
                error.authentication_step = authentication_step
            raise
        except (ClientError, TimeoutError, ValueError):
            raise EdcApiError(
                "Spojení s přihlášením EDC selhalo.",
                category="unavailable",
                phase="authentication",
                authentication_step=authentication_step,
            ) from None
        finally:
            for result in (response, login_response):
                if result is not None:
                    result.release()

    async def _async_follow_login_redirects(
        self, response: Any, authentication_step: str
    ) -> tuple[Any, str, str]:
        """Vrátit odpověď, callback a skutečný poslední krok přihlášení.

        Vstup je odpověď GETu/POSTu. Nejvýše pět redirect GETů zůstává na
        ověřeném SSO originu; autorizační callback se nestahuje. Název kroku
        změníme pouze při odeslání dalšího GETu, nikoli při jeho nalezení.
        Transportní chyba i neplatný cíl zachovají krok, který je způsobil.
        """
        location = response.headers.get("Location", "")
        redirect_step = (
            "credentials_redirect_get"
            if authentication_step == "credentials_post"
            else "authorization_redirect_get"
        )
        try:
            for _ in range(5):
                if parse_qs(urlparse(location).query).get("code"):
                    response.release()
                    self._validate_login_target(location, callback=True)
                    break
                if response.status not in (301, 302, 303, 307, 308) or not location:
                    break
                target = urljoin(str(response.url), location)
                response.release()
                self._validate_login_target(target)
                authentication_step = redirect_step
                response = await self._session.get(
                    target,
                    allow_redirects=False,
                    timeout=REQUEST_TIMEOUT,
                )
                location = response.headers.get("Location", "")
            return response, location, authentication_step
        except EdcApiError as error:
            error.authentication_step = authentication_step
            raise
        except (ClientError, TimeoutError, ValueError):
            raise EdcApiError(
                "Spojení s přihlášením EDC selhalo.",
                category="unavailable",
                phase="authentication",
                authentication_step=authentication_step,
            ) from None

    @staticmethod
    def _require_supported_login_page(page: str) -> None:
        """MFA/CAPTCHA není špatné heslo; bez podpory pokračování vyžaduje člověka.

        Rozpoznáváme explicitní známé pageId nebo CAPTCHA prvek, nikoli volný
        výskyt slova v JS překladech. Neznámá stránka se dál posoudí jako kontrakt.
        """
        page_id = _extract_keycloak_value(page, "pageId")
        if page_id in (
            "login-otp.ftl",
            "login-recovery-authn-code-input.ftl",
            "login-webauthn.ftl",
        ) or re.search(r'class=["\'][^"\']*\b(?:g-recaptcha|h-captcha)\b', page):
            raise EdcApiError(
                "Přihlášení EDC vyžaduje ruční ověření MFA/CAPTCHA.",
                category="user_action",
                phase="authentication",
            )

    @staticmethod
    def _login_http_error(response: Any, authentication_step: str) -> EdcApiError:
        """Pevný text a HTTP kategorie; nikdy neoznačit 5xx/429 jako špatné heslo."""
        return EdcApiError(
            f"Přihlašovací služba EDC vrátila HTTP {response.status}.",
            category=classify_api_failure(response.status),
            status=response.status,
            retry_at=retry_after(
                response.headers.get("Retry-After"), datetime.now(UTC)
            ),
            phase="authentication",
            authentication_step=authentication_step,
        )

    @staticmethod
    def _validate_login_target(target: str, *, callback: bool = False) -> None:
        """Heslo/token nikdy neposílat na cizí origin získaný z HTML či redirectu."""
        parsed = urlparse(target)
        allowed = urlparse(REDIRECT_URI if callback else AUTHORITY_URL)
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() != allowed.netloc.lower()
            or parsed.username is not None
            or parsed.password is not None
            or (callback and parsed.path != allowed.path)
        ):
            raise EdcApiError("EDC změnilo cíl přihlašování.", category="contract")

    @staticmethod
    def _validate_authorization_redirect(
        redirect_query: dict[str, list[str]], expected_state: str
    ) -> None:
        if redirect_query.get("state", [None])[0] != expected_state:
            raise EdcApiError(
                "EDC vrátilo neplatný stav přihlášení.",
                category="contract",
                phase="authentication",
            )

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
            allow_redirects=False,
        )
        try:
            if token_response.status != 200:
                raise self._login_http_error(token_response, "code_exchange_post")
            self._store_tokens(await token_response.json())
        finally:
            token_response.release()

    async def async_get_groups(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/profiles-data/get-sse")
        if not isinstance(data, list) or not all(
            isinstance(item, dict)
            and type(item.get("sseId")) is int
            and item["sseId"] > 0
            for item in data
        ):
            error = EdcApiError(
                "EDC vrátilo neplatný seznam skupin.", category="contract"
            )
            self.last_failure_category = error.category
            async with self._request_lock:
                await self.account_state.block(
                    self.account_state.scope("/profiles-data/get-sse", None), error
                )
            raise error
        async with self._request_lock:
            await self.account_state.recovered(
                self.account_state.scope("/profiles-data/get-sse", None)
            )
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
        payload = build_profile_request(sse_id, date_from, date_to)
        data = await self._request("POST", "/profiles-data/standard/overview", payload)
        try:
            validate_profile_response(data)
            if profile_resolution(data) == "unknown":
                # Využít právě přijatou odpověď stejného klienta: druhé
                # přihlášení by mohlo skončit 403 a zakrýt chybu profilu.
                LOGGER.error("EDC časový kontrakt: %s", _safe_profile_time_summary(data))
                raise ValueError("EDC vrátilo nerozpoznané časové rozlišení.")
            if any(
                not date_from <= date.fromisoformat(row["date"][:10]) < date_to
                for row in data["content"]
            ):
                raise ValueError("EDC vrátilo data mimo požadovaný interval.")
        except ValueError as err:
            failure = EdcApiError(
                str(err),
                category="contract",
                status=self.last_status,
                phase="profile_validation",
                request_context=_safe_request_context(
                    "POST", "/profiles-data/standard/overview", payload
                ),
            )
            self.last_failure_category = failure.category
            async with self._request_lock:
                await self.account_state.block(
                    self.account_state.scope(
                        "/profiles-data/standard/overview", payload, period=True
                    ),
                    failure,
                )
            raise failure from None
        async with self._request_lock:
            await self.account_state.recovered(
                self.account_state.scope("/profiles-data/standard/overview", payload),
                self.account_state.scope(
                    "/profiles-data/standard/overview", payload, period=True
                ),
            )
        return data

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        """Serializovat čtení účtu a nejvýše dva krátké transportní pokusy.

        Serverové čekání se ukládá a vrací plánovači. 400/422 neopakujeme;
        401 obnovíme právě jednou. Délka každého HTTP pokusu je 30 s; čekání
        5/30 s neblokuje event loop. CancelledError vždy propaguje.
        """
        if path not in SAFE_API_PATHS or method not in ("GET", "POST"):
            raise ValueError("Nepovolená čtecí cesta EDC.")
        async with self._request_lock:
            scope = self.account_state.scope(path, payload)
            try:
                self.account_state.check(
                    scope, self.account_state.scope(path, payload, period=True)
                )
            except EdcApiError as error:
                # Ani nový klient po restartu nesmí ztratit HTTP status a
                # kategorii tím, že už pouze čeká na uložený termín.
                self.last_failure_category = error.category
                self.last_status = error.status
                raise
            refreshed = False
            for attempt in range(3):
                try:
                    return await self._request_once(method, path, payload)
                except EdcAccessExpiredError:
                    self.last_failure_category = "authentication"
                    self.last_status = 401
                    if refreshed:
                        raise
                    self._access_token = None
                    refreshed = True
                    # Autentizační opakování není transportní retry.
                    try:
                        return await self._request_once(method, path, payload)
                    except EdcAuthenticationError as error:
                        await self.account_state.note_failure(error)
                        raise
                    except EdcApiError as error:
                        await self.account_state.block(scope, error, error.retry_at)
                        raise
                except EdcAuthenticationError as error:
                    # Potvrzené odmítnutí loginu nevynucuje druhé zadání hesla.
                    self.last_failure_category = "authentication"
                    await self.account_state.note_failure(error)
                    raise
                except EdcApiError as error:
                    self.last_failure_category = error.category
                    self.last_status = error.status
                    if (
                        error.category == "unavailable"
                        and error.phase == "read"
                        and error.retry_at is None
                        and attempt < 2
                    ):
                        await asyncio.sleep((5, 30)[attempt] + random.uniform(0, 1))
                        continue
                    await self.account_state.block(scope, error, error.retry_at)
                    raise
            raise AssertionError("EDC retry vyčerpal neočekávanou větev")

    async def _request_once(
        self, method: str, path: str, payload: dict[str, Any] | None
    ) -> Any:
        try:
            await self._async_ensure_token()
        except (ClientError, TimeoutError, ValueError):
            # Opakování čtení nesmí opakovat přihlašovací POST po jeho timeoutu.
            raise EdcApiError(
                "Obnova přihlášení EDC selhala.",
                category="unavailable",
                phase="authentication",
                authentication_step="refresh_token_post",
            ) from None
        try:
            response = await self._session.request(
                method,
                f"{API_BASE_URL}{path}",
                json=payload,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._access_token}",
                    "Edc-Contract-Type": "STANDARD",
                    "X-Correlation-ID": str(uuid.uuid4()),
                },
            )
            try:
                if 300 <= response.status < 400:
                    raise EdcApiError(
                        "EDC změnilo adresu čtecího API.",
                        category="contract",
                        status=response.status,
                    )
                if response.status == 401:
                    self._access_token = None
                    raise EdcAccessExpiredError("Platnost přihlášení EDC skončila.")
                if response.status >= 400:
                    details = await _async_safe_error_details(response)
                    context = _safe_request_context(method, path, payload)
                    raise EdcApiError(
                        f"EDC API vrátilo HTTP {response.status}{context}."
                        + (f" {details}" if details else ""),
                        category=classify_api_failure(response.status),
                        status=response.status,
                        retry_at=retry_after(
                            response.headers.get("Retry-After"), datetime.now(UTC)
                        ),
                        request_context=context,
                        validation_details=details,
                    )
                try:
                    data = await response.json()
                except (ValueError, ClientError):
                    raise EdcApiError(
                        "EDC vrátilo neplatnou JSON odpověď.",
                        category="contract",
                        status=response.status,
                    ) from None
                self.last_status = response.status
                self.last_failure_category = None
                return data
            finally:
                # Uvolnit spojení i při 401, chybě JSONu nebo velkém těle
                # chyby; diagnostika nesmí zadržovat HTTP pool při retry.
                response.release()
        except EdcApiError:
            raise
        except (ClientError, TimeoutError, ValueError):
            raise EdcApiError(
                "Spojení s EDC selhalo.", category="unavailable"
            ) from None

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
                allow_redirects=False,
            )
            try:
                if response.status == 200:
                    self._store_tokens(await response.json())
                    return
                # Pouze odmítnutá platnost refresh tokenu dovoluje jeden nový
                # login. Technická chyba/limit nesmí znovu odesílat heslo.
                if response.status not in (400, 401):
                    raise self._login_http_error(response, "refresh_token_post")
                if response.status == 400:
                    try:
                        rejection = await response.json()
                    except (ClientError, ValueError):
                        raise self._login_http_error(response, "refresh_token_post") from None
                    if (
                        not isinstance(rejection, dict)
                        or rejection.get("error") != "invalid_grant"
                    ):
                        raise self._login_http_error(response, "refresh_token_post")
                self._refresh_token = None
            except EdcApiError as error:
                if error.authentication_step is None:
                    error.authentication_step = "refresh_token_post"
                raise
            finally:
                response.release()
        await self.async_login()

    def _store_tokens(self, data: dict[str, Any]) -> None:
        try:
            access_token = data["access_token"]
            lifetime = data.get("expires_in", 300)
            if isinstance(lifetime, bool):
                raise TypeError("Neplatný typ délky tokenu.")
            expires_in = int(lifetime)
            if expires_in <= 0 or not math.isfinite(float(expires_in)):
                raise ValueError("Neplatná délka tokenu.")
        except (KeyError, TypeError, ValueError, OverflowError):
            raise EdcApiError(
                "EDC vrátilo neplatnou tokenovou odpověď.",
                category="contract",
                phase="authentication",
            ) from None
        if not isinstance(access_token, str) or not access_token:
            raise EdcApiError(
                "EDC vrátilo neplatnou tokenovou odpověď.",
                category="contract",
                phase="authentication",
            )
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
                context += (
                    f"; období {parsed[0].isoformat()} až {parsed[1].isoformat()}"
                )
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
