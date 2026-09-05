"""Calendar and backward compatibility tests without Home Assistant runtime."""

import importlib.util
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location(
    "edc_report_profiles",
    Path(__file__).parents[1] / "custom_components/edc_sharing/report_profiles.py",
)
profiles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profiles)


class ProfileCalendarTests(unittest.TestCase):
    def test_legacy_schedules_keep_their_cadence_and_language(self):
        options = {
            "report_targets": ["notify.owner"],
            "report_language": "cs",
            "report_time": "08:22:00",
            "report_day": 5,
        }
        options.update(
            {f"{period}_report": True for period in (*profiles.PERIODS, "summary")}
        )
        actual = profiles.configured_profiles(options)
        self.assertEqual(len(actual), 5)
        self.assertEqual(
            [p["frequency"] for p in actual],
            ["daily", "weekly", "monthly", "monthly", "daily"],
        )
        self.assertTrue(
            all(p["language"] == "cs" and p["time"] == "08:22:00" for p in actual)
        )
        self.assertEqual(actual[-1]["periods"], list(profiles.PERIODS))
        self.assertNotIn("report_profiles", options)

    def test_empty_explicit_profiles_do_not_restart_legacy_sending(self):
        self.assertEqual(
            profiles.configured_profiles({"daily_report": True, "report_profiles": []}),
            [],
        )

    def test_periods_independent_of_schedule_and_year_boundary(self):
        today = date(2027, 1, 5)
        self.assertEqual(
            profiles.period_range("yearly", "previous", today),
            (date(2026, 1, 1), date(2027, 1, 1)),
        )
        self.assertEqual(
            profiles.period_range("monthly", "previous", today),
            (date(2026, 12, 1), date(2027, 1, 1)),
        )
        self.assertEqual(
            profiles.period_range("weekly", "current", today),
            (date(2027, 1, 4), date(2027, 1, 6)),
        )
        self.assertEqual(
            profiles.period_range("yearly", "legacy", today),
            (date(2027, 1, 1), date(2027, 1, 6)),
        )

    def test_annual_schedule_and_paused_profile(self):
        profile = profiles.default_profile() | {
            "enabled": True,
            "targets": ["notify.owner"],
            "frequency": "yearly",
            "month": 1,
            "day": 5,
        }
        self.assertFalse(profiles.due_on(profile, date(2026, 9, 5)))
        self.assertTrue(profiles.due_on(profile, date(2027, 1, 5)))
        now = datetime(2026, 9, 5, tzinfo=UTC)
        self.assertEqual(
            profiles.next_run(profile, now), datetime(2027, 1, 5, 8, tzinfo=UTC)
        )
        self.assertIsNone(profiles.next_run(profile | {"enabled": False}, now))

    def test_next_run_skips_nonexistent_dst_hour(self):
        tz = ZoneInfo("Europe/Prague")
        profile = profiles.default_profile() | {
            "enabled": True,
            "targets": ["notify.owner"],
            "time": "02:30:00",
        }
        self.assertEqual(
            profiles.next_run(profile, datetime(2026, 3, 28, 23, tzinfo=tz)),
            datetime(2026, 3, 30, 2, 30, tzinfo=tz),
        )
        self.assertEqual(
            profiles.next_run(profile, datetime(2026, 10, 25, 2, 45, tzinfo=tz)),
            datetime(2026, 10, 26, 2, 30, tzinfo=tz),
        )

    def test_invalid_profiles_and_deduplicated_targets(self):
        profile = profiles.default_profile("test") | {
            "name": "Owner",
            "targets": ["notify.owner", "notify.owner"],
        }
        self.assertEqual(
            profiles.validate_profile(profile)["targets"], ["notify.owner"]
        )
        for values in (
            {"targets": []},
            {"periods": []},
            {"energy": False, "finance": False},
            {"frequency": "weekly", "weekdays": []},
            {"day": 31},
            {"month": 13},
            {"name": "Bad\nSubject"},
            {"time": "08:00:00+02:00"},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                profiles.validate_profile(profile | values)
