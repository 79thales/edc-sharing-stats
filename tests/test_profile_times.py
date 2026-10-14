"""Regrese minutových hranic podle funkční tabulky WebDownloaderu.

Fixture je syntetický kontrakt se zápisem HH:mm převzatým z tabulky,
nikoli zachycená živá JSON odpověď. EANy a kWh jsou smyšlené. Jedna
hodina obsahuje spotřebu 10 kWh, síť 6 kWh a sdílení 4 kWh; chybějící
slot proto musí snížit součet a zrušit úplnost, nikdy doplnit nulu.
"""

import copy
import json
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from tests.test_api import _Session, api
from tests.test_calculation import calculation


def minute_profile():
    """Načíst anonymní referenci; každý test dostává samostatný profil."""
    return json.loads((Path(__file__).parent / "fixtures/profile-clock-minutes.json").read_text())


def full_day(day, suffix):
    """Vygenerovat všechny skutečné UTC sloty dne v Europe/Prague.

    UTC půlnoci určují 23/24/25 hodin nezávisle na testovaném parseru.
    Konec dalšího dne je v kontraktu 24:00; změna DST používá místní
    hranice před a po přechodu. suffix určuje pouze textový zápis času.
    """
    profile = minute_profile()
    seed = profile["content"][0]
    zone = ZoneInfo("Europe/Prague")
    begin = datetime.combine(day, datetime.min.time(), tzinfo=zone).astimezone(UTC)
    stop = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=zone).astimezone(UTC)
    profile["content"] = []
    cursor = begin
    while cursor < stop:
        left, right = cursor.astimezone(zone), (cursor + timedelta(minutes=15)).astimezone(zone)
        row = copy.deepcopy(seed)
        row.update(date=day.isoformat(), start=left.strftime("%H:%M") + suffix,
                   end=("24:00" if right.date() > day else right.strftime("%H:%M")) + suffix)
        profile["content"].append(row)
        cursor += timedelta(minutes=15)
    return profile, int((stop - begin).total_seconds() / 3600)


class ProfileTimeTests(unittest.TestCase):
    def test_minute_clock_keeps_group_and_target_energy(self):
        profile = minute_profile()
        self.assertEqual(calculation.profile_resolution(profile), "quarter_hour")
        for parser in (calculation.parse_hourly_profile, calculation.parse_hourly_target_profiles):
            hour, = parser(profile)
            self.assertTrue(hour.complete)
            self.assertEqual((hour.consumption, hour.grid_purchase, hour.shared, hour.coverage), (10, 6, 4, 40))
        for parser in (calculation.parse_daily_profile, calculation.parse_daily_target_profiles):
            day, = parser(profile)
            self.assertEqual(day.shared, 4)
            self.assertFalse(day.complete)

    def test_full_days_and_dst_have_identical_results_for_all_clock_formats(self):
        for day in (date(2026, 10, 13), date(2026, 3, 29), date(2026, 10, 25)):
            for suffix in ("", ":00", ":00.0000000"):
                with self.subTest(day=day, suffix=suffix):
                    profile, count = full_day(day, suffix)
                    for parser in (calculation.parse_hourly_profile, calculation.parse_hourly_target_profiles):
                        hours = parser(profile, local_tz=ZoneInfo("Europe/Prague"))
                        self.assertEqual(len(hours), count)
                        self.assertEqual(len({hour.start for hour in hours}), count)
                        self.assertTrue(all(hour.complete for hour in hours))
                        self.assertEqual(sum(hour.shared for hour in hours), count * 4)
                    for parser in (calculation.parse_daily_profile, calculation.parse_daily_target_profiles):
                        result, = parser(profile)
                        self.assertTrue(result.complete)
                        self.assertEqual(result.shared, count * 4)

    def test_null_and_missing_slot_do_not_become_complete(self):
        for remove in (False, True):
            profile = minute_profile()
            if remove:
                profile["content"].pop(1)
            else:
                profile["content"][1]["values"][0]["v"] = None
            for parser in (calculation.parse_hourly_profile, calculation.parse_hourly_target_profiles):
                hour, = parser(profile)
                self.assertFalse(hour.complete)
                self.assertEqual(hour.shared, 3)
            self.assertFalse(calculation.parse_daily_profile(profile)[0].complete)

    def test_invalid_clocks_and_durations_remain_unknown(self):
        for field, value in (
            ("start", "24:00"), ("start", "12:60"), ("start", "12:00:01"),
            ("start", "12:00:00.001"), ("start", "12:00Z"), ("start", 1200),
            ("end", "24:15"), ("end", "12:15:59"), ("end", "12:20"),
        ):
            with self.subTest(field=field, value=value):
                profile = minute_profile()
                profile["content"][0][field] = value
                self.assertEqual(calculation.profile_resolution(profile), "unknown")
                self.assertEqual(calculation.parse_hourly_profile(profile), ())

    def test_hourly_minute_boundaries_preserve_full_days_including_dst(self):
        for day in (date(2026, 10, 13), date(2026, 3, 29), date(2026, 10, 25)):
            profile, count = full_day(day, "")
            quarters = profile["content"]
            profile["content"] = []
            for index in range(0, len(quarters), 4):
                row = copy.deepcopy(quarters[index])
                row["end"] = quarters[index + 3]["end"]
                row["values"] = [{"v": 4}, {"v": 0}, {"v": -10}, {"v": -6}]
                profile["content"].append(row)
            self.assertEqual(calculation.profile_resolution(profile), "hour")
            for parser in (calculation.parse_hourly_profile, calculation.parse_hourly_target_profiles):
                hours = parser(profile, local_tz=ZoneInfo("Europe/Prague"))
                self.assertEqual(len(hours), count)
                self.assertTrue(all(hour.complete and hour.shared == 4 for hour in hours))
            self.assertTrue(calculation.parse_daily_profile(profile)[0].complete)

    def test_daily_midnight_total_never_becomes_hourly(self):
        for suffix in ("", ":00", ":00.000"):
            profile = minute_profile()
            profile["content"] = [profile["content"][0]]
            profile["content"][0].update(start="00:00" + suffix, end="24:00" + suffix)
            self.assertEqual(calculation.profile_resolution(profile), "daily")
            self.assertEqual(calculation.parse_hourly_profile(profile), ())
            self.assertTrue(calculation.parse_daily_profile(profile)[0].complete)

    def test_legacy_missing_end_keeps_ambiguity_guard(self):
        profile = minute_profile()
        for row in profile["content"]:
            row.pop("end")
        self.assertEqual(calculation.profile_resolution(profile), "quarter_hour")
        self.assertTrue(calculation.parse_hourly_profile(profile)[0].complete)
        profile["content"] = [profile["content"][0]]
        self.assertEqual(calculation.profile_resolution(profile), "unknown")

    def test_equivalent_clock_text_cannot_bypass_duplicate_detection(self):
        profile = minute_profile()
        duplicate = copy.deepcopy(profile["content"][0])
        duplicate.update(start="12:00:00.000", end="12:15:00")
        profile["content"].append(duplicate)
        for parser in (calculation.parse_hourly_profile, calculation.parse_hourly_target_profiles):
            with self.assertRaises(ValueError):
                parser(profile, local_tz=ZoneInfo("Europe/Prague"))

    def test_mixed_clock_text_keeps_two_separate_dst_folds(self):
        profile, count = full_day(date(2026, 10, 25), "")
        for index, row in enumerate(profile["content"]):
            if index % 2:
                row["start"] += ":00"
                row["end"] += ":00.000"
        for parser in (calculation.parse_hourly_profile, calculation.parse_hourly_target_profiles):
            hours = parser(profile, local_tz=ZoneInfo("Europe/Prague"))
            self.assertEqual(len({hour.start for hour in hours}), count)
            self.assertTrue(all(hour.complete for hour in hours))


class ProfileTimeApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_minute_profile_passes_api_guard_without_mutating_response(self):
        profile = minute_profile()
        original = copy.deepcopy(profile)
        client = api.EdcApiClient(_Session([], [], []), "synthetic-user", "synthetic-password")
        client.last_status = 200
        client._request = AsyncMock(return_value=profile)
        result = await client.async_get_daily_profile(1, date(2026, 10, 13), date(2026, 10, 14))
        self.assertIs(result, profile)
        self.assertEqual(result, original)
        client._request.assert_awaited_once()
        self.assertIsNone(client.account_state.last_failure)

    async def test_invalid_clock_is_still_contract_error_without_retry(self):
        profile = minute_profile()
        profile["content"][0]["start"] = "12:00:01"
        client = api.EdcApiClient(_Session([], [], []), "synthetic-user", "synthetic-password")
        client.last_status = 200
        client._request = AsyncMock(return_value=profile)
        with self.assertRaises(api.EdcApiError) as raised:
            await client.async_get_daily_profile(1, date(2026, 10, 13), date(2026, 10, 14))
        self.assertEqual(raised.exception.category, "contract")
        self.assertEqual(raised.exception.phase, "profile_validation")
        client._request.assert_awaited_once()
