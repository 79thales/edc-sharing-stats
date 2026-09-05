"""Report profile configuration and calendar rules, independent of HA runtime."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

CONF_REPORT_PROFILES = "report_profiles"
PERIODS = ("daily", "weekly", "monthly", "yearly")


def default_profile(profile_id: str = "") -> dict[str, Any]:
    """Return an editable profile; a new profile starts paused."""
    return {
        "id": profile_id,
        "name": "",
        "enabled": False,
        "targets": [],
        "language": "cs",
        "periods": ["daily"],
        "combined": True,
        "period_mode": "current",
        "frequency": "daily",
        "time": "08:00:00",
        "weekdays": ["0"],
        "day": 5,
        "month": 1,
        "only_new": False,
        "energy": True,
        "finance": True,
        "ean_mode": "masked",
    }


def configured_profiles(options: dict, language: str = "en") -> list[dict]:
    """Adapt the old schedules without changing saved options or manual buttons."""
    if CONF_REPORT_PROFILES in options:
        return [dict(p) for p in options[CONF_REPORT_PROFILES]]
    profiles = []
    for period in (*PERIODS, "summary"):
        if not options.get(f"{period}_report", False):
            continue
        profile = default_profile(f"legacy_{period}")
        profile.update(
            name=f"EDC — {period}",
            enabled=True,
            targets=options.get("report_targets", []),
            language=options.get("report_language", language),
            periods=list(PERIODS) if period == "summary" else [period],
            period_mode="legacy",
            ean_mode="full",
            frequency="weekly"
            if period == "weekly"
            else "monthly"
            if period in ("monthly", "yearly")
            else "daily",
            time=options.get("report_time", "07:30:00"),
            day=options.get("report_day", 5),
        )
        if isinstance(profile["targets"], str):
            profile["targets"] = [profile["targets"]]
        profiles.append(profile)
    return profiles


def validate_profile(profile: dict) -> dict:
    """Normalize UI input and reject unsafe or incomplete routing settings."""
    result = default_profile() | profile
    result["name"] = str(result["name"]).strip()
    if (
        not result["name"]
        or len(result["name"]) > 80
        or any(c in result["name"] for c in "\r\n")
    ):
        raise ValueError("invalid_profile")
    for key, choices in (
        ("language", ("cs", "en")),
        ("period_mode", ("current", "previous", "legacy")),
        ("frequency", ("daily", "weekly", "monthly", "yearly")),
        ("ean_mode", ("hidden", "masked", "full")),
    ):
        if result[key] not in choices:
            raise ValueError("invalid_profile")
    for key in ("enabled", "combined", "only_new", "energy", "finance"):
        if not isinstance(result[key], bool):
            raise TypeError("invalid_profile")
    for key in ("periods", "targets", "weekdays"):
        if not isinstance(result[key], list):
            raise TypeError("invalid_profile")
        result[key] = list(dict.fromkeys(result[key]))
    if not result["periods"] or any(p not in PERIODS for p in result["periods"]):
        raise ValueError("invalid_profile")
    if not result["targets"] or any(
        not isinstance(t, str) or not t.startswith("notify.") or len(t.split(".")) != 2
        for t in result["targets"]
    ):
        raise ValueError("invalid_profile")
    if not (result["energy"] or result["finance"]):
        raise ValueError("invalid_profile")
    if any(d not in tuple(str(i) for i in range(7)) for d in result["weekdays"]):
        raise ValueError("invalid_profile")
    if result["frequency"] == "weekly" and not result["weekdays"]:
        raise ValueError("invalid_profile")
    for key, maximum in (("day", 28), ("month", 12)):
        if int(result[key]) != result[key] or not 1 <= int(result[key]) <= maximum:
            raise ValueError("invalid_profile")
        result[key] = int(result[key])
    parsed = time.fromisoformat(result["time"])
    if parsed.tzinfo is not None or parsed.microsecond:
        raise ValueError("invalid_profile")
    result["time"] = parsed.isoformat()
    return result


def due_on(profile: dict, day: date) -> bool:
    """Check the local calendar independently from the report's period."""
    frequency = profile["frequency"]
    return (
        frequency == "daily"
        or frequency == "weekly"
        and str(day.weekday()) in profile["weekdays"]
        or frequency == "monthly"
        and day.day == profile["day"]
        or frequency == "yearly"
        and day.day == profile["day"]
        and day.month == profile["month"]
    )


def next_run(profile: dict, now: datetime) -> datetime | None:
    """Find a valid local occurrence; skip the missing spring DST time."""
    if not profile["enabled"] or not profile["targets"]:
        return None
    for offset in range(367):
        day = now.date() + timedelta(days=offset)
        if not due_on(profile, day):
            continue
        candidate = datetime.combine(
            day, time.fromisoformat(profile["time"]), now.tzinfo
        )
        if candidate.astimezone(UTC).astimezone(now.tzinfo).replace(
            tzinfo=None
        ) != candidate.replace(tzinfo=None):
            continue
        if candidate.astimezone(UTC) > now.astimezone(UTC):
            return candidate
    return None


def period_range(period: str, mode: str, today: date) -> tuple[date, date]:
    """Return a half-open calendar range; daily is handled from latest EDC data."""
    if mode == "legacy":
        mode = "current" if period == "yearly" else "previous"
    if period == "weekly":
        start = today - timedelta(days=today.weekday())
        return (
            (start, today + timedelta(days=1))
            if mode == "current"
            else (start - timedelta(days=7), start)
        )
    if period == "monthly":
        start = today.replace(day=1)
        return (
            (start, today + timedelta(days=1))
            if mode == "current"
            else ((start - timedelta(days=1)).replace(day=1), start)
        )
    if period == "yearly":
        start = date(today.year, 1, 1)
        return (
            (start, today + timedelta(days=1))
            if mode == "current"
            else (date(today.year - 1, 1, 1), start)
        )
    raise ValueError("invalid_period")
