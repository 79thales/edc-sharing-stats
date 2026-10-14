"""P2: izolovaný probe je vypnutý, časově omezený a nemůže měnit EDC data."""

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SPEC = importlib.util.spec_from_file_location(
    "edc_probe_test", Path(__file__).parents[1] / "scripts/probe_edc_portal.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class ProbeGuardTests(unittest.TestCase):
    def test_only_known_read_and_oidc_requests_are_allowed(self):
        self.assertTrue(
            probe.request_allowed(
                "POST",
                "https://api.portal.edc-cr.cz/api/v0/profiles-data/standard/overview",
            )
        )
        self.assertTrue(
            probe.request_allowed(
                "POST",
                "https://sso.portal.edc-cr.cz" + probe.TOKEN_PATH,
                "grant_type=refresh_token&client_id=" + probe.PORTAL_CLIENT_ID,
            )
        )
        for method, url, form in (
            ("POST", "https://api.portal.edc-cr.cz/api/v0/allocations", None),
            ("GET", "https://api.portal.edc-cr.cz/api/v0/unverified", None),
            ("DELETE", "https://portal.edc-cr.cz/", None),
            (
                "POST",
                "https://sso.portal.edc-cr.cz" + probe.TOKEN_PATH,
                "grant_type=password&client_id=" + probe.PORTAL_CLIENT_ID,
            ),
            ("GET", "https://portal.edc-cr.cz.evil.example/", None),
            ("GET", "https://private@portal.edc-cr.cz/", None),
            ("GET", "http://portal.edc-cr.cz/", None),
        ):
            self.assertFalse(probe.request_allowed(method, url, form))

    def test_concurrent_probe_stops_without_overwriting_lock(self):
        with TemporaryDirectory() as directory:
            storage = Path(directory) / "synthetic.json"
            with probe.probe_lock(storage), self.assertRaises(FileExistsError):
                with probe.probe_lock(storage):
                    self.fail("Second process entered")
            self.assertFalse(storage.with_suffix(".probe.lock").exists())

    def test_multi_day_export_and_boolean_group_are_rejected(self):
        config = {
            key: "Synthetic"
            for key in (
                "group_label",
                "group_name",
                "date_from_label",
                "date_to_label",
                "show_button",
                "date_from_display",
                "date_to_display",
            )
        }
        config.update(sse_id=1, date_from="2026-10-12", date_to="2026-10-12")
        self.assertEqual(len(probe.validate_config(config)), 1)
        config["date_to"] = "2026-10-13"
        with self.assertRaises(ValueError):
            probe.validate_config(config)
        config.update(sse_id=True, date_to="2026-10-12")
        with self.assertRaises(ValueError):
            probe.validate_config(config)
