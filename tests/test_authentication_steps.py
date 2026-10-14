"""Přesný krok login chyby bez živého EDC, druhého loginu či soukromých dat.

HTTP odpovědi odpovídají rozdílným hranicím OIDC. Ověřujeme skutečný průchod
klienta, nikoli jen ruční sestavení výjimky: krok musí přežít uložení, restart
i restart bez místní šestihodinové blokace. Stav ani URL s tajnými query
parametry se nesmí exportovat.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from tests.test_api import _Response, _Session, api

SSO = "https://sso.example/auth"
LOGIN = SSO + "/login?session_code=private-session"
CALLBACK = "https://portal.edc-cr.cz/?code=private-code&state=state"
PAGE = '<form id="kc-form-login" action="' + LOGIN + '"></form>'


class AuthenticationStepTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch.object(api, "AUTHORITY_URL", SSO))
        self.enterContext(
            patch.object(
                api,
                "_base64url",
                side_effect=lambda _value: "state",
            )
        )
        self.enterContext(patch.object(api.asyncio, "sleep", new=AsyncMock()))

    async def test_http_403_identifies_each_operation_and_survives_restart(self):
        """Stejný status ze šesti míst má různý krok a nikdy další HTTP pokus.

        Bez Retry-After se pouze uloží chyba. Nový pokus patří plánovači,
        nikoli okamžitému opakování požadavku v rámci této operace.
        """
        cases = (
            ("authorization_get", [_Response(403, SSO)], []),
            (
                "authorization_redirect_get",
                [_Response(302, SSO, location=LOGIN), _Response(403, LOGIN)],
                [],
            ),
            (
                "credentials_post",
                [_Response(200, SSO, text=PAGE)],
                [_Response(403, LOGIN)],
            ),
            (
                "credentials_redirect_get",
                [_Response(200, SSO, text=PAGE), _Response(403, LOGIN)],
                [_Response(302, LOGIN, location=LOGIN)],
            ),
            (
                "code_exchange_post",
                [_Response(302, SSO, location=CALLBACK)],
                [_Response(403, SSO + "/token")],
            ),
            ("refresh_token_post", [], [_Response(403, SSO + "/token")]),
        )
        for step, get_responses, post_responses in cases:
            with self.subTest(step=step):
                session = _Session(get_responses, post_responses)
                state = api.ApiAccountState()
                state.persist = AsyncMock()
                client = api.EdcApiClient(
                    session, "private-user", "private-password", state
                )
                if step == "refresh_token_post":
                    client._refresh_token = "private-refresh"
                with (
                    self.assertLogs(
                        "_edc_sharing_test.api_policy", level="WARNING"
                    ) as logs,
                    self.assertRaises(api.EdcApiError) as raised,
                ):
                    await client.async_get_groups()
                self.assertEqual(raised.exception.authentication_step, step)
                self.assertEqual(raised.exception.phase, "authentication")
                self.assertEqual(raised.exception.status, 403)
                self.assertIn("krok=" + step, logs.output[0])
                self.assertEqual(len(logs.output), 1)
                stored = state.persist.await_args.args[0]
                self.assertEqual(stored["last_failure"]["authentication_step"], step)
                self.assertEqual(stored["last_failure"]["reason_code"], "http")
                self.assertEqual(stored["last_failure"]["wait_source"], "not_scheduled")
                self.assertNotIn("account", stored)
                self.assertIsNone(raised.exception.retry_at)
                self.assertFalse(session.get_responses)
                self.assertFalse(session.post_responses)
                self.assertFalse(session.request_calls)
                restored = api.ApiAccountState()
                restored.restore(stored)
                restored.check(restored.scope("/sharing-groups", None))
                self.assertEqual(restored.blocks, {})
                self.assertEqual(restored.diagnostic_failure()["authentication_step"], step)
                exported = str((stored, restored.diagnostic_failure(), logs.output))
                self.assertNotIn("private", exported)
                self.assertNotIn("https://", exported)

    async def test_authorization_callback_exchanges_token_without_redirect_get(self):
        """Callback není další GET: selhání tokenu patří pouze code exchange."""
        session = _Session(
            [_Response(200, SSO, text=PAGE)],
            [_Response(302, LOGIN, location=CALLBACK), _Response(403, SSO + "/token")],
        )
        client = api.EdcApiClient(session, "private-user", "private-password")
        with self.assertRaises(api.EdcApiError) as raised:
            await client.async_login()
        self.assertEqual(raised.exception.authentication_step, "code_exchange_post")
        self.assertEqual(len(session.get_calls), 1)
        self.assertEqual(len(session.post_calls), 2)

    async def test_timeout_on_redirect_preserves_redirect_step(self):
        session = _Session(
            [_Response(200, SSO, text=PAGE)], [_Response(302, LOGIN, location=LOGIN)]
        )
        original_get = session.get

        async def get(url, **kwargs):
            if url == LOGIN:
                raise TimeoutError("private transport details")
            return await original_get(url, **kwargs)

        session.get = get
        client = api.EdcApiClient(session, "private-user", "private-password")
        with self.assertRaises(api.EdcApiError) as raised:
            await client.async_login()
        self.assertEqual(
            raised.exception.authentication_step, "credentials_redirect_get"
        )
        self.assertEqual(raised.exception.category, "unavailable")
        self.assertNotIn("private", str(raised.exception))
        self.assertEqual(len(session.post_calls), 1)

    async def test_known_credentials_error_keeps_safe_reason_and_step(self):
        session = _Session(
            [_Response(200, SSO, text=PAGE)],
            [
                _Response(
                    200,
                    LOGIN,
                    text='"message":{"summary":"Neplatné jméno nebo heslo.","type":"error"}',
                )
            ],
        )
        client = api.EdcApiClient(session, "private-user", "private-password")
        with self.assertRaises(api.EdcAuthenticationError) as raised:
            await client.async_get_groups()
        self.assertEqual(raised.exception.authentication_step, "credentials_post")
        self.assertEqual(
            client.account_state.last_failure["reason_code"], "credentials"
        )
        self.assertEqual(client.account_state.blocks, {})

    async def test_restore_removes_only_known_local_login_403_wait(self):
        """Starý místní login blok zmizí; server a ostatní ochrany přežijí.

        Migrace zachová důvod a krok, nevymyslí úspěch a po uložení/restartu
        blok znovu nevznikne. Žádný živý přihlašovací požadavek se neposílá.
        """
        until = datetime.now(UTC) + timedelta(hours=6)
        cases = (
            ("account", "authentication", "permission", 403, "local_policy", True),
            ("account", "authentication", "permission", 403, "server_retry_after", False),
            ("account", "authentication", "permission", 403, "legacy_unknown", False),
            ("a" * 64, "read", "permission", 403, "local_policy", False),
            ("account", "authentication", "user_action", 403, "local_policy", False),
            ("account", "authentication", "rate_limit", 429, "local_policy", False),
        )
        for key, phase, category, status, source, removed in cases:
            with self.subTest(phase=phase, category=category, source=source):
                record = {
                    "reason_code": "http", "category": category, "phase": phase,
                    "http_status": status, "wait_source": source,
                    "authentication_step": "credentials_post",
                    "retry_at": until.isoformat(),
                }
                state = api.ApiAccountState()
                state.persist = AsyncMock()
                state.restore({key: {**record, "until": until.isoformat()}, "last_failure": record})
                self.assertEqual(key not in state.blocks, removed)
                self.assertEqual(state.last_failure["http_status"], status)
                self.assertNotIn("recovered_at", state.last_failure)
                if removed:
                    state.check("a" * 64)
                    self.assertNotIn("retry_at", state.last_failure)
                    self.assertEqual(state.last_failure["wait_source"], "not_scheduled")
                else:
                    with self.assertRaises(api.EdcApiError) as waiting:
                        state.check(key)
                    self.assertTrue(waiting.exception.waiting)
                    self.assertEqual(state.blocks[key][0], until)
                await state._save()
                restored = api.ApiAccountState()
                restored.restore(state.persist.await_args.args[0])
                self.assertEqual(key not in restored.blocks, removed)

    async def test_server_retry_after_remains_authoritative_for_authentication(self):
        response = _Response(403, SSO)
        response.headers["Retry-After"] = "86400"
        state = api.ApiAccountState()
        client = api.EdcApiClient(
            _Session([response], []), "private-user", "private-password", state
        )
        with self.assertRaises(api.EdcApiError) as raised:
            await client.async_get_groups()
        self.assertGreater(
            raised.exception.retry_at, datetime.now(UTC) + timedelta(seconds=86398)
        )
        self.assertEqual(state.last_failure["wait_source"], "server_retry_after")

    def test_old_and_untrusted_records_cannot_invent_a_step(self):
        for value in (
            None,
            "https://private-secret/token",
            ["private-secret"],
            {"private": True},
        ):
            state = api.ApiAccountState()
            state.restore(
                {
                    "last_failure": {
                        "category": "permission",
                        "phase": "authentication",
                        "authentication_step": value,
                    }
                }
            )
            self.assertIsNone(state.diagnostic_failure()["authentication_step"])
            self.assertNotIn("private", str(state.diagnostic_failure()))


if __name__ == "__main__":
    unittest.main()
