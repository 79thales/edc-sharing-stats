"""Volitelný soukromý průchod portálem; bez --enabled nezahájí žádnou síť."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "edc_probe_contract", ROOT / "custom_components/edc_sharing/portal_contract.py"
)
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)
HOSTS = {"portal.edc-cr.cz", "api.portal.edc-cr.cz", "sso.portal.edc-cr.cz"}
TOKEN_PATH = "/auth/realms/edc/protocol/openid-connect/token"
PORTAL_CLIENT_ID = "a63c22a3-6e1d-4eac-b383-d06373da046a"


def request_allowed(method: str, url: str, form: str | None = None) -> bool:
    """Pevný allowlist ověřených čtecích a OIDC cest; žádný password grant.

    Každá nová API cesta vyžaduje ruční prověření kódu. Cizí asset lze blokovat,
    ale nesmí se z toho vyvodit změna kontraktu. Host/port/userinfo kontrolujeme
    před pokračováním požadavku, query se nikde neexportuje.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in HOSTS:
        return False
    if parsed.hostname == "api.portal.edc-cr.cz":
        return (method == "POST" and parsed.path == contract.PROFILE_PATH) or (
            method in ("GET", "HEAD") and parsed.path == "/api/v0/profiles-data/get-sse"
        )
    if parsed.hostname == "sso.portal.edc-cr.cz":
        if method == "POST" and parsed.path == TOKEN_PATH:
            fields = parse_qs(form or "", keep_blank_values=True)
            return fields.get("grant_type") in (
                ["refresh_token"],
                ["authorization_code"],
            ) and fields.get("client_id") == [PORTAL_CLIENT_ID]
        return method in ("GET", "HEAD") and parsed.path in (
            "/auth/realms/edc/protocol/openid-connect/auth",
            "/auth/realms/edc/login-status-iframe.html",
        )
    return method in ("GET", "HEAD") and (
        parsed.path
        in ("/", "/sprava-dat/zobrazeni-dat", "/favicon.ico", "/manifest.json")
        or parsed.path.startswith("/_next/static/")
    )


def validate_config(config: dict) -> list[dict]:
    """Historický referenční den a volitelný současný den, ne široký export."""
    if (
        not isinstance(config, dict)
        or type(config.get("sse_id")) is not int
        or config["sse_id"] <= 0
    ):
        raise ValueError("invalid_configuration")
    for key in (
        "group_label",
        "group_name",
        "date_from_label",
        "date_to_label",
        "show_button",
    ):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError("invalid_configuration")
    periods = [config]
    if "current" in config:
        if not isinstance(config["current"], dict):
            raise ValueError("invalid_configuration")
        periods.append(config["current"])
    for period in periods:
        for key in ("date_from", "date_to", "date_from_display", "date_to_display"):
            if not isinstance(period.get(key), str) or not period[key].strip():
                raise ValueError("invalid_configuration")
        if date.fromisoformat(period["date_from"]) != date.fromisoformat(
            period["date_to"]
        ):
            raise ValueError("single_day_required")
    return periods


@contextmanager
def probe_lock(storage: Path):
    """Jeden průchod na privátní profil, i napříč procesy; nikdy nepřebírat zámek.

    Běžné ukončení i zrušení zámek odstraní. Po pádu procesu soubor zůstane;
    správce jej smí odstranit až po ověření, že starý proces neběží.
    """
    path = storage.with_suffix(".probe.lock")
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


async def probe(config: dict, storage: Path, baseline: dict | None) -> dict:
    """Jeden historický den / max. pět profilových požadavků, bez HAR/screenshotů.

    Config i storage-state zůstávají soukromé. Role/popisky dodá mapa ověřená
    na aktuálním portálu. Cizí origin nebo mutační endpoint se blokuje. API
    POST pouze čte profil. Neúspěšné přihlášení vyžaduje obnovení testovací
    session člověkem; tento nástroj nepřebírá cookies uživatelova prohlížeče.
    """
    from playwright.async_api import async_playwright

    periods = validate_config(config)
    count = 0
    token_count = 0
    total_count = 0
    blocked = False
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(
                storage_state=str(storage), service_workers="block"
            )

            async def route(request_route):
                nonlocal count, blocked, token_count, total_count
                request = request_route.request
                parsed = urlparse(request.url)
                allowed = request_allowed(
                    request.method, request.url, request.post_data
                )
                total_count += 1
                allowed = allowed and total_count <= 80
                if (
                    request.method == "POST"
                    and parsed.hostname == "sso.portal.edc-cr.cz"
                ):
                    token_count += 1
                    allowed = allowed and token_count <= 2
                if (
                    request.method == "POST"
                    and parsed.hostname == "api.portal.edc-cr.cz"
                    and parsed.path == contract.PROFILE_PATH
                ):
                    allowed = allowed and count < 5
                    try:
                        payload = request.post_data_json
                        allowed = (
                            allowed
                            and payload.get("sseId") == config["sse_id"]
                            and any(
                                payload.get("dateFrom") == period["date_from"]
                                and payload.get("dateTo") == period["date_to"]
                                for period in periods
                            )
                        )
                    except (ValueError, AttributeError):
                        allowed = False
                    if allowed:
                        count += 1
                if not allowed:
                    blocked = True
                    await request_route.abort()
                else:
                    await request_route.continue_()

            await context.route("**/*", route)
            page = await context.new_page()
            page.set_default_timeout(20000)
            await page.goto("https://portal.edc-cr.cz/sprava-dat/zobrazeni-dat")
            if urlparse(page.url).hostname == "sso.portal.edc-cr.cz":
                return {
                    "status": "inconclusive",
                    "reason": "session_needs_manual_renewal",
                }
            group = page.get_by_role("combobox", name=config["group_label"], exact=True)
            if await group.count() == 0:
                group = page.locator("#mui-component-select-sseId")
            if await group.count() != 1:
                return {"status": "inconclusive", "reason": "group_control_changed"}
            await group.click()
            await page.get_by_role(
                "option", name=config["group_name"], exact=True
            ).click()
            observed = None
            current_result = None
            for index, period in enumerate(periods):
                await page.get_by_label(config["date_from_label"], exact=True).fill(
                    period["date_from_display"]
                )
                await page.get_by_label(config["date_to_label"], exact=True).fill(
                    period["date_to_display"]
                )
                async with page.expect_response(
                    lambda response: (
                        urlparse(response.url).hostname == "api.portal.edc-cr.cz"
                        and urlparse(response.url).path == contract.PROFILE_PATH
                    )
                ) as response_info:
                    await page.get_by_role(
                        "button", name=config["show_button"], exact=True
                    ).click()
                response = await response_info.value
                if response.status != 200:
                    return {
                        "status": "unavailable",
                        "http_status": response.status,
                        "profile_requests": count,
                    }
                payload = response.request.post_data_json
                if (
                    payload.get("sseId") != config["sse_id"]
                    or payload.get("dateFrom") != period["date_from"]
                    or payload.get("dateTo") != period["date_to"]
                ):
                    return {
                        "status": "inconclusive",
                        "reason": "group_or_period_mismatch",
                    }
                if len(await response.body()) > 5 * 1024 * 1024:
                    return {"status": "inconclusive", "reason": "response_too_large"}
                data = await response.json()
                candidate = contract.profile_contract(payload, data)
                if index == 0:
                    observed = candidate
                else:
                    current_result = (
                        "possible_publication_delay"
                        if data.get("content") == []
                        else "rows_present"
                    )
            if not observed.get("response", {}).get("time_layout"):
                return {
                    "status": "inconclusive",
                    "reason": "historical_reference_empty",
                    "profile_requests": count,
                }
            result = (
                contract.compare_contracts(baseline, observed)
                if baseline
                else {"status": "inconclusive", "reason": "baseline_required"}
            )
            result.update(contract=observed, profile_requests=count)
            if current_result:
                result["current_day"] = current_result
            if blocked:
                result.update(status="inconclusive", reason="unapproved_request")
            return result
        finally:
            await asyncio.wait_for(browser.close(), timeout=15)


async def bounded_probe(config, storage, baseline):
    """120 s celkem, včetně navigace; zrušení projde finally a zavře browser."""
    async with asyncio.timeout(120):
        return await probe(config, storage, baseline)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--storage-state", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    if not args.enabled:
        result = {"status": "disabled"}
    elif not all((args.config, args.storage_state)):
        result = {"status": "inconclusive", "reason": "private_configuration_required"}
    else:
        try:
            config = json.loads(args.config.read_text(encoding="utf-8"))
            baseline = (
                json.loads(args.baseline.read_text(encoding="utf-8"))
                if args.baseline
                else None
            )
            with probe_lock(args.storage_state):
                result = asyncio.run(
                    bounded_probe(config, args.storage_state, baseline)
                )
        except FileExistsError:
            result = {"status": "inconclusive", "reason": "probe_already_running"}
        except TimeoutError:
            result = {"status": "inconclusive", "reason": "probe_timeout"}
        except Exception:  # noqa: BLE001 -- hranice nástroje nesmí vypsat privátní browser exception
            # Ani výjimka prohlížeče nesmí vypsat jméno, session či payload.
            result = {
                "status": "inconclusive",
                "reason": "browser_or_session_unavailable",
            }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
