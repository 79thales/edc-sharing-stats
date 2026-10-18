"""Regrese #10: čas výběru revize a kvalita nejsou časové rozlišení ani finalita."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import unittest
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).parents[1] / "custom_components/edc_sharing"
package = ModuleType("_edc_selection_test")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
import importlib

selection = importlib.import_module(package.__name__ + ".profile_selection")
api = importlib.import_module(package.__name__ + ".api")
contract = importlib.import_module(package.__name__ + ".portal_contract")


class SelectionTests(unittest.IsolatedAsyncioTestCase):
    def test_current_payload_matches_public_portal_to_iso_string(self):
        # Čas se převádí do UTC, ale zářijové kalendářní meze se neposunují.
        instant = datetime(2026, 10, 18, 9, 30, 0, 123456,
                           tzinfo=timezone(timedelta(hours=2)))
        payload = api.build_profile_request(1, date(2026, 9, 1), date(2026, 10, 1), as_of=instant)
        self.assertNotIn("calculationType", payload)
        self.assertEqual("2026-10-18T07:30:00.123Z", payload["currentEnteredDateTime"])
        self.assertEqual(("2026-09-01", "2026-09-30"), (payload["dateFrom"], payload["dateTo"]))
        with self.assertRaises(ValueError):
            api.build_profile_request(1, date(2026, 9, 1), date(2026, 10, 1), as_of=instant.replace(tzinfo=None))

    async def test_nested_snapshots_share_time_but_background_tasks_do_not(self):
        initial = datetime(2026, 10, 18, 7, tzinfo=UTC)
        later = initial + timedelta(hours=1)

        @selection.profile_read_snapshot
        async def child():
            return selection.profile_as_of()

        @selection.profile_read_snapshot
        async def parent():
            with patch.object(selection, "datetime") as clock:
                clock.now.return_value = later
                self.assertEqual(initial, await child())
                self.assertEqual(later, await asyncio.create_task(child()))
                self.assertEqual(initial, selection.profile_as_of())
            raise RuntimeError("synthetic")

        with patch.object(selection, "datetime") as clock:
            clock.now.return_value = initial
            with self.assertRaises(RuntimeError):
                await parent()
        self.assertIsNone(selection._PROFILE_AS_OF.get())

    def test_quality_uses_cells_and_does_not_claim_monthly_finality(self):
        raw = {"content": [{"values": [{"v": 1, "q": "Z46"}, {"v": 0, "q": "Z66"},
                                       {"v": None, "q": "Z99"}, 0, {"q": "private"}]}]}
        summary = selection.profile_quality(raw)
        self.assertEqual({"Z46": 1, "Z66": 1, "Z99": 1, "unknown": 2}, summary["quality_counts"])
        self.assertEqual(40, summary["provisional_quality_percent"])
        self.assertEqual("unknown", summary["actual_calculation_type"])
        self.assertNotIn("private", str(summary))
        self.assertIsNone(selection.profile_quality({"content": []})["provisional_quality_percent"])

    def test_contract_recognizes_current_without_recording_timestamp(self):
        payload = api.build_profile_request(1, date(2026, 9, 1), date(2026, 10, 1))
        result = contract.profile_contract(payload, {"content": [], "valueColumns": []})
        self.assertEqual("CURRENT", result["request"]["calculation"])
        self.assertEqual(0, result["request"]["unrecognized_fields"])
        self.assertNotIn(payload["currentEnteredDateTime"], str(result))
