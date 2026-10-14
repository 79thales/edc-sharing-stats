"""P2: monitor je advisory, deduplikuje stav a nezveřejní cizí baseline pole."""

import importlib.util
import json
import unittest
from pathlib import Path
from urllib.error import HTTPError

SPEC = importlib.util.spec_from_file_location(
    "edc_public_monitor_test", Path(__file__).parents[1] / "scripts/check_edc_portal.py"
)
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


class PublicMonitorTests(unittest.TestCase):
    def test_304_returns_only_allowlisted_public_baseline(self):
        class NotModified:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                raise HTTPError(monitor.PORTAL, 304, "Not Modified", {}, None)

        opener = NotModified()
        result = monitor.check(
            {
                "build_hash": "a" * 64,
                "asset_count": 1,
                "calendar_link_count": 0,
                "secret": "private-secret",
            },
            opener=opener,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["scope"], "public_build_only")
        self.assertNotIn("private-secret", json.dumps(result))
        self.assertEqual(opener.timeout, 20)

    def test_event_deduplication_change_and_recovery(self):
        result = {
            "status": "ok",
            "snapshot": {"build_hash": "a" * 64},
            "calendar": {"status": "ok", "events": []},
        }
        state, event = monitor.observation_event([], result)
        self.assertEqual(event, "observation_changed")
        self.assertIsNone(monitor.observation_event(state, result)[1])
        result["calendar"]["events"] = [{"system": "edc_saku", "active": True}]
        self.assertEqual(
            monitor.observation_event(state, result)[1], "observation_changed"
        )
        state["status"] = "unavailable"
        self.assertEqual(monitor.observation_event(state, result)[1], "recovered")
