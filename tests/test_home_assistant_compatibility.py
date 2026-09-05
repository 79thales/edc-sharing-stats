"""Smoke tests executed with supported Home Assistant releases installed."""

from __future__ import annotations

import importlib
import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import patch


HOME_ASSISTANT_INSTALLED = importlib.util.find_spec("homeassistant") is not None


@unittest.skipUnless(
    HOME_ASSISTANT_INSTALLED,
    "Home Assistant is installed only in the compatibility CI job",
)
class HomeAssistantCompatibilityTest(unittest.TestCase):
    """Catch removed or renamed Home Assistant APIs before publishing."""

    def test_all_integration_modules_import(self) -> None:
        modules = (
            "custom_components.edc_sharing",
            "custom_components.edc_sharing.api",
            "custom_components.edc_sharing.button",
            "custom_components.edc_sharing.calculation",
            "custom_components.edc_sharing.config_flow",
            "custom_components.edc_sharing.coordinator",
            "custom_components.edc_sharing.history",
            "custom_components.edc_sharing.report",
            "custom_components.edc_sharing.profile_report",
            "custom_components.edc_sharing.profile_options",
            "custom_components.edc_sharing.report_profiles",
            "custom_components.edc_sharing.sensor",
        )

        for module in modules:
            with self.subTest(module=module):
                importlib.import_module(module)

    def test_new_diagnostic_sensor_api_is_available(self) -> None:
        from homeassistant.components.sensor import SensorDeviceClass

        from custom_components.edc_sharing.sensor import (
            EdcHistoryBackfillStatusSensor,
            EdcHistoryEarliestDateSensor,
        )

        status_sensor = object.__new__(EdcHistoryBackfillStatusSensor)
        earliest_date_sensor = object.__new__(EdcHistoryEarliestDateSensor)
        self.assertEqual(
            status_sensor.device_class,
            SensorDeviceClass.ENUM,
        )
        self.assertEqual(
            earliest_date_sensor.device_class,
            SensorDeviceClass.DATE,
        )

    def test_external_statistics_metadata_and_reimport_are_stable(self) -> None:
        from homeassistant.components.recorder.models import StatisticMeanType
        from homeassistant.const import UnitOfEnergy

        from custom_components.edc_sharing.calculation import HourlySharing
        from custom_components.edc_sharing.history import async_import_hourly_history

        def hour(start: datetime, shared: str) -> HourlySharing:
            value = Decimal(shared)
            return HourlySharing(
                start,
                value,
                Decimal("0"),
                value,
                value,
                value,
                Decimal("0"),
                Decimal("100"),
                Decimal("0"),
            )

        hours = (
            hour(datetime(2026, 10, 25, 0, tzinfo=UTC), "1"),
            hour(datetime(2026, 10, 25, 1, tzinfo=UTC), "2"),
        )
        hass = SimpleNamespace(config=SimpleNamespace(language="en"))

        with patch(
            "custom_components.edc_sharing.history.async_add_external_statistics"
        ) as add_statistics:
            for _ in range(2):
                async_import_hourly_history(
                    hass,
                    sse_id=1,
                    sse_name="Test group",
                    hours=hours,
                    sale_price=Decimal("2"),
                    now=datetime(2026, 10, 25, 3, tzinfo=UTC),
                    local_tz=UTC,
                )
            corrected_hours = (
                hour(datetime(2026, 10, 25, 0, tzinfo=UTC), "3"),
                hours[1],
            )
            async_import_hourly_history(
                hass,
                sse_id=1,
                sse_name="Test group",
                hours=corrected_hours,
                sale_price=Decimal("2"),
                now=datetime(2026, 10, 25, 3, tzinfo=UTC),
                local_tz=UTC,
            )

        self.assertEqual(add_statistics.call_count, 18)
        first_metadata = add_statistics.call_args_list[0].args[1]
        first_rows = add_statistics.call_args_list[0].args[2]
        repeated_rows = add_statistics.call_args_list[6].args[2]
        corrected_rows = add_statistics.call_args_list[12].args[2]
        self.assertEqual(first_metadata["source"], "edc_sharing")
        self.assertEqual(first_metadata["statistic_id"], "edc_sharing:1_shared_hourly")
        self.assertEqual(first_metadata["mean_type"], StatisticMeanType.ARITHMETIC)
        self.assertFalse(first_metadata["has_sum"])
        self.assertEqual(
            first_metadata["unit_of_measurement"], UnitOfEnergy.KILO_WATT_HOUR
        )
        self.assertEqual(
            tuple(row["start"] for row in first_rows),
            (
                datetime(2026, 10, 25, 0, tzinfo=UTC),
                datetime(2026, 10, 25, 1, tzinfo=UTC),
            ),
        )
        self.assertEqual(first_rows, repeated_rows)
        self.assertEqual(first_rows[0]["start"], corrected_rows[0]["start"])
        self.assertEqual(first_rows[0]["mean"], 1.0)
        self.assertEqual(corrected_rows[0]["mean"], 3.0)

    def test_dst_fold_with_home_assistant_timezone(self) -> None:
        from homeassistant.util import dt as dt_util

        from custom_components.edc_sharing.calculation import parse_hourly_profile

        local_tz = dt_util.get_time_zone("Europe/Prague")
        self.assertIsNotNone(local_tz)
        response = {
            "valueColumns": [
                {"ean": "producer", "type": "D", "dir": "IN"},
                {"ean": "producer", "type": "D", "dir": "OUT"},
                {"ean": "consumer", "type": "O", "dir": "IN"},
                {"ean": "consumer", "type": "O", "dir": "OUT"},
            ],
            "content": [
                {
                    "date": "2026-10-25",
                    "start": "02:00:00",
                    "values": [{"v": 1}, {"v": 0}, {"v": -1}, {"v": 0}],
                },
                {
                    "date": "2026-10-25",
                    "start": "02:00:00",
                    "values": [{"v": 2}, {"v": 0}, {"v": -2}, {"v": 0}],
                },
            ],
        }

        hours = parse_hourly_profile(response, local_tz=local_tz)

        self.assertEqual(
            tuple(row.start for row in hours),
            (
                datetime(2026, 10, 25, 0, tzinfo=UTC),
                datetime(2026, 10, 25, 1, tzinfo=UTC),
            ),
        )


@unittest.skipUnless(
    HOME_ASSISTANT_INSTALLED, "Requires Home Assistant compatibility CI"
)
class ReportProfileFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from custom_components.edc_sharing.config_flow import EdcSharingOptionsFlow

        self.entry = SimpleNamespace(
            options={
                "report_targets": ["notify.owner"],
                "daily_report": True,
                "sale_price": 2,
            },
            data={"sse_id": "test"},
        )
        self.flow = EdcSharingOptionsFlow(self.entry)
        self.flow.hass = SimpleNamespace(config=SimpleNamespace(language="cs"))
        self.flow.async_show_form = lambda **kwargs: kwargs
        self.flow.async_show_menu = lambda **kwargs: kwargs
        self.flow.async_create_entry = lambda **kwargs: kwargs

    async def test_profile_creation_validation_and_legacy_preservation(self):
        from custom_components.edc_sharing.report_profiles import default_profile

        menu = await self.flow.async_step_init()
        self.assertEqual(menu["menu_options"], ["general", "profiles"])
        form = await self.flow.async_step_profiles({"profile": "new"})
        values = default_profile() | {
            "name": "Accountant",
            "targets": ["notify.accountant"],
            "periods": ["monthly"],
            "frequency": "yearly",
        }
        values.pop("id")
        normalized = form["data_schema"](values)
        saved = await self.flow.async_step_profile_edit(normalized)
        self.assertEqual(saved["data"]["sale_price"], 2)
        self.assertEqual(saved["data"]["report_targets"], ["notify.owner"])
        self.assertEqual(len(saved["data"]["report_profiles"]), 2)
        self.assertEqual(saved["data"]["report_profiles"][0]["id"], "legacy_daily")
        self.assertEqual(
            saved["data"]["report_profiles"][1]["targets"], ["notify.accountant"]
        )

    async def test_invalid_profile_stays_in_form(self):
        await self.flow.async_step_profiles({"profile": "new"})
        response = await self.flow.async_step_profile_edit({"name": "No recipients"})
        self.assertEqual(response["errors"], {"base": "invalid_profile"})

    async def test_duplicate_is_paused_and_has_new_identity(self):
        await self.flow.async_step_profiles({"profile": "legacy_daily"})
        await self.flow.async_step_profile_duplicate()
        self.assertNotEqual(self.flow._selected_profile["id"], "legacy_daily")
        self.assertFalse(self.flow._selected_profile["enabled"])

    async def test_delete_requires_confirmation_and_preserves_options(self):
        await self.flow.async_step_profiles({"profile": "legacy_daily"})
        canceled = await self.flow.async_step_profile_delete({"confirm": False})
        self.assertEqual(canceled["step_id"], "profile_manage")
        saved = await self.flow.async_step_profile_delete({"confirm": True})
        self.assertEqual(saved["data"]["report_profiles"], [])
        self.assertEqual(saved["data"]["sale_price"], 2)
