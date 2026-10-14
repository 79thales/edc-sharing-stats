"""Přesný krok login chyby bez živého EDC, druhého loginu či soukromých dat.

HTTP odpovědi odpovídají rozdílným hranicím OIDC. Ověřujeme skutečný průchod
klienta, nikoli jen ruční sestavení výjimky: krok musí přežít uložení, restart
i místní čekání. Stav ani URL s tajnými query parametry se nesmí exportovat.
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

        Bez Retry-After zůstává současná místní lhůta šest hodin. Test tuto
        politiku dokumentuje; netvrdí, že ji vyžaduje server nebo že řeší 403.
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
                self.assertEqual(stored["last_failure"]["wait_source"], "local_policy")
                until = datetime.fromisoformat(stored["account"]["until"])
                self.assertAlmostEqual(
                    (until - datetime.now(UTC)).total_seconds(), 21600, delta=2
                )
                self.assertFalse(session.get_responses)
                self.assertFalse(session.post_responses)
                self.assertFalse(session.request_calls)
                restored = api.ApiAccountState()
                restored.restore(stored)
                second_session = _Session([], [])
                second = api.EdcApiClient(
                    second_session, "private-user", "private-password", restored
                )
                with self.assertRaises(api.EdcApiError) as waiting:
                    await second.async_get_groups()
                self.assertTrue(waiting.exception.waiting)
                self.assertEqual(waiting.exception.authentication_step, step)
                self.assertEqual(restored.blocks["account"][0], until)
                self.assertFalse(
                    second_session.get_calls
                    + second_session.post_calls
                    + second_session.request_calls
                )
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
