"""Real HA permissions, private Store, profile gating and SMTP handoff tests."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components import frontend, websocket_api
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.edc_sharing.billing import PANEL_PATH, BillingError
from custom_components.edc_sharing.billing_api import (
    BillingManager,
    async_setup_billing,
    websocket_billing,
    websocket_billing_groups,
)
from custom_components.edc_sharing.calculation import TargetDailySharing
from custom_components.edc_sharing.report_profiles import default_profile


def sample_entry(hass, *, profiles=True):
    profile = default_profile("customer-profile") | {
        "name": "Example customer",
        "report_scope": "target",
        "target_eans": ["EAN-A"],
        "targets": ["notify.example"],
    }
    entry = MockConfigEntry(
        domain="edc_sharing",
        version=2,
        title="Example group",
        data={
            "sse_id": "example",
            "sse_name": "Example group",
            "username": "test@example.com",
            "password": "test-secret",
        },
        options={
            "sale_price": 2,
            **({"report_profiles": [profile]} if profiles else {}),
        },
    )
    entry.add_to_hass(hass)
    rows = tuple(
        TargetDailySharing(
            "EAN-A",
            date(2026, 1, day),
            Decimal(10),
            Decimal(0),
            Decimal(10),
            Decimal(100),
        )
        for day in (1, 2, 3)
    )
    entry.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            data=SimpleNamespace(days=(), latest_day=date(2026, 1, 3)),
            target_days_for_range=lambda start, end: {
                "EAN-A": tuple(r for r in rows if start <= r.day < end)
            },
        )
    )
    return entry


def parameters():
    return {
        "profile_id": "customer-profile",
        "start": "2026-01-01",
        "end": "2026-01-03",
        "due": (dt_util.now().date() + timedelta(days=14)).isoformat(),
        "recipient": "Example customer",
        "recipient_address": "Example location",
    }


async def prepared_manager(hass):
    entry = sample_entry(hass)
    manager = BillingManager(hass, entry)
    await manager.action(
        "settings",
        {"issuer": "Example supplier", "tracking": True, "request_id": "configure-1"},
        0,
    )
    quote = await manager.action("preview", parameters(), None)
    document = await manager.action(
        "issue",
        {
            "parameters": parameters(),
            "preview_id": quote["preview_id"],
            "request_id": "issue-001",
        },
        1,
    )
    return manager, entry, document


def register_commands(hass):
    websocket_api.async_register_command(hass, websocket_billing)
    websocket_api.async_register_command(hass, websocket_billing_groups)


async def test_non_admin_cannot_read_or_mutate_financial_data(
    hass, hass_ws_client, hass_read_only_access_token
):
    entry = sample_entry(hass)
    register_commands(hass)
    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await client.send_json({"id": 1, "type": "edc_sharing/billing/groups"})
    assert not (await client.receive_json())["success"]
    for message_id, action in enumerate(
        (
            "overview",
            "preview",
            "settings",
            "issue",
            "payment",
            "send",
            "document",
            "void_payment",
        ),
        2,
    ):
        await client.send_json(
            {
                "id": message_id,
                "type": "edc_sharing/billing/action",
                "entry_id": entry.entry_id,
                "action": action,
            }
        )
        assert not (await client.receive_json())["success"]
    assert not hass.data.get("edc_sharing_billing_managers")


async def test_no_profile_requires_creation_and_does_not_adapt_legacy_buttons(hass):
    entry = sample_entry(hass, profiles=False)
    hass.config_entries.async_update_entry(
        entry,
        options=dict(entry.options)
        | {"daily_report": True, "report_targets": ["notify.example"]},
    )
    manager = BillingManager(hass, entry)
    before = dict(entry.options)
    overview = await manager.action("overview", {}, None)
    assert overview["profiles"] == []
    assert overview["documents"] == []
    assert "test-secret" not in json.dumps(overview)
    assert "test@example.com" not in json.dumps(overview)
    with pytest.raises(BillingError, match="profile_required"):
        await manager.action(
            "settings",
            {"issuer": "Example", "tracking": False, "request_id": "settings-1"},
            0,
        )
    with pytest.raises(BillingError, match="profile_required"):
        await manager.action("preview", parameters(), None)
    assert entry.options == before


async def test_private_store_round_trip_survives_restart_without_changing_history(hass):
    _manager, entry, document = await prepared_manager(hass)
    before = dict(entry.options)
    restored = BillingManager(hass, entry)
    saved = await restored.action("document", {"document_id": document["id"]}, None)
    assert saved["total"] == "60.00"
    assert saved["balance"]["remaining"] == "60.00"
    assert saved["number"] == document["number"]
    assert entry.options == before
    assert restored.store.version == 1
    assert entry.entry_id in restored.store.key and "example" in restored.store.key


async def test_preview_change_and_concurrent_revision_block_issue(hass):
    entry = sample_entry(hass)
    manager = BillingManager(hass, entry)
    await manager.action(
        "settings",
        {"issuer": "Example", "tracking": False, "request_id": "settings-1"},
        0,
    )
    quote = await manager.action("preview", parameters(), None)
    hass.config_entries.async_update_entry(
        entry, options=dict(entry.options) | {"sale_price": 3}
    )
    request = {
        "parameters": parameters(),
        "preview_id": quote["preview_id"],
        "request_id": "issue-001",
    }
    with pytest.raises(BillingError, match="preview_changed"):
        await manager.action("issue", request, 1)
    with pytest.raises(BillingError, match="stale_revision"):
        await manager.action("issue", request, 0)
    assert (await manager.action("overview", {}, None))["documents"] == []


async def test_storage_failure_leaves_financial_state_unchanged(hass):
    entry = sample_entry(hass)
    manager = BillingManager(hass, entry)
    await manager.action(
        "settings",
        {"issuer": "Example", "tracking": False, "request_id": "settings-1"},
        0,
    )
    quote = await manager.action("preview", parameters(), None)
    with (
        patch.object(
            manager.store,
            "async_save",
            new=AsyncMock(side_effect=OSError("private-path")),
        ),
        pytest.raises(OSError),
    ):
        await manager.action(
            "issue",
            {
                "parameters": parameters(),
                "preview_id": quote["preview_id"],
                "request_id": "issue-001",
            },
            1,
        )
    assert manager.ledger.state["documents"] == []
    assert manager.ledger.state["charges"] == {}
    assert manager.ledger.state["revision"] == 1


async def test_payment_lost_response_retry_does_not_duplicate_receipt(hass):
    manager, _, document = await prepared_manager(hass)
    payload = {
        "document_id": document["id"],
        "amount": "20.00",
        "paid_on": dt_util.now().date().isoformat(),
        "request_id": "payment-001",
    }
    first = await manager.action("payment", payload, 2)
    second = await manager.action("payment", payload, 2)
    assert first["payment"]["id"] == second["payment"]["id"]
    overview = await manager.action("overview", {}, None)
    assert len(overview["payments"]) == 1
    assert overview["balance"]["remaining"] == "40.00"
    with pytest.raises(BillingError, match="request_conflict"):
        await manager.action("payment", payload | {"amount": "30.00"}, 2)


async def test_smtp_handoff_is_not_payment_and_retry_never_auto_resends(hass):
    manager, _, document = await prepared_manager(hass)
    smtp_entry = MockConfigEntry(domain="smtp", data={})
    smtp_entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "notify",
        "smtp",
        "example-recipient",
        config_entry=smtp_entry,
        suggested_object_id="example",
    )
    calls = []

    async def send(call):
        calls.append(call)

    hass.services.async_register("smtp", "send_message", send)
    payload = {"document_id": document["id"], "request_id": "send-0001"}
    result = await manager.action("send", payload, 2)
    await manager.action("send", payload, 2)
    assert len(calls) == 1
    assert "html" in calls[0].data and "attachments" not in calls[0].data
    assert result["deliveries"][-1]["status"] == "handed_to_smtp"
    assert result["balance"]["remaining"] == "60.00"
    assert manager.ledger.state["payments"] == []


async def test_removed_or_changed_profile_cannot_redirect_old_document(hass):
    manager, entry, document = await prepared_manager(hass)
    profiles = [
        dict(entry.options["report_profiles"][0]) | {"targets": ["notify.someone_else"]}
    ]
    hass.config_entries.async_update_entry(
        entry, options=dict(entry.options) | {"report_profiles": profiles}
    )
    with pytest.raises(BillingError, match="profile_changed"):
        await manager.action(
            "send", {"document_id": document["id"], "request_id": "send-0001"}, 2
        )
    hass.config_entries.async_update_entry(
        entry, options=dict(entry.options) | {"report_profiles": []}
    )
    assert (await manager.action("document", {"document_id": document["id"]}, None))[
        "total"
    ] == "60.00"
    with pytest.raises(BillingError, match="profile_required"):
        await manager.action(
            "send", {"document_id": document["id"], "request_id": "send-0002"}, 2
        )


async def test_corrupt_storage_is_not_reset(hass):
    entry = sample_entry(hass)
    manager = BillingManager(hass, entry)
    with (
        patch.object(
            manager.store,
            "async_load",
            new=AsyncMock(return_value={"unexpected": "private-value"}),
        ),
        patch.object(manager.store, "async_save", new=AsyncMock()) as save,
    ):
        with pytest.raises(BillingError, match="storage_invalid"):
            await manager.action("overview", {}, None)
        save.assert_not_called()


async def test_hidden_admin_panel_and_options_link_preserve_existing_settings(
    hass, hass_ws_client
):
    from custom_components.edc_sharing.config_flow import EdcSharingOptionsFlow

    assert await async_setup_component(hass, "frontend", {})
    entry = sample_entry(hass)
    before = dict(entry.options)
    await async_setup_billing(hass)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "get_panels"})
    panel = (await client.receive_json())["result"][PANEL_PATH]
    assert panel["require_admin"] is True and panel["title"] is None
    flow = EdcSharingOptionsFlow(entry)
    flow.hass = hass
    result = await flow.async_step_billing()
    assert entry.entry_id in result["description_placeholders"]["url"]
    assert (await flow.async_step_billing({}))["step_id"] == "init"
    assert entry.options == before


async def test_occupied_billing_panel_and_setup_failure_do_not_affect_edc(
    hass, hass_ws_client
):
    from custom_components.edc_sharing import async_setup

    assert await async_setup_component(hass, "frontend", {})
    frontend.async_register_built_in_panel(
        hass,
        component_name="map",
        frontend_url_path=PANEL_PATH,
        sidebar_title="Keep this panel",
    )
    await async_setup_billing(hass)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "get_panels"})
    panel = (await client.receive_json())["result"][PANEL_PATH]
    assert panel["component_name"] == "map"
    with (
        patch(
            "custom_components.edc_sharing.billing_api.async_setup_billing",
            new=AsyncMock(side_effect=ValueError("private-error")),
        ),
        patch(
            "custom_components.edc_sharing.dashboard_api.async_setup_dashboard_generator",
            new=AsyncMock(),
        ),
    ):
        assert await async_setup(hass, {})
