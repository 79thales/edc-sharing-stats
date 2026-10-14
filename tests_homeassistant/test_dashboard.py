"""Exercise the actual websocket permissions, registry and Lovelace API."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components import frontend
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.template import Template
from homeassistant.loader import async_get_integration
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import parse_yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.edc_sharing.dashboard import (
    PANEL_PATH,
    DashboardTarget,
    period_value_card,
    target_details_card,
)
from custom_components.edc_sharing.dashboard_api import (
    _registered_sources,
    async_register_dashboard_commands,
    async_setup_dashboard_generator,
)


def add_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain="edc_sharing",
        title="Example group",
        version=2,
        data={
            "sse_id": "example",
            "sse_name": "Example group",
            "username": "test@example.com",
            "password": "test-secret",
        },
        options={"sale_price": 2, "report_targets": ["notify.example"]},
    )
    entry.add_to_hass(hass)
    return entry


def preview_message(entry: MockConfigEntry, message_id: int = 1) -> dict:
    return {
        "id": message_id,
        "type": "edc_sharing/dashboard/preview",
        "entry_id": entry.entry_id,
        "title": "Test EDC",
        "url_path": "edc-test",
    }


async def test_target_value_registry_aliases_survive_renames(hass, entity_registry):
    """Reálné unique_id cen a částek nesmějí vytvořit falešný druhý EAN.

    Test nemění měření ani registraci v produkci. Syntetická přejmenování
    ověřují, že generator nevybírá peníze podle friendly_name obsahujícího
    stejná slova jako energetický senzor a nemění konfiguraci integrace.
    """
    entry = add_entry(hass)
    ean = "1111111111111111"
    keys = {
        "shared_latest_available_day": "shared_latest_available_day",
        "sharing_value_latest_available_day": "revenue_latest_available_day",
        "sharing_value_this_month": "revenue_this_month",
        "electricity_sale_price": "sale_price",
    }
    for raw, expected in keys.items():
        item = entity_registry.async_get_or_create(
            "sensor", "edc_sharing", f"example_target_{ean}_{raw}",
            config_entry=entry, suggested_object_id=f"test_{raw}",
        )
        entity_registry.async_update_entity(item.entity_id, new_entity_id=f"sensor.renamed_{expected}")
    before = dict(entry.options)
    with patch("custom_components.edc_sharing.api.EdcApiClient.async_login") as login:
        _, _, targets = _registered_sources(hass, entry)
        login.assert_not_called()
    assert len(targets) == 1
    assert targets[0].entities == {expected: f"sensor.renamed_{expected}" for expected in keys.values()}
    assert entry.options == before


async def test_target_markdown_distinguishes_energy_money_and_missing_values(hass):
    """HA vykreslí nativní hodnotové senzory, nikoli nový finanční výpočet."""
    bindings = {
        "shared_latest_available_day": "sensor.point_shared_day",
        "revenue_latest_available_day": "sensor.point_money_day",
        "shared_this_month": "sensor.point_shared_month",
        "revenue_this_month": "sensor.point_money_month",
        "sale_price": "sensor.point_price",
    }
    for entity, value, unit in (
        ("sensor.point_shared_day", "2.50", "kWh"),
        ("sensor.point_money_day", "5.000", "CZK"),
        ("sensor.point_shared_month", "42.11", "kWh"),
        ("sensor.point_money_month", "84.220", "CZK"),
        ("sensor.point_price", "2.0", "CZK/kWh"),
    ):
        hass.states.async_set(entity, value, {"unit_of_measurement": unit, "friendly_name": "Shared electricity value"})
    template = Template(target_details_card([DashboardTarget("Synthetic target", bindings)])["content"], hass)
    rendered = template.async_render()
    assert "2.50 kWh" in rendered and "5.00 CZK" in rendered
    assert "42.11 kWh" in rendered and "84.22 CZK" in rendered
    assert "2.00 CZK/kWh" in rendered and "5.00 kWh" not in rendered
    for invalid_state, unit in (("unavailable", "CZK"), ("nan", "CZK"), ("inf", "CZK"), ("5", "kWh")):
        hass.states.async_set("sensor.point_money_day", invalid_state, {"unit_of_measurement": unit})
        rendered = template.async_render()
        assert "**Hodnota sdílení:** —" in rendered
        assert "5.00 CZK" not in rendered


async def test_period_value_marks_current_price_and_does_not_zero_missing_days(hass):
    """Orientační cena neúplného období není faktura a mezera není nula."""
    entities = {"sale_price": "sensor.test_price", "surplus_utilization_this_week": "sensor.test_week"}
    hass.states.async_set("sensor.test_price", "2", {"unit_of_measurement": "CZK/kWh"})
    hass.states.async_set("sensor.test_week", "50", {"shared_kwh": 7.78, "available_days": 2})
    template = Template(period_value_card(entities)["content"], hass)
    rendered = template.async_render()
    assert "15.56 CZK" in rendered and "7.78 kWh" in rendered
    assert "aktuální ceně skupiny" in rendered
    assert "vystavená vyúčtování se nemění" in rendered
    hass.states.async_set("sensor.test_week", "unavailable", {"shared_kwh": 0, "available_days": 0})
    rendered = template.async_render()
    assert "0.00 CZK" not in rendered and "**—**" in rendered


async def test_bundled_value_template_uses_the_exact_generator_cards():
    """Přibalený YAML nesmí postupně zaostat za opravenou funkcí generátoru."""
    path = Path(__file__).parents[1] / "examples/dashboard-values.yaml"
    example = parse_yaml(path.read_text(encoding="utf-8"))
    sections = example["views"][1]["sections"]
    target_keys = (
        "shared_latest_available_day", "consumption_latest_available_day",
        "grid_purchase_latest_available_day", "sharing_coverage_latest_available_day",
        "revenue_latest_available_day", "shared_this_month", "consumption_this_month",
        "grid_purchase_this_month", "sharing_coverage_this_month", "revenue_this_month", "sale_price",
    )
    target = DashboardTarget("Ukázkové odběrné místo", {key: f"sensor.example_target_{key}" for key in target_keys})
    entities = {"sale_price": "sensor.example_group_price"} | {
        f"surplus_utilization_{period}": f"sensor.example_utilization_{period}"
        for period in ("latest_available_day", "this_week", "this_month", "this_year")
    }
    assert sections[0]["cards"][1]["content"].rstrip() == target_details_card([target])["content"].rstrip()
    assert sections[1]["cards"][1]["content"].rstrip() == period_value_card(entities)["content"].rstrip()


async def test_preview_uses_renamed_registry_entities_and_is_read_only(
    hass, hass_ws_client, entity_registry
):
    entry = add_entry(hass)
    enabled = entity_registry.async_get_or_create(
        "sensor",
        "edc_sharing",
        "example_shared_today",
        config_entry=entry,
        suggested_object_id="my_shared",
    )
    entity_registry.async_get_or_create(
        "sensor",
        "edc_sharing",
        "example_consumption_today",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    entity_registry.async_update_entity(
        enabled.entity_id, new_entity_id="sensor.user_renamed"
    )
    hass.states.async_set(
        "sensor.user_renamed",
        "12.3",
        {"daily_statistic_id": "edc_sharing:example_shared_daily"},
    )
    async_register_dashboard_commands(hass)
    client = await hass_ws_client(hass)
    with patch("custom_components.edc_sharing.api.EdcApiClient.async_login") as login:
        await client.send_json(preview_message(entry))
        result = await client.receive_json()
        login.assert_not_called()
    assert result["success"]
    data = result["result"]
    text = json.dumps(data)
    assert "sensor.user_renamed" in text
    assert "edc_sharing:example_shared_daily" in text
    assert "consumption_today" in data["missing_entities"]
    assert "test-secret" not in text and "test@example.com" not in text
    assert "notify.example" not in text
    assert parse_yaml(data["yaml"]) == data["config"]
    assert entry.options == {"sale_price": 2, "report_targets": ["notify.example"]}


async def test_non_admin_cannot_list_generate_or_create(
    hass, hass_ws_client, hass_read_only_access_token
):
    assert await async_setup_component(hass, "lovelace", {"lovelace": {}})
    entry = add_entry(hass)
    async_register_dashboard_commands(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    for message in (
        {"id": 1, "type": "edc_sharing/dashboard/groups"},
        preview_message(entry, 2),
        {
            "id": 3,
            "type": "lovelace/dashboards/create",
            "url_path": "edc-forbidden",
            "title": "Forbidden",
        },
    ):
        await client.send_json(message)
        result = await client.receive_json()
        assert not result["success"]
        assert result["error"]["code"] == "unauthorized"


async def test_missing_entry_and_unsafe_path(hass, hass_ws_client):
    entry = add_entry(hass)
    async_register_dashboard_commands(hass)
    client = await hass_ws_client(hass)
    for number, changes, code in (
        (1, {"entry_id": "missing"}, "entry_not_found"),
        (2, {"url_path": "../overview"}, "invalid_path"),
    ):
        await client.send_json(preview_message(entry, number) | changes)
        result = await client.receive_json()
        assert not result["success"]
        assert result["error"]["code"] == code


async def test_hidden_admin_generator_panel_registration(
    hass, hass_ws_client, hass_client
):
    assert await async_setup_component(hass, "frontend", {})
    await async_setup_dashboard_generator(hass)
    assert frontend.async_panel_exists(hass, PANEL_PATH)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "get_panels"})
    response = await client.receive_json()
    panel = response["result"][PANEL_PATH]
    assert panel["require_admin"]
    assert panel["title"] is None
    assert not panel.get("config_panel_domain")
    module_url = panel["config"]["_panel_custom"]["module_url"]
    integration = await async_get_integration(hass, "edc_sharing")
    assert (
        module_url
        == f"/edc_sharing/dashboard-generator.js?v={integration.manifest['version']}"
    )
    http_client = await hass_client(hass)
    resource = await http_client.get(module_url)
    assert resource.status == 200
    source = await resource.text()
    assert (
        'id="back" class="back" href="/config/integrations/integration/edc_sharing"'
        in source
    )
    assert "Zpět do integrace" in source and "Back to integration" in source


# Recorder's database fixtures must be prepared before the hass fixture.
@pytest.mark.usefixtures("recorder_mock")
async def test_helper_panels_preserve_the_native_options_menu_for_each_group(
    hass, hass_ws_client
):
    from custom_components.edc_sharing.billing_api import async_setup_billing

    # The native flow manager also sets up the manifest's recorder dependency.
    assert await async_setup_component(hass, "frontend", {})
    first = add_entry(hass)
    second = MockConfigEntry(
        domain="edc_sharing",
        version=2,
        title="Another example group",
        data={"sse_id": "example-2", "sse_name": "Another example group"},
        options={"sale_price": 3},
    )
    second.add_to_hass(hass)
    await async_setup_dashboard_generator(hass)
    await async_setup_billing(hass)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "get_panels"})
    panels = (await client.receive_json())["result"]
    # This is the metadata HA uses to prefer a panel over the options flow.
    assert not any(
        panel.get("config_panel_domain") == "edc_sharing"
        for panel in panels.values()
    )
    for entry in (first, second):
        before = dict(entry.options)
        before_data = dict(entry.data)
        menu = await hass.config_entries.options.async_init(entry.entry_id)
        assert menu["type"] == "menu" and menu["step_id"] == "init"
        assert menu["menu_options"] == [
            "general",
            "ean_settings",
            "energy_settings",
            "payment_settings",
            "profiles",
            "dashboard",
            "billing",
        ]
        for tool, path in (
            ("dashboard", "/edc-sharing-dashboard"),
            ("billing", "/edc-sharing-billing"),
        ):
            form = await hass.config_entries.options.async_configure(
                menu["flow_id"], {"next_step_id": tool}
            )
            assert form["step_id"] == tool
            assert form["description_placeholders"]["url"] == (
                f"{path}?entry_id={entry.entry_id}"
            )
            menu = await hass.config_entries.options.async_configure(
                menu["flow_id"], {}
            )
            assert menu["step_id"] == "init"
        assert entry.options == before
        assert entry.data == before_data


async def test_core_lovelace_create_save_and_duplicate_protection(
    hass, hass_ws_client, entity_registry
):
    assert await async_setup_component(hass, "lovelace", {"lovelace": {}})
    entry = add_entry(hass)
    async_register_dashboard_commands(hass)
    client = await hass_ws_client(hass)
    await client.send_json(preview_message(entry))
    preview = (await client.receive_json())["result"]
    await client.send_json(
        {
            "id": 2,
            "type": "lovelace/dashboards/create",
            "url_path": "edc-test",
            "title": "Test EDC",
            "require_admin": True,
            "show_in_sidebar": True,
        }
    )
    assert (await client.receive_json())["success"]
    await client.send_json(
        {
            "id": 3,
            "type": "lovelace/config/save",
            "url_path": "edc-test",
            "config": preview["config"],
        }
    )
    assert (await client.receive_json())["success"]
    await client.send_json({"id": 4, "type": "lovelace/config", "url_path": "edc-test"})
    assert (await client.receive_json())["result"] == preview["config"]
    await client.send_json(
        {
            "id": 5,
            "type": "lovelace/dashboards/create",
            "url_path": "edc-test",
            "title": "Do not overwrite",
        }
    )
    assert not (await client.receive_json())["success"]
    await client.send_json({"id": 6, "type": "lovelace/config", "url_path": "edc-test"})
    assert (await client.receive_json())["result"] == preview["config"]


async def test_existing_generator_path_is_not_overwritten(hass, hass_ws_client):
    assert await async_setup_component(hass, "frontend", {})
    frontend.async_register_built_in_panel(
        hass,
        component_name="map",
        frontend_url_path=PANEL_PATH,
        sidebar_title="Keep existing panel",
    )
    await async_setup_dashboard_generator(hass)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "get_panels"})
    panel = (await client.receive_json())["result"][PANEL_PATH]
    assert panel["component_name"] == "map"
    assert panel["title"] == "Keep existing panel"


async def test_dashboard_option_link_does_not_save_options(hass):
    from custom_components.edc_sharing.config_flow import EdcSharingOptionsFlow

    entry = add_entry(hass)
    flow = EdcSharingOptionsFlow(entry)
    flow.hass = hass
    result = await flow.async_step_dashboard()
    assert result["step_id"] == "dashboard"
    assert entry.entry_id in result["description_placeholders"]["url"]
    menu = await flow.async_step_dashboard({})
    assert menu["step_id"] == "init"
    assert entry.options == {"sale_price": 2, "report_targets": ["notify.example"]}


async def test_optional_generator_failure_does_not_block_edc_setup(hass):
    from custom_components.edc_sharing import async_setup

    with patch(
        "custom_components.edc_sharing.dashboard_api.async_setup_dashboard_generator",
        new=AsyncMock(side_effect=ValueError("Panel conflict")),
    ), patch(
        "custom_components.edc_sharing.billing_api.async_setup_billing", new=AsyncMock(),
    ):
        assert await async_setup(hass, {})


async def test_button_offers_link_without_creating_or_sending(hass):
    from custom_components.edc_sharing.button import EdcDashboardButton

    entry = add_entry(hass)
    button = EdcDashboardButton(entry)
    button.hass = hass
    with patch(
        "custom_components.edc_sharing.button.persistent_notification.async_create"
    ) as notify:
        await button.async_press()
        assert PANEL_PATH in notify.call_args.args[1]
        assert entry.entry_id in notify.call_args.args[1]
    assert button.unique_id == "example_generate_dashboard"
