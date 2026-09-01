"""Tests for the EDC Keycloak login page helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest


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


if __name__ == "__main__":
    unittest.main()
