"""Tests for the EDC Keycloak login page helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


try:
    import aiohttp  # noqa: F401
except ModuleNotFoundError:
    aiohttp_stub = types.ModuleType("aiohttp")

    class ClientError(Exception):
        pass

    class ClientSession:
        pass

    aiohttp_stub.ClientError = ClientError
    aiohttp_stub.ClientSession = ClientSession
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


class _Response:
    def __init__(
        self,
        status: int,
        url: str,
        *,
        location: str = "",
        text: str = "",
        json_data: dict | None = None,
    ) -> None:
        self.status = status
        self.url = url
        self.headers = {"Location": location} if location else {}
        self._text = text
        self._json_data = json_data or {}

    async def text(self) -> str:
        return self._text

    async def json(self) -> dict:
        return self._json_data


class _Session:
    def __init__(self, get_responses: list[_Response], post_responses: list[_Response]) -> None:
        self.get_responses = get_responses
        self.post_responses = post_responses
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []

    async def get(self, url: str, **kwargs) -> _Response:
        self.get_calls.append((url, kwargs))
        return self.get_responses.pop(0)

    async def post(self, url: str, **kwargs) -> _Response:
        self.post_calls.append((url, kwargs))
        return self.post_responses.pop(0)


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
        self.assertEqual(len(session.post_calls), 1)
        self.assertEqual(session.post_calls[0][1]["data"]["code"], "auth-code")

    async def test_session_code_is_not_mistaken_for_authorization_code(self) -> None:
        login_page = _Response(200, "https://sso.example/login", text="login page")
        session = _Session([login_page], [])
        client = api.EdcApiClient(session, "user@example.com", "secret")
        response = _Response(
            302,
            "https://sso.example/auth",
            location="https://sso.example/login?session_code=abc",
        )

        final_response, location = await client._async_follow_login_redirects(response)

        self.assertIs(final_response, login_page)
        self.assertEqual(location, "")
        self.assertEqual(len(session.get_calls), 1)

    async def test_missing_login_action_is_technical_error(self) -> None:
        session = _Session(
            [_Response(200, "https://sso.example/auth", text="login page")], []
        )
        client = api.EdcApiClient(session, "user@example.com", "secret")

        with patch.object(
            api,
            "_base64url",
            side_effect=["verifier", "challenge", "state", "nonce"],
        ):
            with self.assertRaises(api.EdcApiError) as raised:
                await client.async_login()

        self.assertNotIsInstance(raised.exception, api.EdcAuthenticationError)


if __name__ == "__main__":
    unittest.main()
