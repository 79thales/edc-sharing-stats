"""Asynchronous OIDC and API client for the EDC portal."""

from __future__ import annotations

import base64
import hashlib
import html
from html.parser import HTMLParser
import json
import os
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
import uuid

from aiohttp import ClientError, ClientSession

from .const import API_BASE_URL, AUTHORITY_URL, CLIENT_ID, REDIRECT_URI


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
                urljoin(str(response.url), login_action), data=form, allow_redirects=False
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
        except (ClientError, TimeoutError, ValueError) as err:
            raise EdcApiError(f"Spojení s EDC selhalo: {err}") from err

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
                urljoin(str(response.url), location), allow_redirects=False
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
        )
        if token_response.status != 200:
            raise EdcAuthenticationError("Přihlášení EDC se nepodařilo dokončit.")
        self._store_tokens(await token_response.json())

    async def async_get_groups(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/profiles-data/get-sse")
        if not isinstance(data, list):
            raise EdcApiError("EDC vrátilo neplatný seznam skupin.")
        return data

    async def async_get_daily_profile(
        self, sse_id: int, date_from_utc: str, date_to_utc: str
    ) -> dict[str, Any]:
        payload = {
            "sseId": sse_id,
            "calculationType": "DAILY",
            "inputData": True,
            "outputData": True,
            "dateFrom": date_from_utc,
            "dateTo": date_to_utc,
            "profileType": "STANDARD",
            "fileName": "_",
        }
        data = await self._request("POST", "/profiles-data/standard/overview", payload)
        if not isinstance(data, dict):
            raise EdcApiError("EDC vrátilo neplatná profilová data.")
        return data

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        try:
            await self._async_ensure_token()
            response = await self._session.request(
                method,
                f"{API_BASE_URL}{path}",
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._access_token}",
                    "Edc-Contract-Type": "STANDARD",
                    "X-Correlation-ID": str(uuid.uuid4()),
                },
            )
            if response.status == 401:
                self._access_token = None
                raise EdcAuthenticationError("Platnost přihlášení EDC skončila.")
            if response.status >= 400:
                raise EdcApiError(f"EDC API vrátilo HTTP {response.status}.")
            return await response.json()
        except EdcApiError:
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            raise EdcApiError(f"Spojení s EDC selhalo: {err}") from err

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
            )
            if response.status == 200:
                self._store_tokens(await response.json())
                return
        await self.async_login()

    def _store_tokens(self, data: dict[str, Any]) -> None:
        self._access_token = str(data["access_token"])
        self._refresh_token = data.get("refresh_token")
        self._expires_at = time.monotonic() + int(data.get("expires_in", 300))


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


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
