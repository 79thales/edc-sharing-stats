"""Tests for the EDC Keycloak login page helpers."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

try:
    import aiohttp  # noqa: F401
except ModuleNotFoundError:
    aiohttp_stub = types.ModuleType("aiohttp")

    class ClientError(Exception):
        pass

    class ClientTimeout:
        def __init__(self, *, total: float) -> None:
            self.total = total

    class ClientSession:
        pass

    aiohttp_stub.ClientError = ClientError
    aiohttp_stub.ClientSession = ClientSession
    aiohttp_stub.ClientTimeout = ClientTimeout
    sys.modules["aiohttp"] = aiohttp_stub


REPOSITORY_ROOT = Path(__file__).parents[1]
COMPONENT_ROOT = REPOSITORY_ROOT / "custom_components" / "edc_sharing"
PACKAGE_NAME = "_edc_sharing_test"

package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(COMPONENT_ROOT)]
sys.modules[PACKAGE_NAME] = package

for module_name in ("const", "api"):
    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE_NAME}.{module_name}", COMPONENT_ROOT / f"{module_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

api = sys.modules[f"{PACKAGE_NAME}.api"]
calculation = sys.modules[f"{PACKAGE_NAME}.calculation"]


class _Content:
    def __init__(self, body: bytes) -> None:
        self.body = body

    async def readexactly(self, size: int) -> bytes:
        if len(self.body) < size:
            raise asyncio.IncompleteReadError(self.body, size)
        return self.body[:size]


class _Response:
    def __init__(
        self,
        status: int,
        url: str,
        *,
        location: str = "",
        text: str = "",
        json_data: Any = None,
        body: bytes | None = None,
    ) -> None:
        self.status = status
        self.url = url
        self.headers = {"Location": location} if location else {}
        self._text = text
        self._json_data = {"content": [], "valueColumns": []} if json_data is None else json_data
        self.content = _Content(
            json.dumps(self._json_data).encode() if body is None else body
        )
        self.released = False

    async def text(self) -> str:
        return self._text

    async def json(self) -> Any:
        return self._json_data

    def release(self) -> None:
        self.released = True


class _Session:
    def __init__(
        self,
        get_responses: list[_Response],
        post_responses: list[_Response],
        request_responses: list[_Response | BaseException] | None = None,
    ) -> None:
        self.get_responses = get_responses
        self.post_responses = post_responses
        self.request_responses = request_responses or []
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []
        self.request_calls: list[tuple[str, str, dict]] = []

    async def get(self, url: str, **kwargs) -> _Response:
        self.get_calls.append((url, kwargs))
        return self.get_responses.pop(0)

    async def post(self, url: str, **kwargs) -> _Response:
        self.post_calls.append((url, kwargs))
        return self.post_responses.pop(0)

    async def request(self, method: str, url: str, **kwargs) -> _Response:
        self.request_calls.append((method, url, kwargs))
        response = self.request_responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class KeycloakPageTest(unittest.TestCase):
    def test_extracts_keycloakify_login_action(self) -> None:
        page = r'''
        const kcContext = {
          "url": {
            "loginAction": "https://sso.portal.edc-cr.cz/auth/realms/edc/login-actions/authenticate?session_code=abc\u0026execution=def"
          }
        };
        '''
        self.assertEqual(
            api._extract_keycloak_value(page, "loginAction"),
            "https://sso.portal.edc-cr.cz/auth/realms/edc/login-actions/authenticate?session_code=abc&execution=def",
        )

    def test_extracts_invalid_credentials_error(self) -> None:
        page = '''
        "message": {
          "summary": "Neplatné jméno nebo heslo.",
          "type": "error",
          "error": true,
        }
        '''
        message = api._extract_keycloak_error(page)
        self.assertEqual(message, "Neplatné jméno nebo heslo.")
        self.assertTrue(api._is_invalid_credentials_error(message))

    def test_ignores_non_error_message(self) -> None:
        page = '"message": {"summary": "Odhlášení proběhlo.", "type": "success"}'
        self.assertIsNone(api._extract_keycloak_error(page))


class LoginRedirectTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch.object(api, "AUTHORITY_URL", "https://sso.example/auth"))
    async def test_existing_edc_session_exchanges_redirect_code(self) -> None:
        authorization_url = "https://sso.example/auth"
        callback_url = "https://portal.edc-cr.cz/?code=auth-code&state=state"
        session = _Session(
            [_Response(302, authorization_url, location=callback_url)],
            [
                _Response(
                    200,
                    "https://sso.example/token",
                    json_data={"access_token": "access", "expires_in": 300},
                )
            ],
        )
        client = api.EdcApiClient(session, "user@example.com", "secret")

        with patch.object(
            api,
            "_base64url",
            side_effect=["verifier", "challenge", "state", "nonce"],
        ):
            await client.async_login()

        self.assertEqual(client._access_token, "access")
        self.assertIn("prompt=login", session.get_calls[0][0])
        self.assertFalse(session.get_calls[0][1]["allow_redirects"])
        self.assertIs(session.get_calls[0][1]["timeout"], api.REQUEST_TIMEOUT)
        self.assertEqual(len(session.post_calls), 1)
        self.assertEqual(session.post_calls[0][1]["data"]["code"], "auth-code")
        self.assertIs(session.post_calls[0][1]["timeout"], api.REQUEST_TIMEOUT)

    async def test_session_code_is_not_mistaken_for_authorization_code(self) -> None:
        login_page = _Response(200, "https://sso.example/login", text="login page")
        session = _Session([login_page], [])
        client = api.EdcApiClient(session, "user@example.com", "secret")
        response = _Response(
            302,
            "https://sso.example/auth",
            location="https://sso.example/login?session_code=abc",
        )

        final_response, location, step = await client._async_follow_login_redirects(
            response, "authorization_get"
        )

        self.assertIs(final_response, login_page)
        self.assertEqual(location, "")
        self.assertEqual(step, "authorization_redirect_get")
        self.assertEqual(len(session.get_calls), 1)

    async def test_missing_login_action_is_technical_error(self) -> None:
        session = _Session(
            [_Response(200, "https://sso.example/auth", text="login page")], []
        )
        client = api.EdcApiClient(session, "user@example.com", "secret")

        with (
            patch.object(
                api,
                "_base64url",
                side_effect=["verifier", "challenge", "state", "nonce"],
            ),
            self.assertRaises(api.EdcApiError) as raised,
        ):
            await client.async_login()

        self.assertNotIsInstance(raised.exception, api.EdcAuthenticationError)

    def test_malformed_token_response_is_a_sanitized_api_error(self) -> None:
        client = api.EdcApiClient(_Session([], []), "user@example.com", "secret")

        with self.assertRaisesRegex(api.EdcApiError, "token"):
            client._store_tokens({"expires_in": "invalid"})


class ApiRequestTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch.object(api.asyncio, "sleep", new=AsyncMock()))
    @staticmethod
    def _authenticated_client(session: _Session):
        client = api.EdcApiClient(session, "user@example.com", "secret")
        client._store_tokens({"access_token": "access", "expires_in": 300})
        return client

    async def test_profile_request_has_explicit_timeout(self) -> None:
        session = _Session([], [], [_Response(200, "https://api.example")])
        client = self._authenticated_client(session)

        await client.async_get_daily_profile(1, date(2026, 9, 1), date(2026, 10, 2))

        self.assertIs(session.request_calls[0][2]["timeout"], api.REQUEST_TIMEOUT)

    async def test_profile_payload_matches_calendar_date_portal_contract(self) -> None:
        response = _Response(200, "https://api.example", json_data={"content": []})
        session = _Session([], [], [response])
        client = self._authenticated_client(session)

        self.assertEqual(
            await client.async_get_daily_profile(1, date(2026, 9, 1), date(2026, 10, 2)),
            {"content": []},
        )
        method, url, options = session.request_calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/profiles-data/standard/overview"))
        snapshot = options["json"].pop("currentEnteredDateTime")
        self.assertEqual(datetime.fromisoformat(snapshot).utcoffset(), timedelta(0))
        self.assertTrue(snapshot.endswith("Z"))
        self.assertEqual(options["json"], {
            "sseId": 1, "inputData": True,
            "outputData": True, "dateFrom": "2026-09-01",
            "dateTo": "2026-10-01", "fileName": "_",
        })
        self.assertTrue(response.released)

    async def test_single_days_leap_day_and_dst_keep_calendar_dates(self) -> None:
        for start in (date(2026, 3, 29), date(2026, 10, 25), date(2028, 2, 29)):
            with self.subTest(day=start):
                session = _Session([], [], [_Response(200, "https://api.example")])
                await self._authenticated_client(session).async_get_daily_profile(
                    1, start, start + timedelta(days=1)
                )
                payload = session.request_calls[0][2]["json"]
                self.assertEqual(payload["dateFrom"], start.isoformat())
                self.assertEqual(payload["dateTo"], start.isoformat())

    async def test_both_chunk_orders_cover_each_inclusive_api_day_once(self) -> None:
        start, end = date(2026, 9, 1), date(2026, 10, 14)
        for split in (calculation.profile_date_ranges, calculation.profile_date_ranges_backwards):
            with self.subTest(split=split.__name__):
                ranges = split(start, end)
                session = _Session([], [], [
                    _Response(200, "https://api.example") for _ in ranges
                ])
                client = self._authenticated_client(session)
                for first, stop in ranges:
                    await client.async_get_daily_profile(1, first, stop)
                requested_days = []
                for _, _, options in session.request_calls:
                    payload = options["json"]
                    first = date.fromisoformat(payload["dateFrom"])
                    last = date.fromisoformat(payload["dateTo"])
                    self.assertLessEqual((last - first).days + 1, 31)
                    requested_days.extend(
                        first + timedelta(days=n) for n in range((last - first).days + 1)
                    )
                self.assertEqual(len(requested_days), len(set(requested_days)))
                self.assertEqual(sorted(requested_days), [
                    start + timedelta(days=n) for n in range((end - start).days)
                ])

    async def test_invalid_calendar_ranges_never_make_http_requests(self) -> None:
        for first, stop in (
            (date(2026, 9, 1), date(2026, 9, 1)),
            (date(2026, 9, 2), date(2026, 9, 1)),
            (date(2026, 9, 1), date(2026, 10, 3)),
            ("2026-09-01", "2026-09-02"),
            (datetime(2026, 9, 1, tzinfo=UTC), date(2026, 9, 2)),
        ):
            with self.subTest(first=first, stop=stop):
                session = _Session([], [])
                with self.assertRaises(ValueError):
                    await self._authenticated_client(session).async_get_daily_profile(1, first, stop)
                self.assertEqual(session.request_calls, [])

    async def test_http_error_exposes_only_safe_code_field_and_period(self) -> None:
        response = _Response(400, "https://api.example", json_data={
            "type": "VALIDATION", "traceId": "sensitive-trace",
            "validationErrors": [
                {"code": "MAX_PERIOD_RANGE", "field": "dateTo", "value": "secret"},
                {"code": "PASSWORD_SECRET", "field": "password"},
                {"code": "NOT_FOUND", "field": "user@example.com"},
            ], "message": "secret access session_code user@example.com",
        })
        session = _Session([], [], [response])
        with self.assertRaises(api.EdcApiError) as raised:
            await self._authenticated_client(session).async_get_daily_profile(
                12345678, date(2026, 9, 1), date(2026, 10, 2)
            )
        message = str(raised.exception)
        for expected in ("HTTP 400", "/profiles-data/standard/overview",
                         "2026-09-01", "2026-10-01", "MAX_PERIOD_RANGE (dateTo)", "NOT_FOUND"):
            self.assertIn(expected, message)
        for secret in ("PASSWORD_SECRET", "secret", "access", "session_code",
                       "user@example.com", "12345678", "sensitive-trace"):
            self.assertNotIn(secret, message)
        self.assertTrue(response.released)

    async def test_bad_error_bodies_preserve_original_http_status(self) -> None:
        for body in (b"<html>secret</html>", b"\xff", b"[]",
                     b"x" * (api.ERROR_BODY_LIMIT + 1),
                     b"[" * 3000 + b"]" * 3000,
                     b'{"validationErrors": [{"code": [], "field": {}}]}'):
            with self.subTest(body_size=len(body)):
                response = _Response(503, "https://api.example", body=body)
                session = _Session([], [], [response] * 3)
                with self.assertRaisesRegex(api.EdcApiError, "HTTP 503") as raised:
                    await self._authenticated_client(session).async_get_groups()
                self.assertNotIn("secret", str(raised.exception))
                self.assertTrue(response.released)

    async def test_generic_error_code_is_supported_without_free_text(self) -> None:
        session = _Session([], [], [_Response(500, "https://api.example", json_data={
            "genericError": {"code": "INTERNAL_ERROR", "message": "password=secret"}
        })] * 3)
        with self.assertRaisesRegex(api.EdcApiError, "INTERNAL_ERROR") as raised:
            await self._authenticated_client(session).async_get_groups()
        self.assertNotIn("secret", str(raised.exception))

    async def test_error_body_read_timeout_does_not_hide_http_status(self) -> None:
        response = _Response(504, "https://api.example")
        async def failed_read(_size):
            raise TimeoutError("secret transport data")
        response.content.readexactly = failed_read
        session = _Session([], [], [response] * 3)
        with self.assertRaisesRegex(api.EdcApiError, "HTTP 504") as raised:
            await self._authenticated_client(session).async_get_groups()
        self.assertNotIn("secret", str(raised.exception))
        self.assertTrue(response.released)

    def test_unknown_paths_and_invalid_date_values_are_not_echoed(self) -> None:
        self.assertEqual(api._safe_request_context("GET", "/private/secret", {}), "")
        message = api._safe_request_context("POST", "/profiles-data/standard/overview", {
            "dateFrom": "password=secret", "dateTo": "2026-99-99", "sseId": "secret",
        })
        self.assertNotIn("secret", message)
        self.assertNotIn("2026-99-99", message)

    async def test_timeout_is_wrapped_without_credentials(self) -> None:
        session = _Session([], [], [TimeoutError("session_code=sensitive")] * 3)
        client = self._authenticated_client(session)

        with self.assertRaisesRegex(api.EdcApiError, "Spojení s EDC selhalo") as raised:
            await client.async_get_groups()

        self.assertNotIn("user@example.com", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("session_code", str(raised.exception))
        self.assertNotIn("sensitive", str(raised.exception))
        self.assertIsNone(raised.exception.__cause__)

    async def test_unauthorized_response_requires_reauthentication(self) -> None:
        session = _Session([], [], [_Response(401, "https://api.example")] * 2)
        client = self._authenticated_client(session)
        client._async_ensure_token = AsyncMock()

        with self.assertRaises(api.EdcAuthenticationError):
            await client.async_get_groups()

        self.assertIsNone(client._access_token)

    async def test_malformed_group_response_is_rejected(self) -> None:
        for payload in ({"bad": "shape"}, ["not-a-group"]):
            with self.subTest(payload=payload):
                session = _Session(
                    [], [], [_Response(200, "https://api.example", json_data=payload)]
                )
                client = self._authenticated_client(session)

                with self.assertRaisesRegex(api.EdcApiError, "neplatný seznam skupin"):
                    await client.async_get_groups()


if __name__ == "__main__":
    unittest.main()
