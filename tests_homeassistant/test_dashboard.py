"""Exercise the actual websocket permissions, registry and Lovelace API."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from homeassistant.components import frontend
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import parse_yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.edc_sharing.dashboard import PANEL_PATH
from custom_components.edc_sharing.dashboard_api import (
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


async def test_hidden_admin_generator_panel_registration(hass, hass_ws_client):
    assert await async_setup_component(hass, "frontend", {})
    await async_setup_dashboard_generator(hass)
    assert frontend.async_panel_exists(hass, PANEL_PATH)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "get_panels"})
    response = await client.receive_json()
    panel = response["result"][PANEL_PATH]
    assert panel["require_admin"]
    assert panel["title"] is None
    assert panel["config"]["_panel_custom"]["module_url"].startswith("/edc_sharing/")


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
