"""Tests for standalone EDC calculation logic."""

from datetime import date
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).parents[1]
if not (REPOSITORY_ROOT / "custom_components").is_dir():
    REPOSITORY_ROOT = Path(__file__).parents[2] / "home_assistant"
MODULE_PATH = REPOSITORY_ROOT / "custom_components" / "edc_sharing" / "calculation.py"
SPEC = importlib.util.spec_from_file_location("edc_calculation", MODULE_PATH)
calculation = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = calculation
SPEC.loader.exec_module(calculation)


class CalculationTests(unittest.TestCase):
    def test_two_month_range_is_split_at_31_days(self) -> None:
        self.assertEqual(
            calculation.two_calendar_month_start(date(2026, 9, 2)),
            date(2026, 8, 1),
        )
        self.assertEqual(
            calculation.profile_date_ranges(date(2026, 8, 1), date(2026, 9, 3)),
            (
                (date(2026, 8, 1), date(2026, 9, 1)),
                (date(2026, 9, 1), date(2026, 9, 3)),
            ),
        )

    def test_empty_profile_is_a_valid_partial_result(self) -> None:
        self.assertEqual(calculation.parse_daily_profile({"content": []}), ())

    def test_extracts_multiple_sharing_and_target_eans(self) -> None:
        response = {
            "valueColumns": [
                {"ean": "producer-1", "type": "D", "dir": "IN"},
                {"ean": "producer-1", "type": "D", "dir": "OUT"},
                {"ean": "producer-2", "type": "D", "dir": "IN"},
                {"ean": "consumer-1", "type": "O", "dir": "IN"},
                {"ean": "consumer-2", "type": "O", "dir": "OUT"},
            ]
        }

        self.assertEqual(
            calculation.extract_eans(response),
            (
                calculation.EanInfo("producer-1", "sharing"),
                calculation.EanInfo("producer-2", "sharing"),
                calculation.EanInfo("consumer-1", "target"),
                calculation.EanInfo("consumer-2", "target"),
            ),
        )

    def test_daily_monthly_and_profit(self) -> None:
        response = {
            "valueColumns": [
                {"ean": "111", "type": "D", "dir": "IN"},
                {"ean": "111", "type": "D", "dir": "OUT"},
                {"ean": "222", "type": "O", "dir": "IN"},
                {"ean": "222", "type": "O", "dir": "OUT"},
            ],
            "content": [
                {"date": "2026-09-01", "values": [{"v": 10}, {"v": 4}, {"v": -8}, {"v": -2}]},
                {"date": "2026-08-31", "values": [{"v": 5}, {"v": 2}, {"v": -4}, {"v": -1}]},
            ],
        }
        result = calculation.calculate_profile(response, Decimal("2.20"), date(2026, 9, 1))
        self.assertEqual(result.today.shared, Decimal("6"))
        self.assertEqual(result.latest.shared, Decimal("6"))
        self.assertEqual(result.latest_day, date(2026, 9, 1))
        self.assertEqual(result.today.coverage, Decimal("75"))
        self.assertEqual(result.month_shared, Decimal("6"))
        self.assertEqual(result.month_revenue, Decimal("13.20"))
        self.assertEqual(result.month_unused, Decimal("4"))

    def test_missing_roles_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            calculation.calculate_profile(
                {"valueColumns": [{"ean": "111", "type": "D", "dir": "IN"}], "content": [{"date": "2026-09-01", "values": [{"v": 1}]}]},
                Decimal("2"),
                date(2026, 9, 1),
            )

    def test_real_edc_sign_convention(self) -> None:
        """Producer values are positive and consumer values negative in EDC."""
        response = {
            "valueColumns": [
                {"ean": "859182400708995788", "type": "D", "dir": "IN"},
                {"ean": "859182400708995788", "type": "D", "dir": "OUT"},
                {"ean": "859182400701870518", "type": "O", "dir": "IN"},
                {"ean": "859182400701870518", "type": "O", "dir": "OUT"},
            ],
            "content": [{
                "date": "2026-08-03",
                "values": [{"v": 12.22}, {"v": 7.43}, {"v": -12.43}, {"v": -7.64}],
            }],
        }
        result = calculation.calculate_profile(response, Decimal("2.20"), date(2026, 8, 3))
        self.assertEqual(result.today.shared, Decimal("4.79"))
        self.assertEqual(result.today.grid_purchase, Decimal("7.64"))
        self.assertEqual(result.today.unused_overflow, Decimal("7.43"))
        self.assertEqual(result.today.consistency_difference, Decimal("0.00"))
        self.assertEqual(result.today_revenue, Decimal("10.5380"))

    def test_quarter_hour_rows_are_aggregated_into_one_day(self) -> None:
        """The EDC overview may return multiple intervals for one DAILY request."""
        response = {
            "valueColumns": [
                {"ean": "producer", "type": "D", "dir": "IN"},
                {"ean": "producer", "type": "D", "dir": "OUT"},
                {"ean": "consumer", "type": "O", "dir": "IN"},
                {"ean": "consumer", "type": "O", "dir": "OUT"},
            ],
            "content": [
                {
                    "date": "2026-08-04T00:00:00",
                    "start": "00:00:00",
                    "values": [{"v": 0.01}, {"v": 0}, {"v": -0.04}, {"v": -0.03}],
                },
                {
                    "date": "2026-08-04T00:00:00",
                    "start": "00:15:00",
                    "values": [{"v": 0.01}, {"v": 0}, {"v": -0.05}, {"v": -0.04}],
                },
                {
                    "date": "2026-08-04T00:00:00",
                    "start": "00:45:00",
                    "values": [{"v": 0.02}, {"v": 0.01}, {"v": -0.01}, {"v": 0}],
                },
                {
                    "date": "2026-08-04T00:00:00",
                    "start": "01:00:00",
                    "values": [{"v": 0.02}, {"v": 0}, {"v": -0.04}, {"v": -0.02}],
                },
            ],
        }

        rows = calculation.parse_daily_profile(response)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].producer_overflow, Decimal("0.06"))
        self.assertEqual(rows[0].unused_overflow, Decimal("0.01"))
        self.assertEqual(rows[0].consumption, Decimal("0.14"))
        self.assertEqual(rows[0].grid_purchase, Decimal("0.09"))
        self.assertEqual(rows[0].shared, Decimal("0.05"))
        self.assertEqual(
            rows[0].coverage, Decimal("0.05") / Decimal("0.14") * Decimal("100")
        )
        self.assertEqual(rows[0].consistency_difference, Decimal("0.00"))

        hours = calculation.parse_hourly_profile(response)

        self.assertEqual(len(hours), 2)
        self.assertEqual(hours[0].start.isoformat(), "2026-08-04T00:00:00")
        self.assertEqual(hours[0].shared, Decimal("0.03"))
        self.assertEqual(hours[0].consumption, Decimal("0.10"))
        self.assertEqual(hours[0].grid_purchase, Decimal("0.07"))
        self.assertEqual(hours[1].start.isoformat(), "2026-08-04T01:00:00")
        self.assertEqual(hours[1].shared, Decimal("0.02"))
        self.assertEqual(hours[1].consumption, Decimal("0.04"))
        self.assertEqual(hours[1].grid_purchase, Decimal("0.02"))

    def test_latest_available_day_is_used_when_today_is_delayed(self) -> None:
        response = {
            "valueColumns": [
                {"ean": "111", "type": "D", "dir": "IN"},
                {"ean": "111", "type": "D", "dir": "OUT"},
                {"ean": "222", "type": "O", "dir": "IN"},
                {"ean": "222", "type": "O", "dir": "OUT"},
            ],
            "content": [
                {"date": "2026-09-01", "values": [{"v": 10}, {"v": 4}, {"v": -8}, {"v": -2}]},
            ],
        }

        result = calculation.calculate_profile(response, Decimal("2"), date(2026, 9, 2))

        self.assertEqual(result.today.shared, Decimal("0"))
        self.assertEqual(result.latest.shared, Decimal("6"))
        self.assertEqual(result.latest_day, date(2026, 9, 1))


if __name__ == "__main__":
    unittest.main()
