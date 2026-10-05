"""Delayed Energy income, selection, corrections and DST regression tests."""

import importlib
import sys
import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from test_calculation import PRAGUE_2026


class EnergyTests(unittest.TestCase):
    def setUp(self):
        package = ModuleType("_edc_energy_test")
        package.__path__ = [
            str(Path(__file__).parents[1] / "custom_components/edc_sharing")
        ]
        self.modules_patch = patch.dict(sys.modules, {package.__name__: package})
        self.modules_patch.start()
        self.addCleanup(self.modules_patch.stop)
        self.energy = importlib.import_module(package.__name__ + ".energy")
        self.calculation = importlib.import_module(package.__name__ + ".calculation")

    def row(self, ean, day, shared):
        value = Decimal(shared)
        return self.calculation.TargetDailySharing(
            ean, day, value, Decimal(0), value, Decimal(100)
        )

    def test_export_queues_energy_compatible_metadata_and_dated_sums(self):
        modules = {
            name: ModuleType(name)
            for name in (
                "homeassistant",
                "homeassistant.components",
                "homeassistant.components.recorder",
                "homeassistant.components.recorder.models",
                "homeassistant.components.recorder.statistics",
                "homeassistant.const",
                "homeassistant.core",
                "homeassistant.util",
                "homeassistant.util.unit_conversion",
            )
        }
        models = modules["homeassistant.components.recorder.models"]
        models.StatisticData = dict
        models.StatisticMetaData = dict
        models.StatisticMeanType = SimpleNamespace(NONE=0, ARITHMETIC=1)
        recorder = modules["homeassistant.components.recorder.statistics"]
        recorder.async_add_external_statistics = Mock()
        modules["homeassistant.const"].PERCENTAGE = "%"
        modules["homeassistant.const"].UnitOfEnergy = SimpleNamespace(
            KILO_WATT_HOUR="kWh"
        )
        modules["homeassistant.core"].HomeAssistant = object
        modules["homeassistant.core"].callback = lambda fn: fn
        converters = modules["homeassistant.util.unit_conversion"]
        converters.EnergyConverter = SimpleNamespace(UNIT_CLASS="energy")
        converters.UnitlessRatioConverter = SimpleNamespace(UNIT_CLASS="unitless")
        day = date(2026, 10, 1)
        rows = {ean: {day: self.row(ean, day, "2")} for ean in ("a", "b", "free")}
        with patch.dict(sys.modules, modules):
            history = importlib.import_module("_edc_energy_test.history")
            for _ in range(2):
                history.async_import_energy_history(
                    SimpleNamespace(config=SimpleNamespace(language="cs")),
                    sse_id=1,
                    sse_name="Example group",
                    target_days=rows,
                    options={
                        "energy_targets": ["a", "b"],
                        "ean_settings": {"b": {"price": "3"}},
                    },
                    sale_price=Decimal(2),
                    today=date(2026, 10, 2),
                    local_tz=UTC,
                )
        calls = recorder.async_add_external_statistics.call_args_list
        self.assertEqual(len(calls), 12)
        for index in range(6):
            self.assertEqual(calls[index].args[1:], calls[index + 6].args[1:])
            metadata, points = calls[index].args[1:]
            self.assertTrue(metadata["has_sum"])
            self.assertEqual(metadata["mean_type"], 0)
            self.assertEqual(metadata["source"], "edc_sharing")
            self.assertTrue(all(point["start"].tzinfo is UTC for point in points))
        self.assertEqual(calls[0].args[1]["unit_of_measurement"], "CZK")
        self.assertEqual(calls[0].args[2][-1]["sum"], 10)
        self.assertEqual(calls[1].args[1]["unit_of_measurement"], "kWh")
        self.assertEqual(calls[1].args[2][-1]["sum"], 4)

    def test_selected_targets_use_individual_prices_and_skip_today(self):
        day = date(2026, 10, 1)
        today = date(2026, 10, 2)
        rows = {
            ean: {day: self.row(ean, day, "2"), today: self.row(ean, today, "9")}
            for ean in ("paid-a", "paid-b", "free")
        }
        values = self.energy.daily_energy_values(
            rows,
            ("paid-a", "paid-b"),
            {"ean_settings": {"paid-b": {"price": "3.5"}}},
            Decimal(2),
            today,
        )
        self.assertEqual(values, {day: (Decimal(4), Decimal(11))})

    def test_empty_selection_missing_target_and_invalid_values(self):
        day = date(2026, 10, 1)
        today = date(2026, 10, 3)
        rows = {"a": {day: self.row("a", day, "2")}}
        for selection in ((), ("a", "missing")):
            self.assertEqual(
                self.energy.daily_energy_values(rows, selection, {}, Decimal(2), today),
                {},
            )
        for value in ("NaN", "-1", "Infinity"):
            rows["a"][day] = self.row("a", day, value)
            self.assertEqual(
                self.energy.daily_energy_values(rows, ("a",), {}, Decimal(2), today), {}
            )

    def test_selection_defaults_off_and_identity_is_order_independent(self):
        self.assertEqual(self.energy.energy_targets({}), ())
        self.assertEqual(self.energy.energy_targets({"energy_targets": "a"}), ())
        self.assertEqual(
            self.energy.energy_targets({"energy_targets": ["b", "a", "a"]}), ("a", "b")
        )
        identifier = self.energy.energy_statistic_id(1, ("a", "b"), "revenue")
        self.assertEqual(
            identifier, self.energy.energy_statistic_id(1, ("b", "a"), "revenue")
        )
        self.assertNotEqual(
            identifier, self.energy.energy_statistic_id(1, ("a",), "revenue")
        )

    def test_restart_overlap_and_correction_rebuild_without_double_counting(self):
        first, second = date(2026, 9, 30), date(2026, 10, 1)
        values = {first: Decimal(4), second: Decimal(7)}
        points = self.energy.cumulative_daily_points(values, UTC)
        self.assertEqual(points, self.energy.cumulative_daily_points(dict(values), UTC))
        values.update({second: Decimal(7)})
        self.assertEqual(points, self.energy.cumulative_daily_points(values, UTC))
        values[first] = Decimal(5)
        corrected = self.energy.cumulative_daily_points(values, UTC)
        self.assertEqual(corrected[-1]["sum"], 12)
        self.assertEqual(corrected[-1]["sum"] - corrected[-2]["sum"], 7)

    def test_older_backfill_rebuilds_all_later_sums_and_preserves_first_day(self):
        day = date(2026, 10, 1)
        older = date(2026, 9, 30)
        points = self.energy.cumulative_daily_points({day: Decimal(7)}, UTC)
        self.assertEqual(points[0]["sum"], 0)
        self.assertEqual(points[-1]["sum"], 7)
        expanded = self.energy.cumulative_daily_points(
            {older: Decimal(4), day: Decimal(7)}, UTC
        )
        self.assertEqual(expanded[-1]["sum"], 11)
        self.assertEqual(expanded[-1]["sum"] - expanded[-2]["sum"], 7)

    def test_dst_daily_booking_uses_the_last_real_hour(self):
        for day, expected in (
            (date(2026, 3, 29), datetime(2026, 3, 29, 21, tzinfo=UTC)),
            (date(2026, 10, 25), datetime(2026, 10, 25, 22, tzinfo=UTC)),
        ):
            points = self.energy.cumulative_daily_points({day: Decimal(7)}, PRAGUE_2026)
            self.assertEqual(points[-1]["start"], expected)
            self.assertEqual(points[-1]["sum"] - points[0]["sum"], 7)
            self.assertEqual(len({p["start"] for p in points}), len(points))

    def test_missing_day_has_no_fabricated_amount(self):
        points = self.energy.cumulative_daily_points(
            {date(2026, 10, 1): Decimal(4), date(2026, 10, 3): Decimal(7)}, UTC
        )
        self.assertEqual(points[-1]["sum"], 11)
        self.assertFalse(any(p["start"].date() == date(2026, 10, 2) for p in points))
