"""The dashboard factory never guesses entity IDs or changes source data."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "edc_dashboard",
    Path(__file__).parents[1] / "custom_components/edc_sharing/dashboard.py",
)
dashboard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = dashboard
SPEC.loader.exec_module(dashboard)


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entities = {key: f"sensor.renamed_{key}" for key in dashboard.GROUP_KEYS}
        self.statistics = {
            f"{metric}_{period}": f"edc_sharing:example_{metric}_{period}"
            for metric in (
                "shared",
                "consumption",
                "grid",
                "unused",
                "coverage",
                "revenue",
            )
            for period in ("daily", "hourly")
        }

    def build(self, **kwargs):
        return dashboard.build_dashboard(
            title="Test EDC",
            url_path="test-edc",
            entities=self.entities,
            statistics=self.statistics,
            **kwargs,
        )

    def test_sections_style_and_details_navigation(self) -> None:
        config = self.build()
        overview, details = config["views"]
        self.assertEqual(overview["type"], "sections")
        self.assertEqual(overview["max_columns"], 4)
        self.assertTrue(details["subview"])
        heading = overview["sections"][0]["cards"][0]
        self.assertEqual(
            heading["badges"][0]["tap_action"]["navigation_path"], "/test-edc/details"
        )
        self.assertNotIn("custom:", json.dumps(config))

    def test_registered_renamed_entities_and_real_edc_statistic_dates(self) -> None:
        text = json.dumps(self.build())
        self.assertIn("sensor.renamed_shared_today", text)
        self.assertIn("edc_sharing:example_shared_daily", text)
        self.assertNotIn('"stat_types": ["state"]', text)
        self.assertNotIn("dvorak", text.lower())
        self.assertNotIn("password", text)

    def test_missing_disabled_and_first_start_entities_are_not_invented(self) -> None:
        config = dashboard.build_dashboard(
            title="Empty", url_path="edc-empty", entities={}, statistics={}
        )
        text = json.dumps(config)
        self.assertNotIn('"entity":', text)
        self.assertNotIn("None", text)
        self.assertIn("Empty", text)

    def test_each_target_keeps_its_own_values_and_price(self) -> None:
        targets = [
            dashboard.DashboardTarget(
                name="Supply point A",
                entities={
                    "shared_this_month": "sensor.point_a_shared",
                    "sale_price": "sensor.point_a_price",
                },
            ),
            dashboard.DashboardTarget(
                name="Supply point B",
                entities={
                    "shared_this_month": "sensor.point_b_shared",
                    "sale_price": "sensor.point_b_price",
                },
            ),
        ]
        text = json.dumps(self.build(targets=targets))
        for name in (
            "sensor.point_a_shared",
            "sensor.point_b_shared",
            "sensor.point_a_price",
            "sensor.point_b_price",
        ):
            self.assertIn(name, text)
        self.assertEqual(len(targets), 2)

    def test_energy_is_opt_in_and_does_not_modify_energy_configuration(self) -> None:
        self.assertNotIn("energy-sources-table", json.dumps(self.build()))
        text = json.dumps(self.build(include_energy=True))
        self.assertIn("energy-sources-table", text)
        self.assertIn("energy_edc_test_edc", text)
        self.assertNotIn("energy/save", text)

    def test_generation_is_deterministic_and_does_not_mutate_inputs(self) -> None:
        original = dict(self.entities)
        first = self.build()
        self.assertEqual(first, self.build())
        self.assertEqual(self.entities, original)
        first["views"][0]["title"] = "Changed"
        self.assertEqual(self.build()["views"][0]["title"], "Test EDC")

    def test_english_and_optional_details(self) -> None:
        config = self.build(language="en", include_details=False)
        self.assertEqual(len(config["views"]), 1)
        self.assertIn("Latest available day", json.dumps(config))
        self.assertNotIn('"badges": [{"type": "button"', json.dumps(config))

    def test_title_and_path_validation(self) -> None:
        for path in (
            "lovelace",
            "../edc",
            "/edc-test",
            "edc sharing",
            "EDC-test",
            "edc-sharing-dashboard",
            "a" * 100,
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                dashboard.build_dashboard(
                    title="Test", url_path=path, entities={}, statistics={}
                )
        for title in ("", " ", "a" * 121):
            with self.subTest(title=title), self.assertRaises(ValueError):
                dashboard.build_dashboard(
                    title=title, url_path="edc-test", entities={}, statistics={}
                )
