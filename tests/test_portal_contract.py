"""P2: build není změna API, osobní data se nedostanou do kontraktu/diffu."""

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "portal_contract_test", ROOT / "custom_components/edc_sharing/portal_contract.py"
)
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


class PortalTests(unittest.TestCase):
    def test_contract_ignores_identity_measurements_and_order(self):
        payload = {
            "sseId": 42,
            "dateFrom": "2026-10-12",
            "dateTo": "2026-10-12",
            "calculationType": "DAILY",
            "inputData": True,
            "outputData": True,
            "fileName": "synthetic-person",
        }
        response = {
            "valueColumns": [{"ean": "synthetic-secret", "type": "O", "dir": "IN"}],
            "content": [
                {
                    "date": "2026-10-12",
                    "start": "12:00:00",
                    "end": "12:15:00",
                    "values": [42],
                }
            ],
        }
        first = contract.profile_contract(payload, response)
        payload.update(sseId=43, dateFrom="2026-10-13", dateTo="2026-10-13")
        second = contract.profile_contract(payload, response)
        self.assertEqual(first, second)
        self.assertNotIn("synthetic", json.dumps(first))
        self.assertEqual(contract.compare_contracts(first, second)["status"], "ok")
        second["request"]["dateFrom_format"] = "other"
        self.assertEqual(
            contract.compare_contracts(first, second)["differences"],
            ["request.dateFrom_format"],
        )

    def test_empty_reference_is_inconclusive(self):
        observed = contract.profile_contract({}, {"content": [], "valueColumns": []})
        self.assertEqual(
            contract.compare_contracts(observed, observed)["status"], "inconclusive"
        )

    def test_asset_change_does_not_claim_api_change(self):
        first = contract.public_snapshot(
            '<script src="/_next/static/a.js"></script><div nonce="secret">2026-10-12</div>'
        )
        same = contract.public_snapshot(
            '<div nonce="changed">2026-10-13</div><script src="/_next/static/a.js"></script>'
        )
        new = contract.public_snapshot('<script src="/_next/static/b.js"></script>')
        self.assertEqual(first, same)
        self.assertNotEqual(first["build_hash"], new["build_hash"])
        self.assertNotIn("secret", json.dumps(first))
