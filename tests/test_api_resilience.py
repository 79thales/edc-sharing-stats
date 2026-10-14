"""A01–A14/D01–D10: nezávislé poruchové vzorky a očekávané chování."""

from __future__ import annotations

import asyncio
import random
import unittest
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock, patch

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
        for value in (None, "", True, "NaN", "Infinity", "1e9999"):
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


if __name__ == "__main__":
    unittest.main()
