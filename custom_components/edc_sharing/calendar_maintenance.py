"""Oficiální ICS oznámení EDC: časový kontext, nikoli automatický důkaz chyby."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CALENDAR_URL = "https://www.edc-cr.cz/kalendar-edc.ics"


def _instant(key: str, value: str) -> datetime:
    """Zachovat UTC/TZID i datum bez času; odmítnout nejednoznačný DST čas."""
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    zone = "Europe/Prague"
    for part in key.split(";")[1:]:
        if part.startswith("TZID="):
            zone = part.removeprefix("TZID=")
    tz = ZoneInfo(zone)
    # Naivní čas je pouze mezikrok: níže ověřujeme oba foldy v uvedené zóně.
    local = datetime.strptime(value, "%Y%m%d" if len(value) == 8 else "%Y%m%dT%H%M%S")  # noqa: DTZ007
    candidates = set()
    for fold in (0, 1):
        aware = local.replace(tzinfo=tz, fold=fold)
        if aware.astimezone(UTC).astimezone(tz).replace(tzinfo=None) == local:
            candidates.add(aware.astimezone(UTC))
    if len(candidates) != 1:
        raise ValueError("Nejednoznačný nebo neexistující čas kalendáře.")
    return candidates.pop()


def parse_calendar_feed(text: str, now: datetime) -> dict:
    """Rozbalit ICS pokračovací řádky a vrátit jen bezpečné provozní údaje.

    UID, popisy a volné názvy událostí neexportovat. Není-li možné ověřit čas,
    neoznačit kalendář jako úplný. Odstávka SEBI/AFLEX není odstávkou sdílení.
    DTEND je mez bez koncového okamžiku/dne, jak určuje ICS.
    """
    if "BEGIN:VCALENDAR" not in text or "VERSION:2.0" not in text or "END:VCALENDAR" not in text:
        return {"status": "inconclusive", "reason": "unsupported_calendar"}
    lines = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    events = []
    current = None
    incomplete = False
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            summary = current.get("SUMMARY", ("", ""))[1].casefold()
            kind = (
                "maintenance"
                if "odstáv" in summary or "maintenance" in summary
                else "release"
                if "release" in summary
                else None
            )
            if kind:
                try:
                    start = _instant(*current["DTSTART"])
                    end = _instant(*current["DTEND"])
                    if end <= start or "RRULE" in current:
                        raise ValueError("Nepodporovaná délka/opakování události.")
                except (KeyError, ValueError, ZoneInfoNotFoundError):
                    incomplete = True
                else:
                    system = (
                        "edc_saku"
                        if "saku" in summary
                        else "sebi"
                        if "sebi" in summary
                        else "aflex"
                        if "aflex" in summary
                        else "unknown"
                    )
                    events.append(
                        {
                            "kind": kind,
                            "system": system,
                            "start": start.isoformat(),
                            "end_exclusive": end.isoformat(),
                            "active": start <= now.astimezone(UTC) < end,
                        }
                    )
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            current[key.split(";", 1)[0]] = (key, value)
    return {
        "status": "inconclusive" if incomplete or current is not None else "ok",
        "scope": "maintenance_context_only",
        "events": sorted(events, key=lambda event: event["start"]),
    }
