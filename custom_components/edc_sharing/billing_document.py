"""Escaped, self-contained settlement HTML and plain-text email fallback."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from html import escape

from .billing import money
from .payment import CzechBankAccount, PaymentRequest, payment_message


def settlement_payment_payload(document: dict, *, preview: bool = False) -> str | None:
    """A QR is an offer to pay the remaining balance, not payment confirmation."""
    if preview and not document.get("can_issue"):
        return None
    balance = document["balance"]
    account = document.get("account")
    if not account or balance["ambiguous"] or Decimal(balance["remaining"]) <= 0:
        return None
    eans = sorted({row["ean"] for row in document["charges"].values()})
    message = payment_message(
        document["group_name"],
        f"{document['start']}..{document['end']}",
        target_name=document["recipient"],
        target_ean=eans[0] if len(eans) == 1 else None,
    )
    payload = (
        PaymentRequest(
            CzechBankAccount(**account), Decimal(balance["remaining"]), message
        ).spd
    )
    # A preview must not allocate, guess or encode a placeholder variable symbol.
    return payload if preview else payload + f"*X-VS:{document['variable_symbol']}"


def render_settlement(
    document: dict, qr: str | None = None, preview: bool = False,
) -> tuple[str, str]:
    """No remote assets, scripts, tax calculation or unescaped user text."""
    cs = document["language"] == "cs"
    labels = (
        (
            "Vyúčtování sdílené elektřiny",
            "Vystavitel",
            "Odběratel",
            "Období včetně",
            "Splatnost",
            "Nasdíleno",
            "Cena",
            "Hodnota",
            "Celková hodnota",
            "Potvrzené úhrady",
            "Zbývá k úhradě",
            "Variabilní symbol",
            "Účet",
        )
        if cs
        else (
            "Shared electricity settlement",
            "Issued by",
            "Customer",
            "Period, inclusive",
            "Due date",
            "Shared",
            "Price",
            "Value",
            "Total value",
            "Confirmed payments",
            "Remaining to pay",
            "Variable symbol",
            "Account",
        )
    )
    (
        title,
        issuer,
        customer,
        period,
        due,
        shared,
        price,
        value,
        total,
        confirmed,
        remaining,
        vs,
        account_label,
    ) = labels
    disclaimer = (
        "Soukromé vyúčtování sdílení. Nejde o automaticky vytvořený daňový doklad ani o potvrzení bankovní platby. Vystavení a odeslání nejsou úhradou."
        if cs
        else "Private electricity-sharing settlement. This is not an automatically generated tax invoice or bank payment confirmation. Issuing and sending do not confirm payment."
    )
    note = (
        "Částky bez ručně potvrzené úhrady se nadále nabízejí k zaplacení. Opakované nebo překrývající se vyúčtování nepřidává další dluh za stejné sdílení. Ceny a podklady již vystavených dnů jsou zachované; nové dny používají cenu nastavenou při vystavení."
        if cs
        else "Amounts without manual payment confirmation remain offered for payment. Repeated or overlapping statements do not create additional debt for the same sharing. Previously issued days retain their price and data; new days use the price configured at issue time."
    )
    data_note = (
        "Úplnost znamená přítomnost uložených denních součtů, nikoli ověření každého intervalu EDC. Úhrady jsou pouze interní ruční evidence, bez přístupu k bance."
        if cs
        else "Completeness means cached daily totals are present, not that every EDC interval has been verified. Payments are an internal manual record only; no bank connection is used."
    )
    account = (
        CzechBankAccount(**document["account"]).domestic
        if document.get("account")
        else ("Nenastaven" if cs else "Not configured")
    )
    rows = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for row in document["charges"].values():
        key = (row["ean"], row["name"], row["location"], row["price"])
        rows[key][0] += Decimal(row["shared"])
        rows[key][1] += Decimal(row["payable"])
    table = []
    text_rows = []
    for (ean, name, location, rate), (energy, amount) in sorted(rows.items()):
        label = name + (f" — {location}" if location else "")
        table.append(
            f"<tr><td>{escape(label)}<br><small>EAN {escape(ean)}</small></td><td>{energy:.3f} kWh</td><td>{escape(rate)} CZK/kWh</td><td>{money(amount)} CZK</td></tr>"
        )
        text_rows.append(
            f"{label} / EAN {ean}: {energy:.3f} kWh × {rate} CZK/kWh = {money(amount)} CZK"
        )
    balance = document["balance"]
    uncertain = (
        (
            "Úhrada není pro tento částečný rozsah jednoznačně přiřaditelná. Částka k úhradě není potvrzená a QR je vypnuté; upravte přiřazení úhrad."
            if cs
            else "Payment allocation is ambiguous for this partial range. The payable balance is not confirmed and QR is disabled; review receipt allocation."
        )
        if balance["ambiguous"]
        else ""
    )
    fields = (
        (period, f"{document['start']} – {document['end']}"),
        (due, document["due"]),
        (account_label, account),
        (vs, document["variable_symbol"]),
        (total, f"{balance['total']} CZK"),
        (confirmed, f"{balance['confirmed']} CZK"),
        (remaining, "—" if uncertain else f"{balance['remaining']} CZK"),
    )
    details = "".join(
        f"<dt>{escape(label)}</dt><dd>{escape(content)}</dd>"
        for label, content in fields
    )
    preview_note = (
        (
            "Náhled QR platby – doklad ještě není vystaven. Neplaťte podle tohoto náhledu. "
            "Finální QR s variabilním symbolem se vytvoří až při vystavení."
            if cs
            else "QR payment preview – the document has not been issued. Do not pay from this preview. "
            "The final QR with its variable symbol is generated only on issue."
        )
        if preview and qr and not uncertain
        else ""
    )
    qr_html = (
        (f'<p class="warning">{escape(preview_note)}</p>' if preview_note else "")
        + f'<p><img alt="QR payment" width="260" height="260" src="{escape(qr, quote=True)}"></p>'
        if qr and not uncertain
        else ""
    )
    html = (
        '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)} {escape(document['number'])}</title>"
        "<style>body{font:15px/1.5 sans-serif;color:#172b30;background:#fff;max-width:920px;margin:24px auto;padding:20px}h1{font-size:25px;color:#009bbb}.parties{display:flex;gap:30px;flex-wrap:wrap}.party{flex:1;min-width:220px;white-space:pre-line}table{border-collapse:collapse;width:100%;margin:20px 0}th,td{text-align:left;border-bottom:1px solid #ccd;padding:10px}dt{font-weight:bold;float:left;clear:left;width:45%}dd{margin-left:47%;padding:4px}small,.note{color:#555}.warning{border:1px solid #d76;padding:12px}@media print{body{max-width:none;margin:0;padding:0}tr,img{break-inside:avoid}}</style></head><body>"
        f"<h1>{escape(title)}</h1><p><strong>{escape(document['number'])}</strong> · {escape(document['group_name'])}<br>{escape(document['issued_at'])}</p>"
        f'<div class="parties"><div class="party"><strong>{issuer}</strong><br>{escape(document["issuer"])}<br>{escape(document["issuer_address"])}</div>'
        f'<div class="party"><strong>{customer}</strong><br>{escape(document["recipient"])}<br>{escape(document["recipient_address"])}</div></div>'
        f"<table><thead><tr><th>{customer} / EAN</th><th>{shared}</th><th>{price}</th><th>{value}</th></tr></thead><tbody>{''.join(table)}</tbody></table>"
        f"<dl>{details}</dl>"
        + (f'<p class="warning">{escape(uncertain)}</p>' if uncertain else "")
        + qr_html
        + f'<p class="note">{escape(note)}</p><p class="note">{escape(data_note)}</p><p class="note">{escape(disclaimer)}</p></body></html>'
    )
    plain = "\n".join(
        [
            f"{title} {document['number']}",
            document["group_name"],
            f"{issuer}: {document['issuer']}\n{document['issuer_address']}",
            f"{customer}: {document['recipient']}\n{document['recipient_address']}",
            *text_rows,
            *(f"{key}: {content}" for key, content in fields),
            uncertain,
            *([preview_note] if preview_note else []),
            note,
            data_note,
            disclaimer,
        ]
    )
    return html, plain
