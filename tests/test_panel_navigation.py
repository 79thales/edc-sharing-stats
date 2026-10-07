"""Auxiliary panels must not replace the native EDC options-flow route."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


class PanelNavigationTests(unittest.TestCase):
    def test_helper_panels_do_not_claim_the_main_config_panel(self) -> None:
        root = Path(__file__).parents[1] / "custom_components/edc_sharing"
        for filename in ("dashboard_api.py", "billing_api.py"):
            with self.subTest(panel=filename):
                tree = ast.parse((root / filename).read_text(encoding="utf-8"))
                calls = [
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "async_register_panel"
                ]
                self.assertEqual(len(calls), 1)
                self.assertNotIn(
                    "config_panel_domain",
                    {keyword.arg for keyword in calls[0].keywords},
                    "A helper panel would hijack the integration's Configure button",
                )


if __name__ == "__main__":
    unittest.main()
