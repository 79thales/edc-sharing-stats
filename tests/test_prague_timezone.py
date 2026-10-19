"""Regrese HACS #10586: jediná inicializace tzdata mimo výpočty.

Syntetické profily mají známé kWh a skutečné UTC sloty podle tzdata.
Referenční otisky všech veřejných výsledků vznikly před úpravou na commitu
uvedeném ve fixture; nezachycují osobní historii ani živá data EDC.
"""

import asyncio
import dataclasses
import hashlib
import importlib.util
import json
import sys
import unittest
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tests.test_calculation import MODULE_PATH, calculation
from tests.test_profile_times import full_day, minute_profile


class PragueTimezoneTests(unittest.TestCase):
    """Ověřit import, sdílení zóny, bezpečný fallback a číselnou kompatibilitu."""

    def load_module(self, factory):
        """Izolovaný import s řízeným konstruktorem; nepozměnit ostatní testy."""
        spec = importlib.util.spec_from_file_location(
            "_edc_timezone_regression", MODULE_PATH
        )
        module = importlib.util.module_from_spec(spec)
        with (
            patch.dict(sys.modules, {spec.name: module}),
            patch("zoneinfo.ZoneInfo", factory),
        ):
            spec.loader.exec_module(module)
        return module

    def test_timezone_is_initialized_once_at_import_outside_running_loop(self):
        zone = ZoneInfo("Europe/Prague")
        calls = []

        def initialize(key):
            # Import je synchronní; konstruktor nesmí přejít do běžících výpočtů.
            with self.assertRaises(RuntimeError):
                asyncio.get_running_loop()
            calls.append(key)
            return zone

        module = self.load_module(initialize)
        self.assertIs(module.PRAGUE_TZ, zone)
        self.assertEqual(calls, ["Europe/Prague"])

        async def calculate():
            # Celý profil provede všechny tři dotčené funkce včetně DST větve.
            with patch.object(
                module, "ZoneInfo", side_effect=AssertionError("runtime tzdata I/O")
            ):
                for day in (date(2026, 3, 29), date(2026, 10, 25)):
                    profile, count = full_day(day, "")
                    for _ in range(2):
                        self.assertEqual(
                            module.profile_resolution(profile), "quarter_hour"
                        )
                        hours = module._profile_complete_hours(profile)
                        self.assertEqual(len(hours), count)
                        self.assertTrue(module._day_completeness(profile, day, hours))

        asyncio.run(calculate())
        self.assertEqual(calls, ["Europe/Prague"])

    def test_all_three_helpers_use_shared_timezone(self):
        # Jiná sdílená instance se stejnými pravidly dokládá předání konstanty.
        zone = ZoneInfo.no_cache("Europe/Prague")
        profile, _ = full_day(date(2026, 10, 25), "")
        with patch.object(calculation, "PRAGUE_TZ", zone):
            with patch.object(
                calculation,
                "parse_hourly_profile",
                wraps=calculation.parse_hourly_profile,
            ) as parser:
                hours = calculation._profile_complete_hours(profile)
                self.assertIs(parser.call_args.kwargs["local_tz"], zone)
            self.assertTrue(
                calculation._day_completeness(profile, date(2026, 10, 25), hours)
            )
            self.assertEqual(calculation.profile_resolution(profile), "quarter_hour")
        # UTC by tentýž podzimní přechod nerozpoznalo a den má jen 24 hodin.
        with patch.object(calculation, "PRAGUE_TZ", UTC):
            self.assertEqual(calculation.profile_resolution(profile), "unknown")
            ordinary, _ = full_day(date(2026, 1, 15), "")
            hours = calculation.parse_hourly_profile(ordinary, local_tz=zone)
            self.assertFalse(
                calculation._day_completeness(ordinary, date(2026, 1, 15), hours)
            )

    def test_missing_tzdata_preserves_existing_fallbacks(self):
        def unavailable(key):
            raise ZoneInfoNotFoundError(key)

        module = self.load_module(unavailable)
        self.assertIsNone(module.PRAGUE_TZ)
        with patch.object(
            module, "ZoneInfo", side_effect=AssertionError("unexpected retry")
        ):
            for day in (date(2026, 3, 29), date(2026, 10, 25)):
                profile, _ = full_day(day, "")
                self.assertEqual(module.profile_resolution(profile), "unknown")
                self.assertEqual(module._profile_complete_hours(profile), ())
                self.assertFalse(module._day_completeness(profile, day))
            ordinary, _ = full_day(date(2026, 1, 15), "")
            self.assertEqual(module.profile_resolution(ordinary), "quarter_hour")
            self.assertEqual(module._profile_complete_hours(ordinary), ())
            self.assertFalse(module.parse_daily_profile(ordinary)[0].complete)
            daily = minute_profile()
            daily["content"] = [daily["content"][0]]
            daily["content"][0].pop("start")
            daily["content"][0].pop("end")
            self.assertEqual(module.profile_resolution(daily), "daily")
            self.assertTrue(module.parse_daily_profile(daily)[0].complete)
            self.assertEqual(module.profile_resolution({"content": []}), "empty")

    def test_utc_conversion_at_both_dst_transitions(self):
        zone = calculation.PRAGUE_TZ
        self.assertIsNotNone(zone)
        for stamp, local, name, fold in (
            ("2026-03-29T00:45:00+00:00", "2026-03-29T01:45:00+01:00", "CET", 0),
            ("2026-03-29T01:00:00+00:00", "2026-03-29T03:00:00+02:00", "CEST", 0),
            ("2026-10-25T00:45:00+00:00", "2026-10-25T02:45:00+02:00", "CEST", 0),
            ("2026-10-25T01:00:00+00:00", "2026-10-25T02:00:00+01:00", "CET", 1),
        ):
            with self.subTest(stamp=stamp):
                utc = datetime.fromisoformat(stamp)
                actual = utc.astimezone(zone)
                self.assertEqual(
                    (actual.isoformat(), actual.tzname(), actual.fold),
                    (local, name, fold),
                )
                self.assertEqual(actual.astimezone(UTC), utc)

    def test_full_quarter_hour_days_and_missing_slots(self):
        for day, count in (
            (date(2026, 1, 15), 24),
            (date(2026, 3, 29), 23),
            (date(2026, 10, 25), 25),
        ):
            with self.subTest(day=day):
                profile, _ = full_day(day, "")
                self.assertEqual(len(profile["content"]), count * 4)
                hours = calculation._profile_complete_hours(profile)
                self.assertEqual(len(hours), count)
                self.assertEqual(len({row.start for row in hours}), count)
                self.assertTrue(all(row.complete for row in hours))
                self.assertTrue(
                    all(
                        right.start - left.start == timedelta(hours=1)
                        for left, right in pairwise(hours)
                    )
                )
                (daily,) = calculation.parse_daily_profile(profile)
                self.assertEqual(daily.shared, count * 4)
                self.assertTrue(daily.complete)
                # Slot v 02:xx zahrnuje podzimní fold; mezera nesmí být nula.
                profile["content"].pop(8)
                (daily,) = calculation.parse_daily_profile(profile)
                self.assertEqual(daily.shared, count * 4 - 1)
                self.assertFalse(daily.complete)

    def test_public_results_match_pre_fix_baseline(self):
        fixture = json.loads(
            (
                Path(__file__).parent / "fixtures/prague-timezone-baseline.json"
            ).read_text(encoding="utf-8")
        )
        for key, expected in fixture["sha256"].items():
            with self.subTest(profile=key):
                stamp, case = key.split("/")
                day = date.fromisoformat(stamp)
                profile, _ = full_day(day, "")
                if case == "missing":
                    profile["content"].pop(8)
                elif case == "null":
                    profile["content"][8]["values"][0]["v"] = None
                daily = calculation.parse_daily_profile(profile)
                target = calculation.parse_daily_target_profiles(profile)
                results = {
                    "daily": daily,
                    "target_daily": target,
                    "hourly": calculation.parse_hourly_profile(
                        profile, local_tz=calculation.PRAGUE_TZ
                    ),
                    "target_hourly": calculation.parse_hourly_target_profiles(
                        profile, local_tz=calculation.PRAGUE_TZ
                    ),
                    "statistics": calculation.calculate_statistics(
                        daily, Decimal("2.5"), day, target_days={"consumer": target}
                    ),
                    "profile": calculation.calculate_profile(
                        profile, Decimal("2.5"), day
                    ),
                    "summary": calculation.calculate_period_summary(
                        daily, Decimal("2.5")
                    ),
                }
                # Zahrnout všechny atributy, nikoli jen vybrané kWh/počty hodin.
                encoded = json.dumps(
                    {
                        name: [dataclasses.asdict(row) for row in value]
                        if isinstance(value, tuple)
                        else dataclasses.asdict(value)
                        for name, value in results.items()
                    },
                    default=str,
                    sort_keys=True,
                ).encode()
                self.assertEqual(hashlib.sha256(encoded).hexdigest(), expected)
