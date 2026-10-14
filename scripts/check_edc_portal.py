"""Veřejná kontrola změny buildů; výsledný JSON neobsahuje soukromý profil."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "edc_public_contract", ROOT / "custom_components/edc_sharing/portal_contract.py"
)
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)
CALENDAR_SPEC = importlib.util.spec_from_file_location(
    "edc_calendar_monitor",
    ROOT / "custom_components/edc_sharing/calendar_maintenance.py",
)
calendar = importlib.util.module_from_spec(CALENDAR_SPEC)
CALENDAR_SPEC.loader.exec_module(calendar)
PORTAL = "https://portal.edc-cr.cz/"


def normalized_baseline(data: object) -> dict | None:
    """Nekopírovat neznámá pole případně špatně zvoleného privátního JSONu."""
    if not isinstance(data, dict):
        return None
    data = data.get("snapshot", data)
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("build_hash"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", data["build_hash"])
    ):
        return None
    result = {
        key: data.get(key)
        for key in ("build_hash", "asset_count", "calendar_link_count")
    }
    for key in ("etag", "last_modified"):
        value = data.get(key)
        result[key] = (
            value
            if isinstance(value, str)
            and len(value) < 512
            and "\r" not in value
            and "\n" not in value
            else None
        )
    return result


def check_calendar(*, opener=None) -> dict:
    """Jeden GET ověřeného oficiálního zdroje, 20 s / 2 MiB, bez přesměrování."""
    try:
        request = Request(
            calendar.CALENDAR_URL,
            headers={"User-Agent": "edc-sharing-stats-contract-monitor"},
        )
        with (opener or build_opener(NoRedirect())).open(
            request, timeout=20
        ) as response:
            body = response.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                return {"status": "inconclusive", "reason": "calendar_too_large"}
            return calendar.parse_calendar_feed(
                body.decode("utf-8-sig"), datetime.now(UTC)
            )
    except (HTTPError, URLError, TimeoutError, UnicodeError, OSError):
        return {"status": "unavailable", "reason": "calendar_transport"}


class NoRedirect(HTTPRedirectHandler):
    """Nepřesměrovávat monitor na jiný systém nebo přihlašovací URL s query."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(baseline: dict | None, *, opener=None) -> dict:
    """Jeden veřejný GET, 20 s / 2 MiB; nedostupnost není úspěšná kontrola API."""
    baseline = normalized_baseline(baseline)
    headers = {
        "User-Agent": "edc-sharing-stats-contract-monitor",
        "Accept": "text/html",
    }
    for source, target in (
        ("etag", "If-None-Match"),
        ("last_modified", "If-Modified-Since"),
    ):
        if baseline and isinstance(baseline.get(source), str):
            headers[target] = baseline[source]
    try:
        with (opener or build_opener(NoRedirect())).open(
            Request(PORTAL, headers=headers), timeout=20
        ) as response:
            body = response.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                return {"status": "inconclusive", "reason": "page_too_large"}
            snapshot = contract.public_snapshot(body.decode("utf-8"))
            snapshot.update(
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
            )
    except HTTPError as error:
        if error.code == 304 and baseline:
            return {"status": "ok", "scope": "public_build_only", "snapshot": baseline}
        return {"status": "unavailable", "http_status": error.code}
    except (URLError, TimeoutError, UnicodeError, OSError):
        return {"status": "unavailable", "reason": "transport"}
    if not snapshot["asset_count"]:
        return {
            "status": "inconclusive",
            "reason": "no_portal_assets",
            "snapshot": snapshot,
        }
    status = (
        "inconclusive"
        if not baseline
        else "changed"
        if baseline.get("build_hash") != snapshot["build_hash"]
        else "ok"
    )
    return {
        "status": status,
        "scope": "public_build_only",
        "snapshot": snapshot,
        "reason": "baseline_required" if not baseline else "build_comparison",
    }


def main() -> None:
    """Baseline schvaluje člověk; nový vzdálený build ji sám nepřepíše."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline", type=Path, default=ROOT / "examples/portal-public-baseline.json"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--calendar", action="store_true")
    args = parser.parse_args()
    baseline = (
        json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline else None
    )
    result = check(baseline)
    if args.calendar:
        result["calendar"] = check_calendar()
    if args.state:
        previous = (
            json.loads(args.state.read_text(encoding="utf-8"))
            if args.state.exists()
            else {}
        )
        state = {
            "status": result["status"],
            "build_hash": result.get("snapshot", {}).get("build_hash"),
            "calendar_status": result.get("calendar", {}).get("status"),
        }
        result["event"] = (
            None
            if previous == state
            else "recovered"
            if previous.get("status") in ("unavailable", "inconclusive")
            and state["status"] == "ok"
            else "observation_changed"
        )
        args.state.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
