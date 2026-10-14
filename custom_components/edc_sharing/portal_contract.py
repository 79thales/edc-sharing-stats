"""Anonymní porovnání kontraktu portálu; žádná síť ani automatická změna API."""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

PROFILE_PATH = "/api/v0/profiles-data/standard/overview"
FIELDS = {
    "sseId",
    "calculationType",
    "inputData",
    "outputData",
    "dateFrom",
    "dateTo",
    "fileName",
}


def _type(value) -> str:
    """Boolean není integer; otisk popisuje typ a nikdy skutečnou identitu."""
    if value is None:
        return "null"
    return {
        bool: "boolean",
        int: "integer",
        float: "number",
        str: "string",
        list: "array",
        dict: "object",
    }.get(type(value), "unknown")


def profile_contract(payload: dict, response: dict) -> dict:
    """Odvodit bezpečný otisk z pozorované čtecí odpovědi, neukládat měření.

    Hodnoty identifikátorů, fileName a vzdálené volné texty nevracíme. U enumu
    uchovat pouze známé hodnoty, ostatní označit unknown. Neznámé klíče žádosti
    hlásíme jen počtem: i název libovolného cizího klíče může obsahovat tajemství.
    """
    request = {key: _type(payload[key]) for key in sorted(FIELDS & payload.keys())}
    request["unrecognized_fields"] = len(payload.keys() - FIELDS)
    for flag in ("inputData", "outputData"):
        request[flag + "_value"] = (
            payload.get(flag) if type(payload.get(flag)) is bool else "unknown"
        )
    enum = payload.get("calculationType")
    request["calculation"] = (
        enum if enum in ("DAILY", "HOURLY", "QUARTER_HOURLY") else "unknown"
    )
    for key in ("dateFrom", "dateTo"):
        value = payload.get(key)
        request[key + "_format"] = (
            "date"
            if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
            else "other"
        )
    columns = response.get("valueColumns")
    rows = response.get("content")
    shape = {"valueColumns": _type(columns), "content": _type(rows)}
    if isinstance(columns, list):
        shape["column_roles"] = sorted(
            {
                f"{column.get('type')}:{column.get('dir')}"
                if column.get("type") in ("D", "O")
                and column.get("dir") in ("IN", "OUT")
                else "unknown"
                for column in columns
                if isinstance(column, dict)
            }
        )
        shape["units"] = sorted(
            {
                column.get("unit")
                if column.get("unit") in ("kWh", "Wh", "MWh", "%")
                else "implicit"
                if column.get("unit") is None
                else "unknown"
                for column in columns
                if isinstance(column, dict)
            }
        )
    if isinstance(rows, list) and rows:
        row_types = set()
        for row in rows:
            if not isinstance(row, dict):
                row_types.add("invalid")
                continue
            row_types.add(
                "interval"
                if row.get("start") and row.get("end")
                else "start_only"
                if row.get("start")
                else "daily"
            )
        shape["time_layout"] = sorted(row_types)
        shape["values_types"] = sorted(
            {_type(row.get("values")) for row in rows if isinstance(row, dict)}
        )
    return {"request": request, "response": shape}


def compare_contracts(baseline: dict, observed: dict) -> dict:
    """Rozlišit potvrzený strukturální rozdíl a neověřitelnou prázdnou odpověď."""
    if not observed.get("response", {}).get("time_layout"):
        return {
            "status": "inconclusive",
            "reason": "no_reference_rows",
            "differences": [],
        }
    differences = []
    for section in ("request", "response"):
        # Ani špatně zvolený soukromý baseline nesmí dostat vlastní tajné klíče
        # do veřejného rozdílu; názvy výstupu zná pouze naše schéma.
        allowed = (
            (
                FIELDS
                | {
                    "unrecognized_fields",
                    "calculation",
                    "dateFrom_format",
                    "dateTo_format",
                    "inputData_value",
                    "outputData_value",
                }
            )
            if section == "request"
            else {
                "valueColumns",
                "content",
                "column_roles",
                "units",
                "time_layout",
                "values_types",
            }
        )
        if (
            not isinstance(baseline.get(section), dict)
            or baseline[section].keys() - allowed
        ):
            return {
                "status": "inconclusive",
                "reason": "invalid_baseline",
                "differences": [],
            }
        for key in sorted(
            (baseline[section].keys() | observed.get(section, {}).keys()) & allowed
        ):
            if baseline.get(section, {}).get(key) != observed.get(section, {}).get(key):
                # Ve veřejném diffu jsou jen názvy našeho vlastního schématu.
                differences.append(f"{section}.{key}")
    return {"status": "changed" if differences else "ok", "differences": differences}


class _PublicPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = set()
        self.calendar_links = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and isinstance(attrs.get("src"), str):
            path = urlparse(attrs["src"]).path
            if path.startswith("/_next/static/") and path.endswith(".js"):
                self.assets.add(path)
        if (
            tag == "a"
            and isinstance(attrs.get("href"), str)
            and ".ics" in attrs["href"]
        ):
            self.calendar_links.add(urlparse(attrs["href"]).path)


def public_snapshot(html: str) -> dict:
    """Hash veřejných build assetů signalizuje nasazení, nikoli rozbité API."""
    parser = _PublicPage()
    parser.feed(html)
    digest = hashlib.sha256("\n".join(sorted(parser.assets)).encode()).hexdigest()
    return {
        "asset_count": len(parser.assets),
        "build_hash": digest,
        "calendar_link_count": len(parser.calendar_links),
    }
