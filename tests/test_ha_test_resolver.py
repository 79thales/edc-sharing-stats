"""The compatibility matrix must keep the requested stable HA version."""

import unittest

from scripts.resolve_ha_tests import resolve_environment


class TestEnvironmentResolver(unittest.TestCase):
    def fetch(self, package, version):
        if package == "homeassistant":
            return {
                "info": {
                    "version": version or "2026.9.4",
                    "requires_python": ">=3.14.2",
                }
            }
        if version is None:
            return {
                "info": self.plugin("0.13.369", "2026.10.0b2"),
                "releases": {
                    "0.13.369": [{}],
                    "0.13.367": [{}],
                    "0.13.350": [{}],
                    "0.13.366": [{"yanked": True}],
                },
            }
        return {
            "info": self.plugin(
                version, "2026.9.4" if version == "0.13.367" else "2026.8.0"
            )
        }

    @staticmethod
    def plugin(version, core):
        return {
            "version": version,
            "requires_python": ">=3.14.2",
            "requires_dist": [f"homeassistant=={core}"],
        }

    def test_latest_stable_skips_beta_targeting_plugin(self):
        result = resolve_environment(fetch=self.fetch)
        self.assertEqual(
            result,
            {"homeassistant": "2026.9.4", "test_plugin": "0.13.367", "python": "3.14"},
        )

    def test_minimum_ha_uses_a_matching_plugin(self):
        self.assertEqual(
            resolve_environment("2026.8.0", self.fetch)["test_plugin"], "0.13.350"
        )

    def test_no_silent_substitution(self):
        with self.assertRaises(ValueError):
            resolve_environment("2026.9.3", self.fetch)
        with self.assertRaises(ValueError):
            resolve_environment("2026.10.0b2", self.fetch)
