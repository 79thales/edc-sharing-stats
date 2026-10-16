"""Syntetické profily: chybějící den není nula ani důkaz platnosti skupiny."""

import copy
import unittest
from datetime import date

from tests.test_api_resilience import interval_profile
from tests.test_calculation import calculation


class HistoryGapTests(unittest.TestCase):
    """Ověřit klasifikaci kalendářních mezer nezávisle na HA a úložišti."""

    def test_complete_zero_day_is_data_but_absent_day_is_pending(self):
        raw = interval_profile()
        raw["content"] = [{"date": "2026-10-12", "values": [0, 0, 0, 0]}]
        days = calculation.parse_daily_profile(raw)
        self.assertEqual(calculation.history_profile_gaps(
            raw, date(2026, 10, 12), date(2026, 10, 14), days,
        ), {date(2026, 10, 13): "missing_day"})
        self.assertTrue(days[0].complete)

    def test_partial_and_all_null_days_are_distinct_from_absent_days(self):
        raw = interval_profile()
        missing = copy.deepcopy(raw["content"][0])
        missing.update(date="2026-10-13", values=[None] * 4)
        raw["content"].append(missing)
        self.assertEqual(calculation.history_profile_gaps(
            raw, date(2026, 10, 12), date(2026, 10, 15),
            calculation.parse_daily_profile(raw),
        ), {
            date(2026, 10, 12): "incomplete_day",
            date(2026, 10, 13): "missing_measurements",
            date(2026, 10, 14): "missing_day",
        })

    def test_empty_profile_does_not_prove_start_of_sharing(self):
        raw = {"content": []}
        self.assertEqual(calculation.history_profile_gaps(
            raw, date(2026, 5, 31), date(2026, 6, 2), (),
        ), {date(2026, 5, 31): "missing_day", date(2026, 6, 1): "missing_day"})


if __name__ == "__main__":
    unittest.main()
