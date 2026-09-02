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
    CONF_DAILY_REPORT,
    CONF_WEEKLY_REPORT,
    CONF_MONTHLY_REPORT,
    CONF_REPORT_DAY,
    CONF_REPORT_TARGETS,
    CONF_REPORT_TIME,
    CONF_SSE_ID,
    CONF_SSE_NAME,
    CONF_YEARLY_REPORT,
    DEFAULT_REPORT_DAY,
    DEFAULT_REPORT_TIME,
    DEFAULT_SALE_PRICE,
    DOMAIN,
    config_entry_unique_id,
)


class EdcSharingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure an EDC account and sharing group."""

    VERSION = 2

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
            await self.async_set_unique_id(
                config_entry_unique_id(self._credentials[CONF_USERNAME], sse_id)
            )
            self._abort_if_unique_id_configured()
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
            unique_id = config_entry_unique_id(
                self._entry.data[CONF_USERNAME], sse_id
            )
            duplicate = any(
                entry.entry_id != self._entry.entry_id
                and entry.unique_id == unique_id
                for entry in self.hass.config_entries.async_entries(DOMAIN)
            )
            if duplicate:
                errors[CONF_SSE_ID] = "already_configured"
            else:
                new_data = self._entry.data | {
                    CONF_SSE_ID: sse_id,
                    CONF_SSE_NAME: choices[sse_id],
                }
                self.hass.config_entries.async_update_entry(
                    self._entry, data=new_data, unique_id=unique_id
                )
                return self.async_create_entry(
                    data={
                        CONF_SALE_PRICE: user_input[CONF_SALE_PRICE],
                        CONF_REPORT_TARGETS: user_input.get(
                            CONF_REPORT_TARGETS, []
                        ),
                        CONF_DAILY_REPORT: user_input[CONF_DAILY_REPORT],
                        CONF_WEEKLY_REPORT: user_input[CONF_WEEKLY_REPORT],
                        CONF_MONTHLY_REPORT: user_input[CONF_MONTHLY_REPORT],
                        CONF_YEARLY_REPORT: user_input[CONF_YEARLY_REPORT],
                        CONF_REPORT_TIME: user_input[CONF_REPORT_TIME],
                        CONF_REPORT_DAY: int(user_input[CONF_REPORT_DAY]),
                    }
                )

        current_price = self._entry.options.get(
            CONF_SALE_PRICE, self._entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE)
        )
        current_targets = self._entry.options.get(CONF_REPORT_TARGETS, [])
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
                vol.Optional(
                    CONF_REPORT_TARGETS, default=current_targets
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="notify", multiple=True)
                ),
                vol.Required(
                    CONF_DAILY_REPORT,
                    default=bool(self._entry.options.get(CONF_DAILY_REPORT, False)),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_WEEKLY_REPORT,
                    default=bool(self._entry.options.get(CONF_WEEKLY_REPORT, False)),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_MONTHLY_REPORT,
                    default=bool(self._entry.options.get(CONF_MONTHLY_REPORT, False)),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_YEARLY_REPORT,
                    default=bool(self._entry.options.get(CONF_YEARLY_REPORT, False)),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_REPORT_TIME,
                    default=str(
                        self._entry.options.get(
                            CONF_REPORT_TIME, DEFAULT_REPORT_TIME
                        )
                    ),
                ): selector.TimeSelector(),
                vol.Required(
                    CONF_REPORT_DAY,
                    default=int(
                        self._entry.options.get(CONF_REPORT_DAY, DEFAULT_REPORT_DAY)
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=28,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }),
            errors=errors,
        )
