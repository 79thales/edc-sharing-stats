"""Smoke tests executed with supported Home Assistant releases installed."""

from __future__ import annotations

import importlib
import importlib.util
import unittest


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
