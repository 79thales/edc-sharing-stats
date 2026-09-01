"""Config flow for EDC sharing."""

from __future__ import annotations

from decimal import Decimal
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EdcApiClient, EdcApiError, EdcAuthenticationError
from .const import (
    CONF_SALE_PRICE,
    CONF_SSE_ID,
    CONF_SSE_NAME,
    DEFAULT_SALE_PRICE,
    DOMAIN,
)


class EdcSharingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure an EDC account and sharing group."""

    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._groups: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api = EdcApiClient(
                async_get_clientsession(self.hass),
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await api.async_login()
                groups = await api.async_get_groups()
            except EdcAuthenticationError:
                errors["base"] = "invalid_auth"
            except EdcApiError:
                errors["base"] = "cannot_connect"
            else:
                self._groups = {
                    str(item["sseId"]): str(item.get("name") or item["sseId"])
                    for item in groups
                    if item.get("sseId") is not None
                }
                if not self._groups:
                    errors["base"] = "no_groups"
                else:
                    self._credentials = dict(user_input)
                    await self.async_set_unique_id(user_input[CONF_USERNAME].strip().lower())
                    self._abort_if_unique_id_configured()
                    return await self.async_step_group()

        schema = vol.Schema({
            vol.Required(CONF_USERNAME): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
            ),
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_SALE_PRICE, default=DEFAULT_SALE_PRICE): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100, step=0.01, mode=selector.NumberSelectorMode.BOX)
            ),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_group(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            sse_id = str(user_input[CONF_SSE_ID])
            data = self._credentials | {
                CONF_SSE_ID: sse_id,
                CONF_SSE_NAME: self._groups[sse_id],
            }
            return self.async_create_entry(title=self._groups[sse_id], data=data)
        return self.async_show_form(
            step_id="group",
            data_schema=vol.Schema({
                vol.Required(CONF_SSE_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=key, label=value) for key, value in self._groups.items()],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after EDC rejects the saved credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and save a replacement password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api = EdcApiClient(
                async_get_clientsession(self.hass),
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await api.async_login()
            except EdcAuthenticationError:
                errors["base"] = "invalid_auth"
            except EdcApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=entry.data | {CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                )
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EdcSharingOptionsFlow(config_entry)


class EdcSharingOptionsFlow(OptionsFlow):
    """Change group and sale price from integration administration."""

    def __init__(self, config_entry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        api = EdcApiClient(
            async_get_clientsession(self.hass),
            self._entry.data[CONF_USERNAME],
            self._entry.data[CONF_PASSWORD],
        )
        try:
            groups = await api.async_get_groups()
            choices = {str(item["sseId"]): str(item.get("name") or item["sseId"]) for item in groups}
        except EdcAuthenticationError:
            return self.async_abort(reason="invalid_auth")
        except EdcApiError:
            return self.async_abort(reason="cannot_connect")

        if user_input is not None:
            sse_id = str(user_input[CONF_SSE_ID])
            new_data = self._entry.data | {CONF_SSE_ID: sse_id, CONF_SSE_NAME: choices[sse_id]}
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)
            return self.async_create_entry(data={CONF_SALE_PRICE: user_input[CONF_SALE_PRICE]})

        current_price = self._entry.options.get(
            CONF_SALE_PRICE, self._entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_SSE_ID, default=str(self._entry.data[CONF_SSE_ID])): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=key, label=value) for key, value in choices.items()]
                    )
                ),
                vol.Required(CONF_SALE_PRICE, default=float(Decimal(str(current_price)))): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=100, step=0.01, mode=selector.NumberSelectorMode.BOX)
                ),
            }),
            errors=errors,
        )
