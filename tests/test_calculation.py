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


if __name__ == "__main__":
    unittest.main()
