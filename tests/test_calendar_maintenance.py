"""Ověřený ICS formát EDC, časový kontext a bezpečný export bez volných textů."""

import importlib.util
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "edc_calendar_test",
    Path(__file__).parents[1] / "custom_components/edc_sharing/calendar_maintenance.py",
)
calendar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(calendar)


class CalendarTests(unittest.TestCase):
    def test_utc_source_and_system_are_not_conflated(self):
        text = "\r\n".join(  # noqa: FLY002 -- záměrné rozdělení na ICS řádky včetně folded summary
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "BEGIN:VEVENT",
                "UID:private-secret",
                "DTSTART:20261013T140000Z",
                "DTEND:20261013T150000Z",
                "SUMMARY:Plánovaná odstávka IS EDC-",
                " SAKU",
                "DESCRIPTION:private-secret",
                "END:VEVENT",
                "BEGIN:VEVENT",
                "DTSTART:20261013T140000Z",
                "DTEND:20261013T160000Z",
                "SUMMARY:Release SEBI",
                "END:VEVENT",
                "END:VCALENDAR",
            ]
        )
        result = calendar.parse_calendar_feed(
            text, datetime(2026, 10, 13, 14, 30, tzinfo=UTC)
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(
            {event["system"] for event in result["events"]}, {"edc_saku", "sebi"}
        )
        self.assertTrue(all(event["active"] for event in result["events"]))
        self.assertNotIn("private-secret", json.dumps(result))
        later = calendar.parse_calendar_feed(text, datetime(2026, 10, 14, tzinfo=UTC))
        self.assertFalse(any(event["active"] for event in later["events"]))

    def test_unknown_format_is_inconclusive(self):
        self.assertEqual(
            calendar.parse_calendar_feed("<html>unknown</html>", datetime.now(UTC))[
                "status"
            ],
            "inconclusive",
        )
