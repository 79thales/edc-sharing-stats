"""Czech QR-payment helpers used by optional EDC report invoices.

The module intentionally contains no Home Assistant runtime dependency so the
financial payload can be tested independently from e-mail delivery.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
import unicodedata


class PaymentConfigurationError(ValueError):
    """Raised when a Czech bank account cannot be converted to an IBAN."""


@dataclass(frozen=True)
class CzechBankAccount:
    """A validated domestic Czech account, including an optional prefix."""

    prefix: str
    number: str
    bank_code: str

    @property
    def domestic(self) -> str:
        """Return the conventional domestic account representation."""
        account = f"{self.prefix}-" if self.prefix else ""
        return f"{account}{self.number}/{self.bank_code}"

    @property
    def iban(self) -> str:
        """Return the Czech IBAN calculated from the domestic account."""
        bban = f"{self.bank_code}{self.prefix.zfill(6)}{self.number.zfill(10)}"
        remainder = 0
        # IBAN validation moves CZ00 behind the BBAN: CZ -> 1235.
        for digit in f"{bban}123500":
            remainder = (remainder * 10 + int(digit)) % 97
        return f"CZ{98 - remainder:02d}{bban}"


@dataclass(frozen=True)
class PaymentRequest:
    """A ready-to-render payment request; no account is persisted here."""

    account: CzechBankAccount
    amount: Decimal
    message: str

    @property
    def spd(self) -> str:
        """Return a SPAYD 1.0 payload accepted by Czech banking apps."""
        return (
            f"SPD*1.0*ACC:{self.account.iban}*AM:{self.amount:.2f}*"
            f"CC:CZK*PT:IP*MSG:{self.message}"
        )


def parse_czech_account(account_number: object, bank_code: object) -> CzechBankAccount:
    """Validate a local Czech account number and derive its canonical parts."""
    raw_account = str(account_number or "").replace(" ", "")
    raw_bank = str(bank_code or "").replace(" ", "")
    matched = re.fullmatch(r"(?:(\d{1,6})-)?(\d{1,10})", raw_account)
    if matched is None or re.fullmatch(r"\d{4}", raw_bank) is None:
        raise PaymentConfigurationError("invalid Czech bank account")
    prefix, number = matched.groups(default="")
    return CzechBankAccount(prefix=prefix, number=number, bank_code=raw_bank)


def payment_message(group_name: object, period: object) -> str:
    """Build a compact, QR-safe payment note without control characters."""
    text = unicodedata.normalize("NFKD", str(group_name)).encode(
        "ascii", "ignore"
    ).decode("ascii")
    text = " ".join(text.replace("*", " ").split())
    return f"EDC sdileni {text} - {period}"[:60].rstrip()


def payment_amount(value: Decimal) -> Decimal | None:
    """Return the two-decimal payable amount, excluding zero or negative sums."""
    amount = value.quantize(Decimal("0.01"))
    return amount if amount > 0 else None


def write_payment_qr(path: str, payload: str) -> None:
    """Write a normal black-and-white QR PNG locally without a web service."""
    import qrcode  # Installed by the integration manifest only when needed.

    image = qrcode.make(payload)
    image.save(path)
