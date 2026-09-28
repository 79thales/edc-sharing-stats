"""Test QR-payment payload construction without Home Assistant or qrcode."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from decimal import Decimal
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "edc_payment",
    Path(__file__).parents[1] / "custom_components/edc_sharing/payment.py",
)
payment = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = payment
spec.loader.exec_module(payment)


class PaymentTests(unittest.TestCase):
    def test_domestic_account_becomes_a_valid_czech_iban(self):
        account = payment.parse_czech_account("120000001", "9999")
        self.assertEqual(account.domestic, "120000001/9999")
        self.assertEqual(account.iban[:2], "CZ")
        rearranged = account.iban[4:] + "1235" + account.iban[2:4]
        self.assertEqual(int(rearranged) % 97, 1)

    def test_account_prefix_and_invalid_inputs(self):
        account = payment.parse_czech_account("12-34", "9999")
        self.assertEqual(account.domestic, "12-34/9999")
        for number, bank in (("", "9999"), ("1", "99"), ("1-2-3", "9999")):
            with self.subTest(number=number, bank=bank):
                with self.assertRaises(payment.PaymentConfigurationError):
                    payment.parse_czech_account(number, bank)

    def test_spayd_payload_uses_two_decimal_positive_amount(self):
        account = payment.parse_czech_account("120000001", "9999")
        request = payment.PaymentRequest(
            account=account,
            amount=Decimal("12.30"),
            message=payment.payment_message("Dvořák's group", "mesic 2026-08"),
        )
        self.assertEqual(
            request.spd,
            f"SPD*1.0*ACC:{account.iban}*AM:12.30*CC:CZK*PT:IP*"
            "MSG:EDC sdileni Dvorak's group - mesic 2026-08",
        )

    def test_payment_message_is_ascii_compact_and_amount_never_is_zero(self):
        message = payment.payment_message("Dvořák * very long sharing group", "rok 2026")
        self.assertLessEqual(len(message), 60)
        self.assertTrue(message.isascii())
        self.assertNotIn("*", message)
        self.assertEqual(payment.payment_amount(Decimal("0")), None)
        self.assertEqual(payment.payment_amount(Decimal("-0.01")), None)
        self.assertEqual(payment.payment_amount(Decimal("1.005")), Decimal("1.00"))


if __name__ == "__main__":
    unittest.main()
