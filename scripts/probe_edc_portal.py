"""Volitelný soukromý průchod portálem; bez --enabled nezahájí žádnou síť."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "edc_probe_contract", ROOT / "custom_components/edc_sharing/portal_contract.py"
)
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)
HOSTS = {"portal.edc-cr.cz", "api.portal.edc-cr.cz", "sso.portal.edc-cr.cz"}


async def probe(config: dict, storage: Path, baseline: dict | None) -> dict:
    """Jeden historický den / max. pět profilových požadavků, bez HAR/screenshotů.

    Config i storage-state zůstávají soukromé. Role/popisky dodá mapa ověřená
    na aktuálním portálu. Cizí origin nebo mutační endpoint se blokuje. API
    POST pouze čte profil. Neúspěšné přihlášení vyžaduje obnovení testovací
    session člověkem; tento nástroj nepřebírá cookies uživatelova prohlížeče.
    """
    from playwright.async_api import async_playwright

    count = 0
    blocked = False
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(
                storage_state=str(storage), service_workers="block"
            )

            async def route(request_route):
                nonlocal count, blocked
                request = request_route.request
                parsed = urlparse(request.url)
                allowed = parsed.scheme == "https" and parsed.hostname in HOSTS
                if request.method == "POST":
                    allowed = (
                        allowed
                        and parsed.path == contract.PROFILE_PATH
                        and parsed.hostname == "api.portal.edc-cr.cz"
                    )
                    count += 1
                    allowed = allowed and count <= 5
                elif request.method not in ("GET", "HEAD"):
                    allowed = False
                if not allowed:
                    blocked = True
                    await request_route.abort()
                else:
                    await request_route.continue_()

            await context.route("**/*", route)
            page = await context.new_page()
            page.set_default_timeout(20000)
            await page.goto("https://portal.edc-cr.cz/sprava-dat/zobrazeni-dat")
            group = page.get_by_role("combobox", name=config["group_label"], exact=True)
            if await group.count() == 0:
                group = page.locator("#mui-component-select-sseId")
            if await group.count() != 1:
                return {"status": "inconclusive", "reason": "group_control_changed"}
            await group.click()
            await page.get_by_role(
                "option", name=config["group_name"], exact=True
            ).click()
            await page.get_by_label(config["date_from_label"], exact=True).fill(
                config["date_from_display"]
            )
            await page.get_by_label(config["date_to_label"], exact=True).fill(
                config["date_to_display"]
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
                or payload.get("dateFrom") != config["date_from"]
                or payload.get("dateTo") != config["date_to"]
            ):
                return {"status": "inconclusive", "reason": "group_or_period_mismatch"}
            if len(await response.body()) > 5 * 1024 * 1024:
                return {"status": "inconclusive", "reason": "response_too_large"}
            observed = contract.profile_contract(payload, await response.json())
            result = contract.compare_contracts(baseline, observed) if baseline else {
                "status": "inconclusive", "reason": "baseline_required"}
            result.update(contract=observed, profile_requests=count)
            if blocked:
                result.update(status="inconclusive", reason="unapproved_request")
            return result
        finally:
            await browser.close()


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
            baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline else None
            result = asyncio.run(probe(config, args.storage_state, baseline))
        except Exception:  # noqa: BLE001 -- hranice nástroje nesmí vypsat privátní browser exception
            # Ani výjimka prohlížeče nesmí vypsat jméno, session či payload.
            result = {
                "status": "inconclusive",
                "reason": "browser_or_session_unavailable",
            }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
