"""A01–A14/D01–D10: nezávislé poruchové vzorky a očekávané chování."""

from __future__ import annotations

import asyncio
import copy
import random
import unittest
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from tests.test_api import _Response, _Session, api
from tests.test_calculation import calculation


def interval_profile(minutes=(0, 15, 30, 45), day="2026-10-12"):
    """Čtyři nezávisle zadané kWh intervaly: spotřeba 10, síť 6, sdílení 4."""
    return {
        "valueColumns": [
            {"ean": "producer", "type": "D", "dir": "IN"},
            {"ean": "producer", "type": "D", "dir": "OUT"},
            {"ean": "target", "type": "O", "dir": "IN"},
            {"ean": "target", "type": "O", "dir": "OUT"},
        ],
        "content": [
            {
                "date": day,
                "start": f"12:{minute:02d}:00",
                "end": "13:00:00" if minute == 45 else f"12:{minute + 15:02d}:00",
                "values": [{"v": 1}, {"v": 0}, {"v": -2.5}, {"v": -1.5}],
            }
            for minute in minutes
        ],
    }


class ContractTests(unittest.TestCase):
    def test_A01_A02_generated_calendar_ranges(self):
        rng = random.Random(41013)
        for _ in range(100):
            start = date(2018, 1, 1) + timedelta(days=rng.randrange(7000))
            stop = start + timedelta(days=rng.randrange(1, 800))
            expected = {
                start + timedelta(days=index) for index in range((stop - start).days)
            }
            for split in (
                calculation.profile_date_ranges,
                calculation.profile_date_ranges_backwards,
            ):
                observed = []
                for first, end in split(start, stop):
                    payload = api.build_profile_request(1, first, end)
                    last = date.fromisoformat(payload["dateTo"])
                    self.assertLessEqual((last - first).days + 1, 31)
                    observed.extend(
                        first + timedelta(days=index)
                        for index in range((last - first).days + 1)
                    )
                self.assertEqual(set(observed), expected)
                self.assertEqual(len(observed), len(expected))

    def test_D01_empty_is_not_missing(self):
        for data in (
            {},
            {"content": None},
            {"content": ""},
            {"content": [None]},
            {"content": [], "valueColumns": None},
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                calculation.validate_profile_response(data)
        calculation.validate_profile_response({"content": []})
        calculation.validate_profile_response({"content": [], "valueColumns": []})

    def test_D02_compatible_fields_and_column_reordering(self):
        profile = interval_profile()
        profile["new_optional_metadata"] = {"ignored": True}
        profile["valueColumns"].reverse()
        for row in profile["content"]:
            row["values"].reverse()
        rows = calculation.parse_hourly_target_profiles(profile)
        self.assertEqual(float(rows[0].shared), 4)
        self.assertTrue(rows[0].complete)

    def test_D03_D04_missing_values_and_invalid_roles(self):
        for value in ("", True, "NaN", "Infinity", "1e9999"):
            profile = interval_profile()
            profile["content"][0]["values"][0]["v"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculation.parse_daily_profile(profile)
        for change in (
            "short_vector",
            "missing_direction",
            "unknown_role",
            "duplicate_column",
        ):
            profile = interval_profile()
            if change == "short_vector":
                profile["content"][0]["values"].pop()
            elif change == "missing_direction":
                profile["valueColumns"][0].pop("dir")
            elif change == "unknown_role":
                profile["valueColumns"][0]["type"] = "changed"
            else:
                profile["valueColumns"][1] = dict(profile["valueColumns"][0])
            with self.subTest(change=change), self.assertRaises(ValueError):
                calculation.validate_profile_response(profile)

    def test_null_is_missing_interval_not_zero_or_api_contract_change(self):
        profile = interval_profile()
        profile["content"][0]["values"][0]["v"] = None
        calculation.validate_profile_response(profile)
        self.assertEqual(calculation.missing_measurement_counts(profile), (1, 1))
        self.assertFalse(calculation.parse_daily_profile(profile)[0].complete)
        hours = calculation.parse_hourly_profile(profile)
        self.assertEqual(len(hours), 1)
        self.assertFalse(hours[0].complete)
        self.assertEqual(float(hours[0].shared), 3)
        self.assertTrue(
            all(
                not row.complete
                for row in calculation.parse_daily_target_profiles(profile)
            )
        )
        profile["content"] = [profile["content"][0]]
        self.assertEqual(calculation.parse_daily_profile(profile), ())
        self.assertEqual(calculation.parse_hourly_profile(profile), ())

    def test_missing_value_key_remains_schema_error(self):
        profile = interval_profile()
        profile["content"][0]["values"][0] = {"renamed": None}
        with self.assertRaises(ValueError):
            calculation.validate_profile_response(profile)

    def test_null_autumn_dst_interval_does_not_shift_second_fold(self):
        raw = interval_profile()
        raw["content"] = []
        for index, hour in enumerate([0, 1, 2, 2, *range(3, 24)]):
            raw["content"].append(
                {
                    "date": "2026-10-25",
                    "start": f"{hour:02d}:00:00",
                    "end": "02:00:00" if index == 2 else f"{hour + 1:02d}:00:00",
                    "values": [None if index == 2 else 1, 0, -2.5, -1.5],
                }
            )
        hours = calculation.parse_hourly_profile(
            raw, local_tz=ZoneInfo("Europe/Prague")
        )
        starts = {row.start for row in hours}
        self.assertNotIn(datetime(2026, 10, 25, 0, tzinfo=UTC), starts)
        self.assertIn(datetime(2026, 10, 25, 1, tzinfo=UTC), starts)
        self.assertEqual(len(hours), 24)
        self.assertFalse(calculation.parse_daily_profile(raw)[0].complete)

    def test_D05_daily_total_never_becomes_midnight_hour(self):
        profile = interval_profile((0,))
        profile["content"][0].update(start="00:00:00", end="24:00:00")
        self.assertEqual(calculation.profile_resolution(profile), "daily")
        self.assertEqual(calculation.parse_hourly_profile(profile), ())
        self.assertTrue(calculation.parse_daily_profile(profile)[0].complete)
        profile["content"][0].pop("end")
        self.assertEqual(calculation.profile_resolution(profile), "unknown")
        self.assertEqual(calculation.parse_hourly_profile(profile), ())

    def test_D07_partial_hour_is_not_complete_or_billable_day(self):
        profile = interval_profile((0, 15, 45))
        self.assertFalse(calculation.parse_hourly_profile(profile)[0].complete)
        rows = calculation.parse_daily_profile(profile)
        self.assertFalse(rows[0].complete)
        result = calculation.calculate_statistics(
            rows, calculation.Decimal(2), date(2026, 10, 13)
        )
        self.assertIsNone(result.latest_day)
        self.assertEqual(result.days, ())

    def test_D09_independent_energy_balance_and_coverage(self):
        hour = calculation.parse_hourly_profile(interval_profile())[0]
        self.assertEqual(float(hour.consumption), 10)
        self.assertEqual(float(hour.grid_purchase), 6)
        self.assertEqual(float(hour.shared), 4)
        self.assertEqual(float(hour.coverage), 40)
        self.assertEqual(hour.consumption, hour.grid_purchase + hour.shared)

    def test_D06_complete_dst_days_keep_23_and_25_unique_utc_hours(self):
        for day, starts, expected in (
            ("2026-03-29", [0, 1, *range(3, 24)], 23),
            ("2026-10-25", [0, 1, 2, 2, *range(3, 24)], 25),
        ):
            profile = interval_profile()
            profile["content"] = []
            for index, hour in enumerate(starts):
                end = (
                    3
                    if day == "2026-03-29" and hour == 1
                    else 2
                    if day == "2026-10-25" and index == 2
                    else hour + 1
                )
                profile["content"].append(
                    {
                        "date": day,
                        "start": f"{hour:02d}:00:00",
                        "end": f"{end:02d}:00:00",
                        "values": [{"v": 10}, {"v": 0}, {"v": -16}, {"v": -6}],
                    }
                )
            hours = calculation.parse_hourly_profile(
                profile, local_tz=ZoneInfo("Europe/Prague")
            )
            self.assertEqual(calculation.profile_resolution(profile), "hour")
            self.assertEqual(len(hours), expected)
            self.assertEqual(len({row.start for row in hours}), expected)
            self.assertTrue(all(row.complete for row in hours))
            days = calculation.parse_daily_profile(profile)
            self.assertTrue(days[0].complete)
            self.assertEqual(float(days[0].shared), expected * 10)
            profile["content"].pop()
            self.assertFalse(calculation.parse_daily_profile(profile)[0].complete)

    def test_A09_retry_after_seconds_dates_and_invalid_values(self):
        now = datetime(2026, 10, 14, tzinfo=UTC)
        for value in ("90", format_datetime(now + timedelta(seconds=90), usegmt=True)):
            self.assertEqual(api.retry_after(value, now), now + timedelta(seconds=90))
        for value in (
            "invalid",
            "-1",
            "9" * 128,
            format_datetime(now - timedelta(days=1)),
            None,
        ):
            self.assertIsNone(api.retry_after(value, now))

    def test_A13_foreign_login_target_is_rejected(self):
        for target in (
            "https://evil.example/login",
            "http://sso.portal.edc-cr.cz/login",
            "https://test@example.com/login",
        ):
            with self.assertRaises(api.EdcApiError) as raised:
                api.EdcApiClient._validate_login_target(target)
            self.assertNotIn("secret", str(raised.exception))
            self.assertEqual(raised.exception.category, "contract")

    def test_D04_unit_change_and_secret_token_error_are_rejected_safely(self):
        profile = interval_profile()
        profile["valueColumns"][0]["unit"] = "Wh"
        with self.assertRaises(ValueError):
            calculation.validate_profile_response(profile)
        client = api.EdcApiClient(_Session([], []), "private-user", "private-password")
        for lifetime in ("private-secret", True, float("inf"), -1):
            with self.assertRaises(api.EdcApiError) as raised:
                client._store_tokens(
                    {"access_token": "private-token", "expires_in": lifetime}
                )
            self.assertEqual(raised.exception.category, "contract")
            self.assertTrue(raised.exception.__suppress_context__)
            self.assertNotIn("private", str(raised.exception))


class ResilienceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sleep = self.enterContext(
            patch.object(api.asyncio, "sleep", new=AsyncMock())
        )

    def client(self, responses, state=None):
        session = _Session([], [], responses)
        client = api.EdcApiClient(session, "private-user", "private-password", state)
        client._store_tokens({"access_token": "private-token", "expires_in": 3600})
        return client, session

    async def test_A04_invalid_group_never_reaches_network(self):
        client, session = self.client([])
        for group in (True, 0, -1, "1", 1.5):
            with self.assertRaises(ValueError):
                await client.async_get_daily_profile(
                    group, date(2026, 10, 12), date(2026, 10, 13)
                )
        self.assertEqual(session.request_calls, [])

    async def test_A07_bad_request_is_not_retried_or_relogged_in(self):
        client, session = self.client(
            [_Response(400, "https://api.example", body=b"private-password")]
        )
        for _ in range(2):
            with self.assertRaises(api.EdcApiError) as raised:
                await client.async_get_groups()
            self.assertEqual(raised.exception.category, "validation")
            self.assertNotIn("private", str(raised.exception))
        self.assertEqual(len(session.request_calls), 1)
        self.assertEqual(session.post_calls, [])
        self.sleep.assert_not_awaited()

    async def test_A09_A11_shared_wait_survives_restore(self):
        state = api.ApiAccountState()
        state.persist = AsyncMock()
        response = _Response(429, "https://api.example")
        response.headers["Retry-After"] = "7200"
        client, _first_session = self.client([response], state)
        with self.assertRaises(api.EdcApiError) as raised:
            await client.async_get_groups()
        self.assertGreaterEqual(
            raised.exception.retry_at, datetime.now(UTC) + timedelta(seconds=7199)
        )
        restored = api.ApiAccountState()
        stored = state.persist.await_args.args[0]
        self.assertNotIn("private", str(stored))
        restored.restore(stored)
        second, session = self.client([], restored)
        with self.assertRaises(api.EdcApiError):
            await second.async_get_groups()
        self.assertEqual(session.request_calls, [])
        self.sleep.assert_not_awaited()
        self.assertTrue(response.released)

    async def test_A10_transport_retries_are_bounded_and_released(self):
        responses = [_Response(503, "https://api.example") for _ in range(3)]
        client, session = self.client(responses.copy())
        with self.assertRaises(api.EdcApiError):
            await client.async_get_groups()
        self.assertEqual(len(session.request_calls), 3)
        self.assertEqual(self.sleep.await_count, 2)
        self.assertTrue(all(item.released for item in responses))

    async def test_A10_cancellation_releases_account_lock(self):
        client, _session = self.client(
            [
                asyncio.CancelledError(),
                _Response(200, "https://api.example", json_data=[]),
            ]
        )
        with self.assertRaises(asyncio.CancelledError):
            await client.async_get_groups()
        self.assertFalse(client.account_state.lock.locked())
        self.assertEqual(await client.async_get_groups(), [])

    async def test_A08_expired_access_token_only_one_refresh(self):
        client, session = self.client(
            [
                _Response(401, "https://api.example"),
                _Response(200, "https://api.example", json_data=[]),
            ]
        )
        client._async_ensure_token = AsyncMock()
        self.assertEqual(await client.async_get_groups(), [])
        self.assertEqual(len(session.request_calls), 2)
        self.assertEqual(client._async_ensure_token.await_count, 2)

    async def test_A12_schema_change_blocks_without_zero_cache(self):
        client, session = self.client(
            [_Response(200, "https://api.example", json_data={"renamedContent": []})]
        )
        with self.assertRaises(api.EdcApiError) as raised:
            await client.async_get_daily_profile(
                1, date(2026, 10, 12), date(2026, 10, 13)
            )
        self.assertEqual(raised.exception.category, "contract")
        self.assertIsNotNone(raised.exception.retry_at)
        self.assertEqual(len(session.request_calls), 1)

    async def test_A08_refresh_limit_does_not_send_password(self):
        response = _Response(429, "https://sso.example/token")
        response.headers["Retry-After"] = "7200"
        session = _Session([], [response], [])
        client = api.EdcApiClient(session, "private-user", "private-password")
        client._refresh_token = "private-refresh"
        for _ in range(2):
            with self.assertRaises(api.EdcApiError) as raised:
                await client.async_get_groups()
            self.assertEqual(raised.exception.category, "rate_limit")
        self.assertEqual(len(session.post_calls), 1)
        self.assertEqual(session.get_calls, [])
        self.assertTrue(response.released)
        self.sleep.assert_not_awaited()

    async def test_A08_rejected_refresh_allows_one_supported_login(self):
        response = _Response(
            400, "https://sso.example/token", json_data={"error": "invalid_grant"}
        )
        session = _Session(
            [], [response], [_Response(200, "https://api.example", json_data=[])]
        )
        client = api.EdcApiClient(session, "private-user", "private-password")
        client._refresh_token = "private-refresh"
        client.async_login = AsyncMock(
            side_effect=lambda: client._store_tokens(
                {"access_token": "new", "expires_in": 3600}
            )
        )
        self.assertEqual(await client.async_get_groups(), [])
        client.async_login.assert_awaited_once()
        self.assertEqual(len(session.post_calls), 1)

    async def test_A13_mfa_and_bad_state_are_not_wrong_password(self):
        for page in ('"pageId": "login-otp.ftl"', '<div class="g-recaptcha"></div>'):
            with self.assertRaises(api.EdcApiError) as raised:
                client = api.EdcApiClient(
                    _Session([_Response(200, "https://sso.example", text=page)], []),
                    "private-user",
                    "private-password",
                )
                await client.async_get_groups()
            self.assertEqual(raised.exception.category, "user_action")
            self.assertNotIsInstance(raised.exception, api.EdcAuthenticationError)
        with self.assertRaises(api.EdcApiError) as raised:
            api.EdcApiClient._validate_authorization_redirect(
                {"state": ["wrong"]}, "expected"
            )
        self.assertEqual(raised.exception.category, "contract")

    async def test_A11_persistence_failure_keeps_monotonic_wait(self):
        state = api.ApiAccountState()
        state.persist = AsyncMock(side_effect=OSError("private-error"))
        error = api.EdcApiError("safe", category="rate_limit")
        await state.block("scope", error)
        self.assertTrue(state.persistence_failed)
        state.restore({"account": {"category": [], "until": "private-invalid"}})
        # Simulovat posun wall clock vpřed: uložený UTC termín již vypršel,
        # monotónní zbývající čas ale musí dále zakazovat požadavek.
        state.blocks["account"] = (datetime.now(UTC) - timedelta(hours=1), "rate_limit")
        with (
            patch.object(
                api.time, "monotonic", return_value=state.deadlines["account"] - 60
            ),
            self.assertRaises(api.EdcApiError),
        ):
            state.check("other")
        self.assertFalse(state.lock.locked())

    async def test_A11_concurrent_group_waits_and_obeys_first_failure(self):
        """Druhá skupina už čeká: nově uložený 429 zabrání jejímu HTTP volání."""
        state = api.ApiAccountState()
        first, _ = self.client([], state)
        second, _ = self.client([], state)
        started, queued, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def first_read(*_args):
            started.set()
            await release.wait()
            raise api.EdcApiError("safe", category="rate_limit", status=429)

        async def second_read():
            queued.set()
            return await second.async_get_daily_profile(
                2, date(2026, 10, 12), date(2026, 10, 13)
            )

        first._request_once = AsyncMock(side_effect=first_read)
        second._request_once = AsyncMock()
        task1 = asyncio.create_task(first.async_get_groups())
        await started.wait()
        task2 = asyncio.create_task(second_read())
        await queued.wait()
        try:
            second._request_once.assert_not_awaited()
        finally:
            release.set()
        results = await asyncio.gather(task1, task2, return_exceptions=True)
        self.assertTrue(all(isinstance(item, api.EdcApiError) for item in results))
        second._request_once.assert_not_awaited()
        self.assertFalse(state.lock.locked())

    async def test_original_http_failure_is_logged_once_and_restored_with_details(self):
        state = api.ApiAccountState()
        state.persist = AsyncMock()
        response = _Response(
            400,
            "https://api.example",
            body=b'{"validationErrors":[{"code":"MAX_PERIOD_RANGE","field":"dateTo","message":"private-secret"}]}',
        )
        client, session = self.client([response], state)
        with self.assertLogs("_edc_sharing_test.api_policy", level="WARNING") as logs:
            for _ in range(3):
                with self.assertRaises(api.EdcApiError):
                    await client.async_get_daily_profile(
                        1, date(2026, 10, 12), date(2026, 10, 13)
                    )
        self.assertEqual(len(logs.output), 1)
        self.assertIn("HTTP=400", logs.output[0])
        self.assertIn("MAX_PERIOD_RANGE (dateTo)", logs.output[0])
        self.assertNotIn("private", str(logs.output))
        stored = state.persist.await_args.args[0]
        self.assertEqual(
            stored["last_failure"]["validation_details"], "MAX_PERIOD_RANGE (dateTo)"
        )
        self.assertNotIn("private", str(stored))
        restored = api.ApiAccountState()
        restored.restore(stored)
        second, second_session = self.client([], restored)
        with self.assertRaises(api.EdcApiError) as raised:
            await second.async_get_daily_profile(
                1, date(2026, 10, 12), date(2026, 10, 13)
            )
        self.assertTrue(raised.exception.waiting)
        self.assertEqual(second.last_status, 400)
        self.assertEqual(second.last_failure_category, "validation")
        self.assertIn("MAX_PERIOD_RANGE (dateTo)", str(raised.exception))
        self.assertEqual(len(session.request_calls), 1)
        self.assertEqual(second_session.request_calls, [])

    async def test_schema_wait_is_short_local_and_limited_to_exact_period(self):
        state = api.ApiAccountState()
        state.persist = AsyncMock()
        client, session = self.client(
            [
                _Response(200, "https://api.example", json_data={"renamedContent": []}),
                _Response(
                    200,
                    "https://api.example",
                    json_data=interval_profile(day="2026-10-13"),
                ),
            ],
            state,
        )
        with self.assertRaises(api.EdcApiError) as raised:
            await client.async_get_daily_profile(
                1, date(2026, 10, 12), date(2026, 10, 13)
            )
        self.assertEqual(raised.exception.phase, "profile_validation")
        self.assertLessEqual(
            (raised.exception.retry_at - datetime.now(UTC)).total_seconds(), 900
        )
        self.assertEqual(state.last_failure["reason_code"], "profile_lists")
        self.assertEqual(state.last_failure["http_status"], 200)
        await client.async_get_daily_profile(1, date(2026, 10, 13), date(2026, 10, 14))
        with self.assertRaises(api.EdcApiError) as waiting:
            await client.async_get_daily_profile(
                1, date(2026, 10, 12), date(2026, 10, 13)
            )
        self.assertTrue(waiting.exception.waiting)
        self.assertIn("strukturu profilových seznamů", str(waiting.exception))
        self.assertEqual(len(session.request_calls), 2)
        self.assertEqual(state.last_failure["reason_code"], "profile_lists")

    async def test_null_measurement_does_not_create_contract_quarantine(self):
        raw = interval_profile()
        raw["content"][0]["values"][0]["v"] = None
        client, _ = self.client([_Response(200, "https://api.example", json_data=raw)])
        result = await client.async_get_daily_profile(
            1, date(2026, 10, 12), date(2026, 10, 13)
        )
        self.assertEqual(client.account_state.blocks, {})
        self.assertIsNone(client.account_state.last_failure)
        self.assertFalse(calculation.parse_hourly_profile(result)[0].complete)

    async def test_server_retry_after_is_not_shortened_by_profile_policy(self):
        state = api.ApiAccountState()
        state.persist = AsyncMock()
        response = _Response(403, "https://api.example")
        response.headers["Retry-After"] = "86400"
        client, session = self.client([response], state)
        with self.assertRaises(api.EdcApiError) as raised:
            await client.async_get_daily_profile(
                1, date(2026, 10, 12), date(2026, 10, 13)
            )
        self.assertGreaterEqual(
            (raised.exception.retry_at - datetime.now(UTC)).total_seconds(), 86399
        )
        self.assertEqual(state.last_failure["wait_source"], "server_retry_after")
        with self.assertRaises(api.EdcApiError):
            await client.async_get_daily_profile(
                1, date(2026, 10, 13), date(2026, 10, 14)
            )
        self.assertEqual(len(session.request_calls), 1)

    async def test_legacy_wait_logs_unknown_origin_once_without_extending(self):
        state = api.ApiAccountState()
        scope = state.scope("/profiles-data/standard/overview", {"sseId": 1})
        until = datetime.now(UTC) + timedelta(hours=6)
        state.restore({scope: {"until": until.isoformat(), "category": "contract"}})
        with self.assertLogs("_edc_sharing_test.api_policy", level="WARNING") as logs:
            for _ in range(3):
                with self.assertRaises(api.EdcApiError):
                    state.check(scope)
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(state.blocks[scope][0], until)
        self.assertEqual(state.last_failure["wait_source"], "legacy_unknown")
        self.assertEqual(state.last_failure["reason_code"], "legacy")

    async def test_expired_wait_keeps_cause_and_logs_one_verified_recovery(self):
        state = api.ApiAccountState()
        state.persist = AsyncMock()
        payload = api.build_profile_request(1, date(2026, 10, 12), date(2026, 10, 13))
        scope = state.scope("/profiles-data/standard/overview", payload, period=True)
        await state.block(
            scope,
            api.EdcApiError(
                "EDC změnilo strukturu profilových seznamů.",
                category="contract",
                phase="profile_validation",
                status=200,
            ),
        )
        stored = copy.deepcopy(state.persist.await_args.args[0])
        stored[scope]["until"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        restored = api.ApiAccountState()
        restored.persist = AsyncMock()
        restored.restore(stored)
        self.assertEqual(restored.blocks, {})
        self.assertEqual(restored.last_failure["reason_code"], "profile_lists")
        client, _ = self.client(
            [_Response(200, "https://api.example", json_data=interval_profile())],
            restored,
        )
        with self.assertLogs("_edc_sharing_test.api_policy", level="INFO") as logs:
            await client.async_get_daily_profile(
                1, date(2026, 10, 12), date(2026, 10, 13)
            )
        self.assertEqual(len(logs.output), 1)
        self.assertIn("recovered_at", restored.last_failure)
        self.assertIn(
            "recovered_at", restored.persist.await_args.args[0]["last_failure"]
        )

    async def test_restore_does_not_trust_free_text_or_malformed_values(self):
        state = api.ApiAccountState()
        state.restore(
            {
                "last_failure": {
                    "category": "contract",
                    "reason_code": ["private-secret"],
                    "reason": "private-secret",
                    "phase": {},
                    "http_status": True,
                    "request_context": "private-secret",
                    "validation_details": "NOT_FOUND (private-secret)",
                    "failed_at": "private-secret",
                }
            }
        )
        self.assertNotIn("private", str(state.last_failure))
        self.assertEqual(state.last_failure["reason_code"], "legacy")
        self.assertIsNone(state.last_failure["http_status"])
        self.assertNotIn("failed_at", state.last_failure)

    async def test_confirmed_bad_credentials_are_recorded_without_retry_block(self):
        state = api.ApiAccountState()
        state.persist = AsyncMock()
        client, _ = self.client([], state)
        client._request_once = AsyncMock(
            side_effect=api.EdcAuthenticationError("Neplatné jméno nebo heslo EDC.")
        )
        with self.assertRaises(api.EdcAuthenticationError):
            await client.async_get_groups()
        self.assertEqual(state.blocks, {})
        self.assertEqual(state.last_failure["reason_code"], "credentials")
        self.assertEqual(state.last_failure["phase"], "authentication")
        self.assertNotIn("private", str(state.persist.await_args.args[0]))


if __name__ == "__main__":
    unittest.main()
