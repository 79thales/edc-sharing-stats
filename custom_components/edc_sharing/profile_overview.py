"""Read-only, mobile-friendly overview of report profiles."""

from __future__ import annotations

import re
from datetime import datetime, tzinfo
from html import escape


def _text(value: str) -> str:
    """Keep user-supplied names as text in a Markdown description."""
    value = escape(" ".join(str(value).split()), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~\-])", r"\\\1", value)


def delivery_label(result: str, czech: bool) -> str:
    """Use the same status wording in the overview and profile detail."""
    labels = {
        "not_sent": ("Zatím neodesláno", "Not sent yet"),
        "sending": ("Odesílání probíhá", "Sending"),
        "interrupted": (
            "Přerušeno restartem nebo změnou nastavení",
            "Interrupted by restart or settings reload",
        ),
        "sent": ("Předáno příjemcům", "Handed off to recipients"),
        "failed": ("Selhalo", "Failed"),
        "partial_failure": (
            "Některým příjemcům se odeslání nezdařilo",
            "Some recipients failed",
        ),
        "no_new_data": (
            "Přeskočeno: nezměněná data nebo již odesláno",
            "Skipped: unchanged data or already sent",
        ),
        "not_loaded": ("Integrace není načtená", "Integration is not loaded"),
    }
    return labels.get(result, ("Stav není dostupný", "Status unavailable"))[
        0 if czech else 1
    ]


def _date_time(value: str, local_tz: tzinfo, czech: bool) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return "—"
    if parsed.tzinfo is None:
        return "—"
    return parsed.astimezone(local_tz).strftime(
        "%d. %m. %Y %H:%M:%S" if czech else "%Y-%m-%d %H:%M:%S"
    )


def format_overview(
    profiles: list[dict],
    recipients: dict[str, str],
    statuses: dict[str, dict],
    *,
    czech: bool,
    local_tz: tzinfo,
    ean_labels: dict[str, str] | None = None,
) -> str:
    """Describe every profile without sending mail, fetching data or saving state."""
    if not profiles:
        return (
            "Zatím nejsou nadefinované žádné profily. Vyberte **＋ Přidat profil** níže."
            if czech
            else "No profiles have been configured yet. Select **＋ Add profile** below."
        )
    enabled = sum(bool(p["enabled"]) for p in profiles)
    count = (
        f"Profily: **{len(profiles)}** · zapnuté: **{enabled}** · pozastavené: **{len(profiles) - enabled}**"
        if czech
        else f"Profiles: **{len(profiles)}** · enabled: **{enabled}** · paused: **{len(profiles) - enabled}**"
    )
    blocks = [count]
    period_names = dict(
        zip(
            ("daily", "weekly", "monthly", "yearly"),
            ("denní", "týdenní", "měsíční", "roční")
            if czech
            else ("daily", "weekly", "monthly", "yearly"),
            strict=True,
        )
    )
    weekdays = (
        ("po", "út", "st", "čt", "pá", "so", "ne")
        if czech
        else ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    )
    for profile in profiles:
        label = "Zapnuto" if czech else "Enabled"
        if not profile["enabled"]:
            label = "Pozastaveno" if czech else "Paused"
        lines = [f"### {_text(profile['name'])} — {label}"]
        targets = []
        for target in profile["targets"]:
            name = recipients.get(target)
            targets.append(
                f"{_text(name)} ({_text(target)})"
                if name
                else f"{_text(target)} — {'entita nenalezena' if czech else 'entity not found'}"
            )
        names = "; ".join(targets) or (
            "Nejsou vybraní příjemci" if czech else "No recipients selected"
        )
        lines.append(f"**{'Příjemci' if czech else 'Recipients'}:** {names}")
        if profile.get("report_scope", "group") == "target":
            scope = "; ".join(
                _text((ean_labels or {}).get(ean, ean))
                for ean in profile.get("target_eans", [])
            ) or ("Žádná místa" if czech else "No supply points")
        else:
            scope = "Celá skupina sdílení" if czech else "Whole sharing group"
        lines.append(f"**{'Odběrná místa' if czech else 'Supply points'}:** {scope}")
        lines.append(
            "Všichni příjemci tohoto profilu dostanou stejný obsah."
            if czech else "All recipients of this profile receive the same content."
        )
        if profile.get("finance", True) and profile.get("report_scope", "group") == "group":
            individual = profile.get("group_finance_mode") == "ean_prices"
            finance = (
                ("Součet podle cen jednotlivých EANů" if czech else "Sum using individual EAN prices")
                if individual else ("Cena celé skupiny" if czech else "Group price")
            )
            lines.append(f"**{'Finance' if czech else 'Finance'}:** {finance}")
        periods = ", ".join(period_names[p] for p in profile["periods"])
        combined = "souhrn v jednom e-mailu" if czech else "summary in one email"
        if not profile["combined"]:
            combined = "samostatné e-maily" if czech else "separate emails"
        lines.append(f"**{'Obsah' if czech else 'Content'}:** {periods} · {combined}")
        ranges = []
        for period in profile["periods"]:
            if period == "daily":
                scope = (
                    "poslední dostupný den EDC" if czech else "latest available EDC day"
                )
            else:
                current = profile["period_mode"] == "current" or (
                    profile["period_mode"] == "legacy" and period == "yearly"
                )
                scope = (
                    ("probíhající" if czech else "current")
                    if current
                    else (
                        "předchozí uzavřené období"
                        if czech
                        else "previous completed period"
                    )
                )
            ranges.append(f"{period_names[period]} = {scope}")
        period_scope = "; ".join(ranges)
        lines.append(f"**{'Rozsah' if czech else 'Range'}:** {period_scope}")
        frequency = profile["frequency"]
        if frequency == "daily":
            schedule = "denně" if czech else "daily"
        elif frequency == "weekly":
            schedule = ", ".join(weekdays[int(d)] for d in sorted(profile["weekdays"]))
        elif frequency == "monthly":
            schedule = (
                f"{profile['day']}. den každého měsíce"
                if czech
                else f"day {profile['day']} of every month"
            )
        else:
            schedule = (
                f"každoročně {profile['day']}. {profile['month']}."
                if czech
                else f"annually, month {profile['month']}, day {profile['day']}"
            )
        lines.append(
            f"**{'Rozvrh' if czech else 'Schedule'}:** {schedule}, {profile['time']}"
        )
        settings = ["čeština" if profile["language"] == "cs" else "English"]
        if profile["only_new"]:
            settings.append("jen při změně dat" if czech else "only when data changes")
        lines.append(
            f"**{'Jazyk a odesílání' if czech else 'Language and sending'}:** {' · '.join(settings)}"
        )
        state = statuses.get(profile["id"], {"result": "not_loaded"})
        lines.append(
            f"**{'Výsledek' if czech else 'Result'}:** {delivery_label(state['result'], czech)}"
        )
        for key, cs_label, en_label in (
            ("last_attempt", "Poslední pokus", "Last attempt"),
            ("last_success", "Poslední úspěšné předání", "Last successful handoff"),
            ("next_attempt", "Příští pokus", "Next attempt"),
        ):
            value = _date_time(state.get(key, ""), local_tz, czech)
            lines.append(f"**{cs_label if czech else en_label}:** {value}")
        blocks.append("\n\n".join(lines))
    return "\n\n---\n\n".join(blocks)
