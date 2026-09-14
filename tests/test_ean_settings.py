"""Test EAN metadata normalization without a Home Assistant runtime."""

from __future__ import annotations

import importlib
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


class EanSettingsTests(unittest.TestCase):
    """Keep optional local metadata safe for manually edited older options."""

    def setUp(self) -> None:
        package = ModuleType("_edc_ean_settings_test")
        package.__path__ = [
            str(Path(__file__).parents[1] / "custom_components" / "edc_sharing")
        ]
        self.modules_patch = patch.dict(sys.modules, {package.__name__: package})
        self.modules_patch.start()
        self.addCleanup(self.modules_patch.stop)
        self.settings = importlib.import_module(package.__name__ + ".ean_settings")

    def test_name_location_and_target_price_are_normalized(self) -> None:
        options = {
            "ean_settings": {
                "target-example": {
                    "name": "  Flat 2  ",
                    "location": "  Prague  ",
                    "price": "3.50",
                }
            }
        }
        self.assertEqual(self.settings.ean_name("target-example", options), "Flat 2")
        self.assertEqual(
            self.settings.ean_location("target-example", options), "Prague"
        )
        self.assertEqual(
            self.settings.target_sale_price(
                "target-example", options, Decimal("2")
            ),
            Decimal("3.50"),
        )

    def test_invalid_metadata_never_replaces_group_price(self) -> None:
        options = {
            "ean_settings": {
                "target-example": {
                    "name": 42,
                    "location": ["not text"],
                    "price": "NaN",
                }
            }
        }
        self.assertEqual(self.settings.configured_ean_settings(options), {})
        self.assertEqual(
            self.settings.target_sale_price(
                "target-example", options, Decimal("2.25")
            ),
            Decimal("2.25"),
        )


if __name__ == "__main__":
    unittest.main()
