"""Ověřit skutečný důvod odmítnutí bez úniku obsahu EDC odpovědi."""

import copy
import unittest
from datetime import date
from unittest.mock import AsyncMock

from tests.test_api import _Session, api
from tests.test_profile_times import minute_profile


class TimeDiagnosticTests(unittest.TestCase):
    def test_unsupported_seconds_and_mixed_resolution_are_visible(self):
        raw = minute_profile()
        raw["content"][0]["end"] = "12:14:59"
        original = copy.deepcopy(raw)
        summary = api._safe_profile_time_summary(raw)
        self.assertEqual(summary["row_resolutions"], {"unknown": 1, "quarter_hour": 3})
        self.assertEqual(summary["samples"][0]["end"], "12:14:59")
        self.assertEqual(raw, original)
        raw["content"][0].pop("start")
        self.assertEqual(api._safe_profile_time_summary(raw)["row_resolutions"]["daily"], 1)

    def test_private_strings_and_columns_never_reach_output(self):
        raw = minute_profile()
        raw["valueColumns"][0]["ean"] = "private-ean"
        raw["content"][0].update(start="private-token", end={"private-password": "private-user"})
        raw["content"][0]["values"] = [123456789]
        summary = api._safe_profile_time_summary(raw)
        for private in ("private-ean", "private-token", "private-password", "private-user", "123456789"):
            self.assertNotIn(private, str(summary))
        self.assertEqual(summary["samples"][0]["start"], "<str>")
        self.assertEqual(summary["samples"][0]["end"], "<dict>")

    def test_summary_is_bounded_and_keeps_final_row(self):
        raw = minute_profile()
        row = copy.deepcopy(raw["content"][0])
        row["end"] = "12:14:59"
        raw["content"] = [copy.deepcopy(row) for _ in range(5000)]
        summary = api._safe_profile_time_summary(raw)
        self.assertEqual(summary["rows"], 5000)
        self.assertEqual(summary["inspected_rows"], 4096)
        self.assertLessEqual(len(summary["samples"]), 6)
        self.assertIn(4999, [sample["row_index"] for sample in summary["samples"]])


class TimeDiagnosticApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_logs_time_and_still_rejects_contract_without_retry(self):
        raw = minute_profile()
        raw["content"][0]["end"] = "12:14:59"
        client = api.EdcApiClient(_Session([], [], []), "private-user", "private-password")
        client._request = AsyncMock(return_value=raw)
        client.last_status = 200
        with (
            self.assertLogs(api.LOGGER, level="ERROR") as logs,
            self.assertRaises(api.EdcApiError) as raised,
        ):
            await client.async_get_daily_profile(1, date(2026, 10, 13), date(2026, 10, 14))
        self.assertIn("12:14:59", str(logs.output))
        self.assertNotIn("private-user", str(logs.output))
        self.assertNotIn("private-password", str(logs.output))
        self.assertEqual(raised.exception.category, "contract")
        self.assertIsNotNone(raised.exception.retry_at)
        client._request.assert_awaited_once()

    async def test_valid_profile_has_no_extra_error_log(self):
        client = api.EdcApiClient(_Session([], [], []), "private-user", "private-password")
        client._request = AsyncMock(return_value=minute_profile())
        with self.assertNoLogs(api.LOGGER, level="ERROR"):
            await client.async_get_daily_profile(1, date(2026, 10, 13), date(2026, 10, 14))
