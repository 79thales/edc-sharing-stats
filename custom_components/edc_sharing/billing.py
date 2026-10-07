"""Private-person settlements, independent of HA and existing energy statistics.

A charge is one target EAN/day, not a document. Documents are immutable views
of charge keys. Only explicit manual receipts affect the payable balance.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation
from hashlib import sha256
from typing import Any
from uuid import uuid4

from .const import (
    CONF_PAYMENT_ACCOUNT_NUMBER,
    CONF_PAYMENT_BANK_CODE,
    CONF_SALE_PRICE,
    DEFAULT_SALE_PRICE,
)
from .ean_settings import ean_location, ean_name, target_sale_price
from .payment import parse_czech_account
from .report_profiles import validate_profile

ZERO = Decimal(0)
CENT = Decimal("0.01")
PANEL_PATH = "edc-sharing-billing"


class BillingError(ValueError):
    """A public error code, never an exception containing private data."""


def decimal_value(value: object) -> Decimal:
    """Reject unknown, non-finite, negative and unreasonably large values."""
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number > Decimal("1e12"):
            raise ValueError
        return number
    except (InvalidOperation, ValueError, TypeError) as err:
        raise BillingError("invalid_amount") from err


def money(value: object) -> str:
    """Round currency for output, never raw shared energy or daily amounts."""
    return str(decimal_value(value).quantize(CENT, rounding=ROUND_HALF_UP))


def fingerprint(value: Any) -> str:
    """Bind confirmation to the exact server-side preview or routing."""
    return sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def profile_routing(profile: Mapping) -> str:
    """Changing recipients or scope requires a new explicitly previewed document."""
    return fingerprint(
        {
            key: profile.get(key)
            for key in (
                "id",
                "targets",
                "language",
                "report_scope",
                "target_eans",
                "finance",
                "group_finance_mode",
            )
        }
    )


def charge_key(ean: str, day: date) -> str:
    """Stable opaque internal key; full EAN is kept only in private local data."""
    return fingerprint([ean, day.isoformat()])


def _label(value: object, *, required: bool = False, limit: int = 300) -> str:
    if (
        not isinstance(value, str)
        or len(value) > limit
        or any(ord(c) < 32 and c not in "\n\t" for c in value)
    ):
        raise BillingError("invalid_parties")
    text = value.strip()
    if required and not text:
        raise BillingError("invalid_parties")
    return text


class BillingLedger:
    """No polling, bank access, automatic billing or writes to existing schemas."""

    def __init__(self, state: dict | None = None) -> None:
        self.state = (
            deepcopy(state)
            if state is not None
            else {
                "revision": 0,
                "next_number": 1,
                "settings": {"issuer": "", "issuer_address": "", "tracking": False},
                "charges": {},
                "documents": [],
                "payments": [],
            }
        )
        self._validate()

    def _validate(self) -> None:
        """Fail closed instead of silently resetting an unreadable financial store."""
        try:
            state = self.state
            if (
                not isinstance(state, dict)
                or type(state["revision"]) is not int
                or state["revision"] < 0
            ):
                raise ValueError
            if (
                type(state["next_number"]) is not int
                or not 1 <= state["next_number"] <= 1000000
            ):
                raise ValueError
            if (
                not isinstance(state["settings"], dict)
                or type(state["settings"]["tracking"]) is not bool
            ):
                raise ValueError
            if (
                not isinstance(state["charges"], dict)
                or not isinstance(state["documents"], list)
                or not isinstance(state["payments"], list)
            ):
                raise TypeError
            for key, row in state["charges"].items():
                if key != charge_key(row["ean"], date.fromisoformat(row["day"])):
                    raise ValueError
                decimal_value(row["amount"])
                if money(row["payable"]) != row["payable"]:
                    raise ValueError
                decimal_value(row["shared"])
                decimal_value(row["price"])
            for collection in (state["documents"], state["payments"]):
                ids = set()
                for item in collection:
                    if (
                        not isinstance(item, dict)
                        or item["id"] in ids
                        or not item["charge_keys"]
                    ):
                        raise ValueError
                    ids.add(item["id"])
                    if not set(item["charge_keys"]) <= state["charges"].keys():
                        raise ValueError
            for item in state["payments"]:
                decimal_value(item["amount"])
                if type(item["settles_keys"]) is not bool:
                    raise ValueError
                if (
                    Decimal(item["amount"]) <= 0
                    or money(item["amount"]) != item["amount"]
                ):
                    raise ValueError
                date.fromisoformat(item["paid_on"])
            for item in state["documents"]:
                if len(item["charge_keys"]) != len(set(item["charge_keys"])):
                    raise ValueError
                if item["total"] != money(
                    sum(
                        (
                            decimal_value(state["charges"][key]["payable"])
                            for key in item["charge_keys"]
                        ),
                        ZERO,
                    )
                ):
                    raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError) as err:
            raise BillingError("storage_invalid") from err

    def _changed(self) -> None:
        self.state["revision"] += 1

    def configure(self, *, issuer: str, issuer_address: str, tracking: bool) -> None:
        if type(tracking) is not bool:
            raise BillingError("invalid_settings")
        self.state["settings"] = {
            "issuer": _label(issuer, required=True),
            "issuer_address": _label(issuer_address),
            "tracking": tracking,
        }
        self._changed()

    def balance(self, keys, *, charges: dict | None = None) -> dict:
        """Do not infer how a partial receipt splits across EANs or dates."""
        charges = charges if charges is not None else self.state["charges"]
        keys = set(keys)
        receipts = [
            item for item in self.state["payments"] if not item.get("voided_at")
        ]
        settled = (
            set().union(
                *(set(item["charge_keys"]) for item in receipts if item["settles_keys"])
            )
            if receipts
            else set()
        )
        unsettled = keys - settled
        total = Decimal(
            money(sum((decimal_value(charges[key]["payable"]) for key in keys), ZERO))
        )
        remaining = Decimal(
            money(
                sum((decimal_value(charges[key]["payable"]) for key in unsettled), ZERO)
            )
        )
        ambiguous = []
        for item in receipts:
            if item["settles_keys"]:
                continue
            paid_keys = set(item["charge_keys"])
            if paid_keys <= unsettled:
                remaining -= decimal_value(item["amount"])
            elif paid_keys & unsettled:
                ambiguous.append(item["id"])
        if remaining < 0:
            raise BillingError("invalid_balance")
        return {
            "total": money(total),
            "confirmed": money(total - remaining),
            "remaining": money(remaining),
            "ambiguous": ambiguous,
        }

    def preview(
        self,
        *,
        profile: dict,
        rows: Mapping,
        group_days: Mapping,
        options: Mapping,
        group_name: str,
        start: date,
        end: date,
        today: date,
        issuer: str,
        issuer_address: str,
        recipient: str,
        recipient_address: str,
        due: date,
    ) -> dict:
        """Use cached daily aggregates only; end dates are inclusive in the UI."""
        try:
            profile = validate_profile(profile)
        except (TypeError, ValueError, KeyError) as err:
            raise BillingError("profile_required") from err
        if not profile["id"]:
            raise BillingError("profile_required")
        if not profile["finance"]:
            raise BillingError("finance_required")
        if end < start or end >= today or (end - start).days >= 3660:
            raise BillingError("invalid_period")
        if due < today:
            raise BillingError("invalid_due_date")
        group = profile["report_scope"] == "group"
        selected = (
            sorted(
                set(rows)
                | {
                    row["ean"]
                    for row in self.state["charges"].values()
                    if start.isoformat() <= row["day"] <= end.isoformat()
                }
            )
            if group
            else sorted(set(profile["target_eans"]))
        )
        if not selected:
            raise BillingError("no_targets")
        default_price = decimal_value(options.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE))
        charges, missing, keys = {}, {}, []
        dates = tuple(start + timedelta(days=i) for i in range((end - start).days + 1))
        for ean in selected:
            data = {row.day: row for row in rows.get(ean, ())}
            price = (
                default_price
                if group and profile["group_finance_mode"] == "group_price"
                else target_sale_price(ean, options, default_price)
            )
            price = decimal_value(price)
            for day in dates:
                key = charge_key(ean, day)
                if key in self.state["charges"]:
                    charges[key] = deepcopy(self.state["charges"][key])
                else:
                    row = data.get(day)
                    try:
                        if row is None:
                            raise BillingError("incomplete_data")
                        shared = decimal_value(row.shared)
                        value = decimal_value(shared * price)
                    except BillingError:
                        missing.setdefault(ean, []).append(day.isoformat())
                        continue
                    charges[key] = {
                        "ean": ean,
                        "name": ean_name(ean, options),
                        "location": ean_location(ean, options) or "",
                        "day": day.isoformat(),
                        "shared": str(shared),
                        "price": str(price),
                        "amount": str(value),
                    }
                keys.append(key)
        # Group billing needs every target day and a reconciled group total.
        # This checks presence/consistency of daily aggregates, not intraday quality.
        inconsistent = []
        if group:
            for day in dates:
                if all(
                    charge_key(ean, day) in self.state["charges"] for ean in selected
                ):
                    continue
                original = group_days.get(day)
                target_values = [
                    charges[key]["shared"]
                    for ean in selected
                    if (key := charge_key(ean, day)) in charges
                ]
                try:
                    if (
                        original is None
                        or len(target_values) != len(selected)
                        or abs(
                            decimal_value(original.shared)
                            - sum((decimal_value(v) for v in target_values), ZERO)
                        )
                        > Decimal("0.000001")
                    ):
                        inconsistent.append(day.isoformat())
                except BillingError:
                    inconsistent.append(day.isoformat())
        account = None
        if options.get(CONF_PAYMENT_ACCOUNT_NUMBER) or options.get(
            CONF_PAYMENT_BANK_CODE
        ):
            try:
                parsed = parse_czech_account(
                    options.get(CONF_PAYMENT_ACCOUNT_NUMBER),
                    options.get(CONF_PAYMENT_BANK_CODE),
                )
            except ValueError as err:
                raise BillingError("invalid_account") from err
            account = {
                "prefix": parsed.prefix,
                "number": parsed.number,
                "bank_code": parsed.bank_code,
            }
        self._allocate_cents(charges)
        balance = self.balance(keys, charges=charges)
        quote = {
            "revision": self.state["revision"],
            "profile_id": profile["id"],
            "profile_name": profile["name"],
            "routing": profile_routing(profile),
            "language": profile["language"],
            "scope": profile["report_scope"],
            "group_name": group_name,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "due": due.isoformat(),
            "issuer": _label(issuer, required=True),
            "issuer_address": _label(issuer_address),
            "recipient": _label(recipient, required=True),
            "recipient_address": _label(recipient_address),
            "account": account,
            "charges": charges,
            "charge_keys": sorted(keys),
            "balance": balance,
            "missing_days": missing,
            "inconsistent_days": inconsistent,
            "can_issue": bool(keys)
            and not missing
            and not inconsistent
            and not balance["ambiguous"],
        }
        quote["preview_id"] = fingerprint(quote)
        return quote

    def _allocate_cents(self, charges: dict) -> None:
        """Freeze cents once while retaining unrounded energy and raw value.

        Round new charges per EAN/issued range, then allocate residual cents
        by largest remainder (date as tie-breaker). Subranges and receipts use
        these same canonical cents, never independently rerounded raw values.
        """
        eans = {
            row["ean"]
            for key, row in charges.items()
            if key not in self.state["charges"]
        }
        for ean in eans:
            keys = [
                key
                for key, row in charges.items()
                if row["ean"] == ean and key not in self.state["charges"]
            ]
            floor = {
                key: decimal_value(charges[key]["amount"]).quantize(
                    CENT, rounding=ROUND_DOWN
                )
                for key in keys
            }
            target = Decimal(
                money(
                    sum((decimal_value(charges[key]["amount"]) for key in keys), ZERO)
                )
            )
            residual = int((target - sum(floor.values(), ZERO)) / CENT)
            ordered = sorted(
                keys,
                key=lambda key: (
                    -(decimal_value(charges[key]["amount"]) - floor[key]),
                    charges[key]["day"],
                ),
            )
            extra = set(ordered[:residual])
            for key in keys:
                charges[key]["payable"] = money(
                    floor[key] + (CENT if key in extra else ZERO)
                )

    def issue(self, quote: dict, *, now: str, request_id: str) -> dict:
        """Reissuing a statement never creates an additional charge."""
        for document in self.state["documents"]:
            if document["request_id"] == request_id:
                return deepcopy(document)
        if quote["balance"]["ambiguous"]:
            raise BillingError("ambiguous_payment")
        if not quote["can_issue"]:
            raise BillingError("incomplete_data")
        for document in self.state["documents"]:
            if all(
                document[key] == quote[key]
                for key in (
                    "profile_id",
                    "routing",
                    "charge_keys",
                    "issuer",
                    "issuer_address",
                    "recipient",
                    "recipient_address",
                    "account",
                    "due",
                )
            ):
                return deepcopy(document)
        sequence = self.state["next_number"]
        if sequence > 999999:
            raise BillingError("numbering_exhausted")
        year = date.fromisoformat(now[:10]).year
        document = {
            key: deepcopy(value)
            for key, value in quote.items()
            if key
            not in {
                "revision",
                "preview_id",
                "balance",
                "can_issue",
                "missing_days",
                "inconsistent_days",
                "charges",
            }
        }
        document.update(
            id=uuid4().hex,
            number=f"EDC-{year}-{sequence:06d}",
            variable_symbol=f"{year}{sequence:06d}",
            issued_at=now,
            request_id=request_id,
            total=quote["balance"]["total"],
            deliveries=[],
        )
        self.state["charges"].update(deepcopy(quote["charges"]))
        self.state["documents"].append(document)
        self.state["next_number"] += 1
        self._changed()
        return deepcopy(document)

    def document(self, document_id: str) -> dict:
        try:
            item = deepcopy(
                next(
                    item
                    for item in self.state["documents"]
                    if item["id"] == document_id
                )
            )
        except StopIteration as err:
            raise BillingError("document_not_found") from err
        item["balance"] = self.balance(item["charge_keys"])
        item["charges"] = {
            key: deepcopy(self.state["charges"][key]) for key in item["charge_keys"]
        }
        value = item["balance"]
        item["payment_status"] = (
            "allocation_required"
            if value["ambiguous"]
            else "no_payment_required"
            if value["total"] == "0.00"
            else "confirmed"
            if value["remaining"] == "0.00"
            else "partial"
            if value["confirmed"] != "0.00"
            else "unconfirmed"
        )
        return item

    def confirm_payment(
        self,
        document_id: str,
        *,
        amount: object,
        paid_on: date,
        now: str,
        request_id: str,
        start: date | None = None,
        end: date | None = None,
        ean: str | None = None,
    ) -> dict:
        """Internal manual information only; never claim a bank verified a receipt."""
        for item in self.state["payments"]:
            if item["request_id"] == request_id:
                return deepcopy(item)
        if not self.state["settings"]["tracking"]:
            raise BillingError("tracking_disabled")
        document = self.document(document_id)
        if paid_on > date.fromisoformat(now[:10]):
            raise BillingError("invalid_payment_date")
        if (start is None) != (end is None) or start and end and end < start:
            raise BillingError("invalid_period")
        if start and (
            start.isoformat() < document["start"] or end.isoformat() > document["end"]
        ):
            raise BillingError("invalid_period")
        keys = sorted(
            key
            for key, row in document["charges"].items()
            if (ean is None or row["ean"] == ean)
            and (start is None or start.isoformat() <= row["day"] <= end.isoformat())
        )
        if not keys:
            raise BillingError("no_targets")
        value = decimal_value(amount)
        if value <= 0 or value != value.quantize(CENT):
            raise BillingError("invalid_amount")
        balance = self.balance(keys)
        if balance["ambiguous"]:
            raise BillingError("ambiguous_payment")
        if value > Decimal(balance["remaining"]):
            raise BillingError("overpayment")
        receipt = {
            "id": uuid4().hex,
            "document_id": document_id,
            "request_id": request_id,
            "amount": money(value),
            "paid_on": paid_on.isoformat(),
            "recorded_at": now,
            "charge_keys": keys,
            "allocation_start": min(document["charges"][key]["day"] for key in keys),
            "allocation_end": max(document["charges"][key]["day"] for key in keys),
            "allocation_eans": sorted(
                {document["charges"][key]["ean"] for key in keys}
            ),
            "settles_keys": value == Decimal(balance["remaining"]),
            "voided_at": None,
        }
        self.state["payments"].append(receipt)
        self._changed()
        return deepcopy(receipt)

    def void_payment(self, payment_id: str, *, now: str, request_id: str) -> None:
        """Keep the audit record; reverse only an explicit manual confirmation."""
        for item in self.state["payments"]:
            if item["id"] == payment_id:
                if item.get("voided_at"):
                    return
                # A later full settlement may rely on this partial receipt.
                if any(
                    p["settles_keys"]
                    and not p.get("voided_at")
                    and p["id"] != payment_id
                    and set(item["charge_keys"]) <= set(p["charge_keys"])
                    for p in self.state["payments"]
                ):
                    raise BillingError("dependent_payment")
                item.update(voided_at=now, void_request_id=request_id)
                self._changed()
                return
        raise BillingError("payment_not_found")
