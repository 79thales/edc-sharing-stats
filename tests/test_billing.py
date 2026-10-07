"""Financial regressions: issuing is not paying, and overlap is not new debt."""

from __future__ import annotations

import importlib
import sys
import unittest
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType, SimpleNamespace

package = ModuleType("_edc_billing_test")
package.__path__ = [str(Path(__file__).parents[1] / "custom_components/edc_sharing")]
sys.modules[package.__name__] = package
billing = importlib.import_module(package.__name__ + ".billing")
calculation = importlib.import_module(package.__name__ + ".calculation")
profiles = importlib.import_module(package.__name__ + ".report_profiles")
BillingError, BillingLedger = billing.BillingError, billing.BillingLedger
TargetDailySharing = calculation.TargetDailySharing
default_profile = profiles.default_profile


def target_rows(ean="EAN-A", days=3, shared="10"):
    return tuple(
        TargetDailySharing(
            ean,
            date(2026, 1, day),
            Decimal(shared),
            Decimal(0),
            Decimal(shared),
            Decimal(100),
        )
        for day in range(1, days + 1)
    )


class BillingTest(unittest.TestCase):
    def setUp(self):
        self.ledger = BillingLedger()
        self.profile = default_profile("profile-a") | {
            "name": "Example customer",
            "targets": ["notify.example"],
            "report_scope": "target",
            "target_eans": ["EAN-A"],
        }
        self.rows = {"EAN-A": target_rows()}

    def preview(self, start=1, end=3, **updates):
        values = {
            "profile": self.profile,
            "rows": self.rows,
            "group_days": {},
            "options": {"sale_price": 2},
            "group_name": "Example sharing",
            "start": date(2026, 1, start),
            "end": date(2026, 1, end),
            "today": date(2026, 2, 1),
            "issuer": "Example supplier",
            "issuer_address": "",
            "recipient": "Example customer",
            "recipient_address": "",
            "due": date(2026, 2, 15),
        }
        return self.ledger.preview(**(values | updates))

    def issue(self, start=1, end=3, request_id="issue-a", **updates):
        return self.ledger.issue(
            self.preview(start, end, **updates),
            now="2026-02-01T09:00:00+01:00",
            request_id=request_id,
        )

    def pay(self, document, amount, request_id="pay-a", **updates):
        self.ledger.state["settings"]["tracking"] = True
        return self.ledger.confirm_payment(
            document["id"],
            amount=amount,
            paid_on=date(2026, 2, 2),
            now="2026-02-02T09:00:00+01:00",
            request_id=request_id,
            **updates,
        )

    def test_preview_does_not_write(self):
        before = deepcopy(self.ledger.state)
        quote = self.preview()
        self.assertEqual("60.00", quote["balance"]["remaining"])
        self.assertEqual(before, self.ledger.state)

    def test_issuing_or_sending_is_not_payment(self):
        document = self.issue()
        document["deliveries"] = [{"status": "handed_to_smtp"}]
        self.assertEqual("60.00", self.preview()["balance"]["remaining"])
        self.assertEqual([], self.ledger.state["payments"])

    def test_repeated_issue_is_one_document_and_one_set_of_charges(self):
        first = self.issue()
        second = self.issue(request_id="issue-b")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(1, len(self.ledger.state["documents"]))
        self.assertEqual(3, len(self.ledger.state["charges"]))

    def test_partial_confirmation_only_reduces_remaining(self):
        document = self.issue()
        self.pay(document, "20.00")
        balance = self.preview()["balance"]
        self.assertEqual("60.00", balance["total"])
        self.assertEqual("20.00", balance["confirmed"])
        self.assertEqual("40.00", balance["remaining"])

    def test_full_confirmation_covers_smaller_custom_period(self):
        self.pay(self.issue(), "60.00")
        self.assertEqual("0.00", self.preview(2, 2)["balance"]["remaining"])

    def test_partial_payment_is_not_guessed_for_partial_overlap(self):
        self.pay(self.issue(), "20.00")
        quote = self.preview(2, 2)
        self.assertTrue(quote["balance"]["ambiguous"])
        self.assertFalse(quote["can_issue"])
        with self.assertRaisesRegex(BillingError, "ambiguous_payment"):
            self.issue(2, 2, request_id="overlap")

    def test_explicit_payment_allocation_to_day_is_not_ambiguous(self):
        self.pay(
            self.issue(),
            "10.00",
            start=date(2026, 1, 2),
            end=date(2026, 1, 2),
            ean="EAN-A",
        )
        self.assertEqual("10.00", self.preview(2, 2)["balance"]["remaining"])
        self.assertEqual("50.00", self.preview()["balance"]["remaining"])

    def test_yearly_style_overlap_keeps_unconfirmed_amounts(self):
        monthly = self.issue(1, 1)
        annual = self.issue(1, 3, request_id="annual")
        self.assertEqual(
            "60.00", self.ledger.balance(annual["charge_keys"])["remaining"]
        )
        self.pay(monthly, "20.00")
        self.assertEqual(
            "40.00", self.ledger.balance(annual["charge_keys"])["remaining"]
        )
        self.assertEqual(3, len(self.ledger.state["charges"]))

    def test_final_payment_after_partial_payment_settles_without_double_count(self):
        document = self.issue()
        self.pay(document, "20.00")
        self.pay(document, "40.00", request_id="pay-b")
        self.assertEqual("0.00", self.preview()["balance"]["remaining"])
        self.assertEqual("0.00", self.preview(1, 1)["balance"]["remaining"])

    def test_void_confirmation_restores_offer_to_pay(self):
        payment = self.pay(self.issue(), "60.00")
        self.ledger.void_payment(
            payment["id"], now="2026-02-03T10:00:00+01:00", request_id="void-a"
        )
        self.assertEqual("60.00", self.preview()["balance"]["remaining"])
        self.assertEqual(1, len(self.ledger.state["payments"]))

    def test_snapshot_survives_price_and_data_corrections_and_restart(self):
        document = self.issue()
        self.ledger = BillingLedger(deepcopy(self.ledger.state))
        changed = self.preview(
            options={"sale_price": 9}, rows={"EAN-A": target_rows(shared="99")}
        )
        self.assertEqual("60.00", changed["balance"]["total"])
        self.assertEqual("60.00", self.ledger.document(document["id"])["total"])

    def test_new_days_use_current_price_but_existing_days_are_frozen(self):
        self.issue(1, 1)
        quote = self.preview(options={"sale_price": 3})
        self.assertEqual("80.00", quote["balance"]["total"])

    def test_missing_day_blocks_issue_without_treating_it_as_zero(self):
        quote = self.preview(rows={"EAN-A": (target_rows()[0], target_rows()[2])})
        self.assertEqual(["2026-01-02"], quote["missing_days"]["EAN-A"])
        self.assertFalse(quote["can_issue"])
        with self.assertRaisesRegex(BillingError, "incomplete_data"):
            self.issue(rows={"EAN-A": target_rows(days=1)})

    def test_frozen_day_stays_available_after_history_is_unavailable(self):
        self.issue()
        quote = self.preview(rows={})
        self.assertTrue(quote["can_issue"])
        self.assertEqual("60.00", quote["balance"]["total"])

    def test_unavailable_negative_and_nonfinite_data_block_issue(self):
        for value in ("-1", "NaN", "Infinity"):
            quote = self.preview(rows={"EAN-A": target_rows(shared=value)})
            self.assertFalse(quote["can_issue"])

    def test_future_reversed_and_too_long_periods_are_rejected(self):
        for start, end in (
            (date(2026, 1, 3), date(2026, 1, 1)),
            (date(2026, 1, 1), date(2026, 2, 1)),
            (date(2000, 1, 1), date(2026, 1, 1)),
        ):
            with self.assertRaisesRegex(BillingError, "invalid_period"):
                self.ledger.preview(
                    profile=self.profile,
                    rows=self.rows,
                    group_days={},
                    options={"sale_price": 2},
                    group_name="Example",
                    start=start,
                    end=end,
                    today=date(2026, 2, 1),
                    issuer="Example",
                    issuer_address="",
                    recipient="Example",
                    recipient_address="",
                    due=date(2026, 2, 15),
                )

    def test_payment_retries_are_idempotent_and_overpayments_rejected(self):
        document = self.issue()
        first = self.pay(document, "20.00")
        self.assertEqual(first["id"], self.pay(document, "20.00")["id"])
        self.assertEqual(1, len(self.ledger.state["payments"]))
        for amount in ("0", "-1", "NaN", "Infinity", "40.01", "1.001"):
            with self.assertRaises(BillingError):
                self.pay(document, amount, request_id="invalid-" + amount)

    def test_profiles_and_finance_are_required(self):
        for profile in (
            None,
            self.profile | {"finance": False},
            self.profile | {"id": ""},
        ):
            with self.assertRaises(BillingError):
                self.preview(profile=profile)

    def test_tracking_is_optional_and_disabled_by_default(self):
        self.assertFalse(self.ledger.state["settings"]["tracking"])
        document = self.issue()
        self.assertEqual(
            "unconfirmed", self.ledger.document(document["id"])["payment_status"]
        )

    def test_money_rounding_is_decimal_and_display_only(self):
        quote = self.preview(rows={"EAN-A": target_rows(shared="0.0025")})
        self.assertEqual("0.02", quote["balance"]["total"])
        self.assertEqual("0.0050", next(iter(quote["charges"].values()))["amount"])

    def test_group_profile_prices_and_consistency_are_explicit(self):
        rows = {"EAN-A": target_rows(), "EAN-B": target_rows(ean="EAN-B")}
        group_days = {
            date(2026, 1, day): SimpleNamespace(shared=Decimal(20)) for day in (1, 2, 3)
        }
        profile = self.profile | {
            "report_scope": "group",
            "target_eans": [],
            "group_finance_mode": "ean_prices",
        }
        quote = self.preview(
            profile=profile,
            rows=rows,
            group_days=group_days,
            options={"sale_price": 2, "ean_settings": {"EAN-B": {"price": "3"}}},
        )
        self.assertEqual("150.00", quote["balance"]["total"])
        self.assertTrue(quote["can_issue"])
        group_days[date(2026, 1, 2)] = SimpleNamespace(shared=Decimal(999))
        self.assertFalse(
            self.preview(profile=profile, rows=rows, group_days=group_days)["can_issue"]
        )

    def test_document_html_is_escaped_and_qr_is_remaining_not_original_total(self):
        render = importlib.import_module(package.__name__ + ".billing_document")
        doc = self.issue(
            recipient='<script>alert("x")</script>',
            options={
                "sale_price": 2,
                "payment_account_number": "123456789",
                "payment_bank_code": "0100",
            },
        )
        self.pay(doc, "20.00")
        document = self.ledger.document(doc["id"])
        html, text = render.render_settlement(document, "data:image/png;base64,AA==")
        self.assertNotIn('<script>alert("x")</script>', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("40.00 CZK", text)
        self.assertIn("data:image/png;base64,AA==", html)
        payload = render.settlement_payment_payload(document)
        self.assertIn("*AM:40.00*", payload)
        self.assertIn("*X-VS:", payload)
        self.pay(doc, "40.00", request_id="pay-b")
        self.assertIsNone(
            render.settlement_payment_payload(self.ledger.document(doc["id"]))
        )

    def test_invalid_store_and_disabled_tracking_fail_closed(self):
        with self.assertRaisesRegex(BillingError, "storage_invalid"):
            BillingLedger({"revision": 0})
        doc = self.issue()
        with self.assertRaisesRegex(BillingError, "tracking_disabled"):
            self.ledger.confirm_payment(
                doc["id"],
                amount="1",
                paid_on=date(2026, 2, 1),
                now="2026-02-01T10:00:00+01:00",
                request_id="payment-disabled",
            )


if __name__ == "__main__":
    unittest.main()
