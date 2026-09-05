"""Exercise real report rendering/sending with mocked HA clock, storage and notify."""

import importlib
import sys
import unittest
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch


class ReportDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = datetime(2026, 9, 5, 8, tzinfo=UTC)
        self.saved = None
        testcase = self

        class Store:
            def __init__(self, *args):
                pass

            async def async_load(self):
                return deepcopy(testcase.saved)

            async def async_save(self, value):
                testcase.saved = deepcopy(value)

        class HomeAssistantError(Exception):
            pass

        names = (
            "homeassistant",
            "homeassistant.core",
            "homeassistant.exceptions",
            "homeassistant.helpers",
            "homeassistant.helpers.event",
            "homeassistant.helpers.storage",
            "homeassistant.util",
            "homeassistant.util.dt",
        )
        modules = {name: ModuleType(name) for name in names}
        modules["homeassistant.core"].HomeAssistant = object
        modules["homeassistant.core"].callback = lambda fn: fn
        modules["homeassistant.exceptions"].HomeAssistantError = HomeAssistantError
        modules["homeassistant.helpers.event"].async_track_time_change = (
            lambda *args, **kwargs: lambda: None
        )
        modules["homeassistant.helpers.storage"].Store = Store
        modules["homeassistant.util.dt"].now = lambda: self.now
        modules["homeassistant.util.dt"].as_local = lambda value: value
        modules["homeassistant.util.dt"].as_utc = lambda value: value.astimezone(UTC)
        package = ModuleType("_edc_delivery_test")
        package.__path__ = [
            str(Path(__file__).parents[1] / "custom_components/edc_sharing")
        ]
        modules[package.__name__] = package
        api = ModuleType(package.__name__ + ".api")
        api.EdcApiError = type("EdcApiError", (Exception,), {})
        api.EdcAuthenticationError = type("EdcAuthenticationError", (Exception,), {})
        modules[api.__name__] = api
        self.modules_patch = patch.dict(sys.modules, modules)
        self.modules_patch.start()
        self.addCleanup(self.modules_patch.stop)
        self.runtime = importlib.import_module(package.__name__ + ".profile_report")
        self.rules = importlib.import_module(package.__name__ + ".report_profiles")
        calculation = importlib.import_module(package.__name__ + ".calculation")
        self.error = HomeAssistantError
        self.hass = SimpleNamespace(
            services=SimpleNamespace(async_call=AsyncMock()),
            config=SimpleNamespace(language="cs"),
        )
        self.entry = SimpleNamespace(
            entry_id="test",
            options={},
            data={"sse_id": "test", "sse_name": "Test group", "sale_price": 2},
        )
        d = Decimal
        self.day = calculation.DailySharing(
            date(2026, 9, 3), d(10), d(6), d(4), d(7), d(4), d(3), d(40), d(0)
        )
        self.coordinator = SimpleNamespace(
            data=SimpleNamespace(latest_day=self.day.day, latest=self.day),
            eans=[
                SimpleNamespace(role="sharing", ean="producer-example"),
                SimpleNamespace(role="target", ean="consumer-example"),
            ],
        )
        reporter_class = importlib.import_module(
            package.__name__ + ".report"
        ).EdcReportManager
        self.reporter = reporter_class(self.hass, self.entry, self.coordinator)
        self.manager = self.runtime.ProfileReportManager(self.reporter)
        await self.manager.async_initialize()
        self.profile = self.rules.default_profile("one") | {
            "name": "Owner",
            "enabled": True,
            "targets": ["notify.one", "notify.two"],
        }

    async def test_profile_language_content_and_recipient_isolation(self):
        first = self.profile | {
            "targets": ["notify.one"],
            "language": "cs",
            "finance": False,
            "ean_mode": "hidden",
        }
        second = self.profile | {
            "id": "two",
            "targets": ["notify.two"],
            "language": "en",
            "energy": False,
        }
        await self.manager.async_send(first)
        await self.manager.async_send(second)
        calls = self.hass.services.async_call.call_args_list
        self.assertEqual(calls[0].kwargs["target"], {"entity_id": "notify.one"})
        self.assertEqual(calls[1].kwargs["target"], {"entity_id": "notify.two"})
        self.assertIn("Spotřeba: 10.00", calls[0].args[2]["message"])
        self.assertNotIn("CZK", calls[0].args[2]["message"])
        self.assertNotIn("EAN", calls[0].args[2]["message"])
        self.assertIn("Sharing value: 8.00 CZK", calls[1].args[2]["message"])
        self.assertNotIn("Consumption:", calls[1].args[2]["message"])
        self.assertNotIn("producer-example", calls[1].args[2]["message"])

    async def test_restart_and_duplicate_schedule_do_not_resend(self):
        await self.manager.async_send(self.profile, scheduled=True)
        self.assertEqual(self.hass.services.async_call.await_count, 2)
        restarted = self.runtime.ProfileReportManager(self.reporter)
        await restarted.async_initialize()
        await restarted.async_send(self.profile, scheduled=True)
        self.assertEqual(self.hass.services.async_call.await_count, 2)
        await restarted.async_send(self.profile)
        self.assertEqual(self.hass.services.async_call.await_count, 4)

    async def test_failed_recipient_does_not_block_others_or_leak_exception(self):
        self.hass.services.async_call.side_effect = [
            RuntimeError("private SMTP credentials"),
            None,
        ]
        with self.assertRaises(self.error) as error:
            await self.manager.async_send(self.profile)
        self.assertNotIn("private", str(error.exception))
        self.assertEqual(self.hass.services.async_call.await_count, 2)
        self.assertEqual(self.manager.state["one"]["result"], "partial_failure")
        self.assertNotIn("private", str(self.saved))
        self.hass.services.async_call.side_effect = None
        await self.manager.async_send(self.profile, scheduled=True)
        self.assertEqual(self.hass.services.async_call.await_count, 3)
        self.assertEqual(
            self.hass.services.async_call.call_args.kwargs["target"],
            {"entity_id": "notify.one"},
        )

    async def test_new_data_only_and_revised_data(self):
        profile = self.profile | {"only_new": True}
        await self.manager.async_send(profile, scheduled=True)
        self.now = datetime(2026, 9, 6, 8, tzinfo=UTC)
        await self.manager.async_send(profile, scheduled=True)
        self.assertEqual(self.hass.services.async_call.await_count, 2)
        from dataclasses import replace

        self.coordinator.data.latest = replace(self.day, shared=Decimal(5))
        await self.manager.async_send(profile, scheduled=True)
        self.assertEqual(self.hass.services.async_call.await_count, 4)

    async def test_current_period_missing_data_preview_and_combination(self):
        profile = self.profile | {"periods": ["daily", "monthly"], "combined": True}
        with patch.object(
            self.runtime.ProfileRenderer,
            "_async_fetch_days",
            AsyncMock(return_value=(self.day,)),
        ):
            combined = await self.manager.preview(profile)
            self.assertEqual(len(combined), 1)
            self.assertIn("(1/5)", combined[0][1])
            self.assertIn("Neúplné období", combined[0][1])
            separate = await self.manager.preview(profile | {"combined": False})
            self.assertEqual(len(separate), 2)
        self.hass.services.async_call.assert_not_awaited()
        self.assertIsNone(self.saved)

    async def test_only_new_ignores_advancing_calendar_heading(self):
        profile = self.profile | {"periods": ["monthly"], "only_new": True}
        with patch.object(
            self.runtime.ProfileRenderer,
            "_async_fetch_days",
            AsyncMock(return_value=(self.day,)),
        ):
            await self.manager.async_send(profile, scheduled=True)
            self.now = datetime(2026, 9, 6, 8, tzinfo=UTC)
            await self.manager.async_send(profile, scheduled=True)
        self.assertEqual(self.hass.services.async_call.await_count, 2)

    async def test_fetch_failure_sends_nothing_and_is_sanitized(self):
        profile = self.profile | {"periods": ["monthly"]}
        with patch.object(
            self.runtime.ProfileRenderer,
            "_async_fetch_days",
            AsyncMock(side_effect=ValueError("private token")),
        ):
            await self.manager.async_send(profile, scheduled=True)
        self.hass.services.async_call.assert_not_awaited()
        self.assertEqual(self.manager.state["one"]["result"], "failed")
        self.assertNotIn("private", str(self.saved))
