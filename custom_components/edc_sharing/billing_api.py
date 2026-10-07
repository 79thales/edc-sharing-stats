"""Authenticated admin panel, versioned local ledger and explicit SMTP handoff."""

from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .billing import (
    PANEL_PATH,
    BillingError,
    BillingLedger,
    fingerprint,
    profile_routing,
)
from .billing_document import render_settlement, settlement_payment_payload
from .const import CONF_SSE_ID, CONF_SSE_NAME, DOMAIN
from .payment import payment_qr_data_uri
from .report_profiles import CONF_REPORT_PROFILES, configured_profiles

STORAGE_VERSION = 1
MODULE_PATH = "/edc_sharing/billing.js"
_LOGGER = logging.getLogger(__name__)
_MUTATIONS = {"settings", "issue", "payment", "void_payment", "send"}


def explicit_profiles(entry: ConfigEntry) -> list[dict]:
    """Do not silently create profiles from the old report-button defaults."""
    if CONF_REPORT_PROFILES not in entry.options:
        return []
    return [p for p in configured_profiles(dict(entry.options)) if p.get("id")]


async def async_setup_billing(hass: HomeAssistant) -> None:
    from homeassistant.components.frontend import async_panel_exists
    from homeassistant.components.http import StaticPathConfig
    from homeassistant.components.panel_custom import async_register_panel

    websocket_api.async_register_command(hass, websocket_billing)
    websocket_api.async_register_command(hass, websocket_billing_groups)
    if async_panel_exists(hass, PANEL_PATH):
        _LOGGER.warning(
            "The EDC billing URL is occupied; the existing panel is unchanged"
        )
        return
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                MODULE_PATH, str(Path(__file__).parent / "frontend/billing.js"), False
            )
        ]
    )
    await async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name="edc-sharing-billing-v1",
        module_url=f"{MODULE_PATH}?v={integration.manifest['version']}",
        require_admin=True,
        config_panel_domain=DOMAIN,
    )


class BillingManager:
    """Lazy ledger: failure does not stop existing EDC setup or report timers."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass, self.entry = hass, entry
        self.lock = asyncio.Lock()
        self.ledger: BillingLedger | None = None
        # Keep financial data isolated from history, reporting state and groups.
        self.store: Store[dict[str, Any]] = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.billing.{entry.entry_id}.{entry.data[CONF_SSE_ID]}",
            private=True,
        )

    async def _load(self) -> BillingLedger:
        if self.ledger is None:
            self.ledger = BillingLedger(await self.store.async_load())
        return self.ledger

    async def _save(self, candidate: BillingLedger) -> None:
        """Commit in memory only after HA's atomic Store save succeeds."""
        validated = BillingLedger(candidate.state)
        await self.store.async_save(validated.state)
        self.ledger = validated

    def _profile(self, profile_id: str) -> dict:
        try:
            return next(
                p for p in explicit_profiles(self.entry) if p["id"] == profile_id
            )
        except StopIteration as err:
            raise BillingError("profile_required") from err

    def _smtp_ready(self, profile: dict) -> bool:
        registry = er.async_get(self.hass)
        return (
            bool(profile["targets"])
            and self.hass.services.has_service("smtp", "send_message")
            and all(
                (item := registry.async_get(target)) is not None
                and item.platform == "smtp"
                and item.disabled_by is None
                for target in profile["targets"]
            )
        )

    def _preview(self, ledger: BillingLedger, payload: dict) -> dict:
        try:
            profile = self._profile(payload["profile_id"])
            start, end, due = (
                date.fromisoformat(payload[key]) for key in ("start", "end", "due")
            )
            runtime = getattr(self.entry, "runtime_data", None)
            coordinator = getattr(runtime, "coordinator", None)
            rows = (
                coordinator.target_days_for_range(start, end + timedelta(days=1))
                if coordinator
                else {}
            )
            data = getattr(coordinator, "data", None)
            quote = ledger.preview(
                profile=profile,
                rows=rows,
                group_days={row.day: row for row in getattr(data, "days", ())},
                options=self.entry.options,
                group_name=str(self.entry.data.get(CONF_SSE_NAME) or self.entry.title),
                start=start,
                end=end,
                today=dt_util.now().date(),
                issuer=ledger.state["settings"]["issuer"],
                issuer_address=ledger.state["settings"]["issuer_address"],
                recipient=payload["recipient"],
                recipient_address=payload.get("recipient_address", ""),
                due=due,
            )
            quote["smtp_ready"] = self._smtp_ready(profile)
            return quote
        except (KeyError, TypeError, ValueError, OverflowError) as err:
            if isinstance(err, BillingError):
                raise
            raise BillingError("invalid_request") from err

    async def _document(self, ledger: BillingLedger, document_id: str) -> dict:
        document = ledger.document(document_id)
        payload = settlement_payment_payload(document)
        qr = (
            await self.hass.async_add_executor_job(payment_qr_data_uri, payload)
            if payload
            else None
        )
        html, text = await self.hass.async_add_executor_job(
            render_settlement, document, qr
        )
        return document | {"html": html, "text": text}

    async def action(self, action: str, payload: dict, revision: int | None) -> dict:
        async with self.lock:
            ledger = await self._load()
            now = dt_util.now().isoformat()
            if action == "overview":
                runtime = getattr(self.entry, "runtime_data", None)
                coordinator = getattr(runtime, "coordinator", None)
                data = getattr(coordinator, "data", None)
                documents = []
                for item in reversed(ledger.state["documents"]):
                    document = ledger.document(item["id"])
                    documents.append(
                        {
                            key: value
                            for key, value in document.items()
                            if key
                            not in {"charges", "charge_keys", "account", "routing"}
                        }
                    )
                return {
                    "revision": ledger.state["revision"],
                    "settings": deepcopy(ledger.state["settings"]),
                    "today": dt_util.now().date().isoformat(),
                    "latest_day": str(getattr(data, "latest_day", None) or ""),
                    "profiles": [
                        {
                            "id": p["id"],
                            "name": p["name"],
                            "scope": p["report_scope"],
                            "targets": p["targets"],
                            "finance": p["finance"],
                            "smtp_ready": self._smtp_ready(p),
                        }
                        for p in explicit_profiles(self.entry)
                    ],
                    "documents": documents,
                    "payments": deepcopy(ledger.state["payments"]),
                    "balance": ledger.balance(ledger.state["charges"]),
                }
            if action == "preview":
                return self._preview(ledger, payload)
            if action == "document":
                return await self._document(ledger, payload["document_id"])
            request_id = payload.get("request_id")
            if action in _MUTATIONS and (
                not isinstance(request_id, str) or not 8 <= len(request_id) <= 80
            ):
                raise BillingError("invalid_request")
            # Lost responses must not issue a second document or record payment twice.
            if action == "issue":
                existing = next(
                    (
                        d
                        for d in ledger.state["documents"]
                        if d["request_id"] == request_id
                    ),
                    None,
                )
                if existing:
                    if existing.get("request_digest") != fingerprint(
                        payload["parameters"]
                    ):
                        raise BillingError("request_conflict")
                    return await self._document(ledger, existing["id"])
            if action == "payment":
                existing = next(
                    (
                        p
                        for p in ledger.state["payments"]
                        if p["request_id"] == request_id
                    ),
                    None,
                )
                if existing:
                    if existing.get("request_digest") != fingerprint(
                        {k: v for k, v in payload.items() if k != "request_id"}
                    ):
                        raise BillingError("request_conflict")
                    return {
                        "payment": deepcopy(existing),
                        "revision": ledger.state["revision"],
                    }
            if action == "send":
                existing = next(
                    (
                        d
                        for d in ledger.state["documents"]
                        if d["id"] == payload["document_id"]
                    ),
                    None,
                )
                if existing and any(
                    s["request_id"] == request_id for s in existing["deliveries"]
                ):
                    return await self._document(ledger, existing["id"])
            if action in _MUTATIONS and revision != ledger.state["revision"]:
                raise BillingError("stale_revision")
            candidate = BillingLedger(ledger.state)
            if action == "settings":
                if not explicit_profiles(self.entry):
                    raise BillingError("profile_required")
                candidate.configure(
                    issuer=payload["issuer"],
                    issuer_address=payload.get("issuer_address", ""),
                    tracking=payload["tracking"],
                )
                await self._save(candidate)
            elif action == "issue":
                quote = self._preview(candidate, payload["parameters"])
                if quote["preview_id"] != payload.get("preview_id"):
                    raise BillingError("preview_changed")
                document = candidate.issue(quote, now=now, request_id=request_id)
                persisted = next(
                    d for d in candidate.state["documents"] if d["id"] == document["id"]
                )
                if persisted["request_id"] == request_id:
                    persisted["request_digest"] = fingerprint(payload["parameters"])
                await self._save(candidate)
                return await self._document(candidate, document["id"])
            elif action == "payment":
                start = (
                    date.fromisoformat(payload["start"])
                    if payload.get("start")
                    else None
                )
                end = date.fromisoformat(payload["end"]) if payload.get("end") else None
                receipt = candidate.confirm_payment(
                    payload["document_id"],
                    amount=payload["amount"],
                    paid_on=date.fromisoformat(payload["paid_on"]),
                    now=now,
                    request_id=request_id,
                    start=start,
                    end=end,
                    ean=payload.get("ean") or None,
                )
                stored = next(
                    p for p in candidate.state["payments"] if p["id"] == receipt["id"]
                )
                stored["request_digest"] = fingerprint(
                    {k: v for k, v in payload.items() if k != "request_id"}
                )
                await self._save(candidate)
                return {"payment": receipt, "revision": candidate.state["revision"]}
            elif action == "void_payment":
                candidate.void_payment(
                    payload["payment_id"], now=now, request_id=request_id
                )
                await self._save(candidate)
            elif action == "send":
                return await self._send(
                    candidate, payload["document_id"], request_id, now
                )
            return {"revision": candidate.state["revision"]}

    async def _send(
        self, ledger: BillingLedger, document_id: str, request_id: str, now: str
    ) -> dict:
        document = ledger.document(document_id)
        profile = self._profile(document["profile_id"])
        if profile_routing(profile) != document["routing"]:
            raise BillingError("profile_changed")
        if not self._smtp_ready(profile):
            raise BillingError("smtp_unavailable")
        if document["balance"]["ambiguous"]:
            raise BillingError("ambiguous_payment")
        rendered = await self._document(ledger, document_id)
        persisted = next(d for d in ledger.state["documents"] if d["id"] == document_id)
        attempt = {
            "request_id": request_id,
            "at": now,
            "status": "handoff_in_progress",
            "successful": 0,
            "failed_or_uncertain": 0,
        }
        persisted["deliveries"].append(attempt)
        ledger._changed()
        # Persist intent BEFORE an external side effect; retries never auto-resend.
        await self._save(ledger)
        for target in profile["targets"]:
            try:
                await self.hass.services.async_call(
                    "smtp",
                    "send_message",
                    {
                        "title": (
                            "Vyúčtování sdílení "
                            if document["language"] == "cs"
                            else "Sharing settlement "
                        )
                        + document["number"],
                        "message": rendered["text"],
                        "html": rendered["html"],
                    },
                    target={"entity_id": target},
                    blocking=True,
                )
            except Exception:  # noqa: BLE001 -- arbitrary SMTP errors can contain private addresses/passwords
                attempt["failed_or_uncertain"] += 1
            else:
                attempt["successful"] += 1
        attempt["status"] = (
            "handed_to_smtp"
            if not attempt["failed_or_uncertain"]
            else "partial_or_uncertain"
            if attempt["successful"]
            else "failed_or_uncertain"
        )
        ledger._changed()
        await self._save(ledger)
        return await self._document(ledger, document_id)


@websocket_api.require_admin
@websocket_api.websocket_command({"type": "edc_sharing/billing/groups"})
@websocket_api.async_response
async def websocket_billing_groups(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    connection.send_result(
        msg["id"],
        [
            {
                "entry_id": entry.entry_id,
                "name": str(entry.data.get(CONF_SSE_NAME) or entry.title),
            }
            for entry in hass.config_entries.async_entries(DOMAIN)
        ],
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        "type": "edc_sharing/billing/action",
        vol.Required("entry_id"): str,
        vol.Required("action"): vol.In(
            (
                "overview",
                "preview",
                "document",
                "settings",
                "issue",
                "payment",
                "void_payment",
                "send",
            )
        ),
        vol.Optional("payload", default=dict): dict,
        vol.Optional("revision"): vol.All(int, vol.Range(min=0)),
    }
)
@websocket_api.async_response
async def websocket_billing(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(
            msg["id"], "entry_not_found", "EDC config entry not found"
        )
        return
    managers = hass.data.setdefault("edc_sharing_billing_managers", {})
    key = (entry.entry_id, str(entry.data[CONF_SSE_ID]))
    if key not in managers:
        managers[key] = BillingManager(hass, entry)
    manager = managers[key]
    try:
        result = await manager.action(
            msg["action"], msg["payload"], msg.get("revision")
        )
    except BillingError as err:
        connection.send_error(
            msg["id"], str(err), "Review the billing request or ledger state"
        )
    except (KeyError, ValueError, TypeError, OverflowError):
        connection.send_error(msg["id"], "invalid_request", "Invalid billing request")
    except Exception:  # noqa: BLE001 -- never expose storage/SMTP paths or personal data to logs
        connection.send_error(
            msg["id"],
            "billing_unavailable",
            "Billing could not complete; existing EDC functions are unchanged",
        )
    else:
        connection.send_result(msg["id"], result)
