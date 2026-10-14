"""P0: vygenerovaný dashboard, skutečný Recorder a vykreslený nativní graf."""

import copy
import json
import re
from datetime import UTC, datetime

from homeassistant.setup import async_setup_component
from playwright.async_api import async_playwright, expect

from custom_components.edc_sharing.dashboard import build_dashboard
from tests_homeassistant.test_statistics_health import profile, queue


async def test_generated_graph_and_selected_day(
    hass,
    recorder_mock,
    hass_ws_client,
    hass_client,
    hass_access_token,
    socket_enabled,
    freezer,
    tmp_path,
):
    """Dvě známé hodiny zapsat a vykreslit; změna dne musí změnit období grafu.

    Prohlížeč používá nový izolovaný profil a testovací HA token vytvořený
    fixture. Není připojen k uživatelovu prohlížeči ani živému EDC/HA.
    Screenshot obsahuje pouze syntetickou skupinu a zadané testovací hodnoty.
    """
    moment = datetime(2026, 10, 14, 12, tzinfo=UTC)
    freezer.move_to(moment)
    await hass.config.async_set_time_zone("Europe/Prague")
    assert await async_setup_component(hass, "frontend", {})
    assert await async_setup_component(hass, "lovelace", {"lovelace": {}})
    assert await async_setup_component(hass, "energy", {})
    raw = profile()
    additional = copy.deepcopy(raw["content"])
    for row in additional:
        row["start"] = row["start"].replace("12:", "13:")
        row["end"] = (
            "14:00:00" if row["end"] == "13:00:00" else row["end"].replace("12:", "13:")
        )
        for value in row["values"]:
            value["v"] *= 2
    raw["content"].extend(additional)
    queue(hass, raw)
    await recorder_mock.async_block_till_done()
    config = build_dashboard(
        title="Synthetic EDC",
        url_path="edc-test",
        entities={},
        language="en",
        statistics={
            f"{metric}_hourly": f"edc_sharing:1_{metric}_hourly"
            for metric in ("shared", "consumption", "grid", "coverage")
        },
    )
    ws = await hass_ws_client(hass)
    await ws.send_json(
        {
            "id": 1,
            "type": "lovelace/dashboards/create",
            "url_path": "edc-test",
            "title": "Synthetic EDC",
            "require_admin": True,
            "show_in_sidebar": True,
        }
    )
    assert (await ws.receive_json())["success"]
    await ws.send_json(
        {
            "id": 2,
            "type": "lovelace/config/save",
            "url_path": "edc-test",
            "config": config,
        }
    )
    assert (await ws.receive_json())["success"]
    http = await hass_client()
    base_url = str(http.server.make_url("/")).rstrip("/")
    tokens = {
        "hassUrl": base_url,
        "access_token": hass_access_token,
        "refresh_token": "synthetic-refresh",
        "token_type": "Bearer",
        "client_id": base_url,
        "expires_in": 86400,
        "expires": int(moment.timestamp() * 1000) + 86400000,
    }
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(
                locale="en-US", timezone_id="Europe/Prague", service_workers="block"
            )
            await context.add_init_script(
                "localStorage.setItem('hassTokens', "
                + json.dumps(json.dumps(tokens))
                + ");"
            )
            # Samostatný test nesmí zahájit přístup do cloudové služby.
            await context.route("https://**/*", lambda route: route.abort())
            page = await context.new_page()
            await page.clock.install(time=moment)
            page.set_default_timeout(30000)
            await page.goto(base_url + "/edc-test/details")
            card = page.locator("hui-statistics-graph-card").filter(
                has_text="Sharing, consumption and grid – Whole group"
            )
            chart = card.locator("statistics-chart")
            await expect(chart).to_be_visible()
            handle = await chart.element_handle()
            await page.wait_for_function(
                "el => el.statisticsData?.['edc_sharing:1_shared_hourly']?.length === 2",
                arg=handle,
            )
            assert await chart.evaluate(
                "el => el.statisticsData['edc_sharing:1_shared_hourly'].map(row => row.mean)"
            ) == [4, 8]
            await expect(chart.locator("canvas")).to_be_visible()
            await card.screenshot(path=str(tmp_path / "hourly-graph.png"))
            await page.goto(base_url + "/edc-test/hourly-date")
            card = page.locator("hui-statistics-graph-card").filter(
                has_text="Sharing, consumption and grid – Whole group"
            )
            chart = card.locator("statistics-chart")
            await expect(
                card.get_by_text(re.compile("No statistics", re.IGNORECASE))
            ).to_be_visible()
            picker = page.locator("hui-energy-date-selection-card")
            previous = picker.get_by_role(
                "button", name=re.compile("previous", re.IGNORECASE)
            )
            await previous.click()
            handle = await chart.element_handle()
            await page.wait_for_function(
                "el => el.startTime?.getTime() === Date.parse('2026-10-12T22:00:00Z')",
                arg=handle,
            )
            await previous.click()
            await page.wait_for_function(
                "el => el.startTime?.getTime() === Date.parse('2026-10-11T22:00:00Z')",
                arg=handle,
            )
            await page.wait_for_function(
                "el => el.statisticsData?.['edc_sharing:1_shared_hourly']?.length === 2",
                arg=handle,
            )
            await expect(chart.locator("canvas")).to_be_visible()
        finally:
            await browser.close()
