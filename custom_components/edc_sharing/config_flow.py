"""Config flow for EDC sharing."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import EdcApiClient, EdcApiError, EdcAuthenticationError
from .profile_options import ProfileOptionsMixin
from .report_profiles import CONF_REPORT_PROFILES
from .const import (
    CONF_EAN_SETTINGS,
    CONF_SALE_PRICE,
    CONF_DAILY_REPORT,
    CONF_WEEKLY_REPORT,
    CONF_MONTHLY_REPORT,
    CONF_REPORT_DAY,
    CONF_REPORT_LANGUAGE,
    CONF_REPORT_TARGETS,
    CONF_REPORT_TIME,
    CONF_SSE_ID,
    CONF_SSE_NAME,
    CONF_SUMMARY_REPORT,
    CONF_YEARLY_REPORT,
    DEFAULT_REPORT_DAY,
    DEFAULT_REPORT_TIME,
    DEFAULT_SALE_PRICE,
    DOMAIN,
    config_entry_unique_id,
)
from .ean_settings import configured_ean_settings, ean_location, ean_name


class EdcSharingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure an EDC account and sharing group."""

    VERSION = 2

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._groups: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
                ),
                vol.Required(CONF_PASSWORD): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_SALE_PRICE, default=DEFAULT_SALE_PRICE
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=100, step=0.01, mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_group(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
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
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SSE_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value=key, label=value)
                                for key, value in self._groups.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
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
                    data_updates=entry.data
                    | {CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    )
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EdcSharingOptionsFlow(config_entry)


class EdcSharingOptionsFlow(ProfileOptionsMixin, OptionsFlow):
    """Change group and sale price from integration administration."""

    def __init__(self, config_entry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["general", "ean_settings", "profiles"]
        )

    def _known_eans(self) -> tuple:
        """Use EANs discovered by the current coordinator refresh only."""
        runtime = getattr(self._entry, "runtime_data", None)
        coordinator = getattr(runtime, "coordinator", None)
        return tuple(getattr(coordinator, "eans", ()))

    async def async_step_ean_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose an EAN whose local name, location or price should be edited."""
        eans = self._known_eans()
        if not eans:
            return self.async_show_form(
                step_id="ean_settings",
                data_schema=vol.Schema({}),
                errors={"base": "no_eans"},
            )

        errors: dict[str, str] = {}
        if user_input is not None:
            selected = str(user_input.get("ean") or "")
            self._selected_ean = next(
                (item for item in eans if item.ean == selected), None
            )
            if self._selected_ean is not None:
                return await self.async_step_ean_edit()
            errors["ean"] = "invalid_ean_settings"

        czech = (self.hass.config.language or "en").casefold().startswith("cs")
        choices = []
        for item in eans:
            role = (
                "Sdílející EAN" if item.role == "sharing" else "Cílový EAN"
            ) if czech else ("Sharing EAN" if item.role == "sharing" else "Target EAN")
            label = ean_name(item.ean, self._entry.options)
            if label != item.ean:
                label = f"{role}: {label} ({item.ean})"
            else:
                label = f"{role}: {item.ean}"
            if location := ean_location(item.ean, self._entry.options):
                label = f"{label} — {location}"
            choices.append(selector.SelectOptionDict(value=item.ean, label=label))
        return self.async_show_form(
            step_id="ean_settings",
            data_schema=vol.Schema(
                {
                    vol.Required("ean"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=choices,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_ean_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Save optional local metadata for a discovered sharing-group EAN."""
        selected = getattr(self, "_selected_ean", None)
        if selected is None:
            return await self.async_step_ean_settings()

        current = configured_ean_settings(self._entry.options).get(
            selected.ean, {}
        )
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input.get("name") or "").strip()
            location = str(user_input.get("location") or "").strip()
            if len(name) > 120 or len(location) > 120:
                errors["base"] = "invalid_ean_settings"

            price: Decimal | None = None
            if selected.role == "target" and not user_input.get(
                "use_group_price", True
            ):
                try:
                    price = Decimal(str(user_input.get("price")))
                except (InvalidOperation, TypeError, ValueError):
                    errors["price"] = "invalid_ean_settings"
                else:
                    if not price.is_finite() or price < 0:
                        errors["price"] = "invalid_ean_settings"

            if not errors:
                raw_settings = self._entry.options.get(CONF_EAN_SETTINGS, {})
                settings = {
                    str(ean): dict(value)
                    for ean, value in raw_settings.items()
                    if isinstance(ean, str) and isinstance(value, Mapping)
                } if isinstance(raw_settings, Mapping) else {}
                item: dict[str, Any] = {}
                if name:
                    item["name"] = name
                if location:
                    item["location"] = location
                if selected.role == "target" and price is not None:
                    item["price"] = str(price)
                if item:
                    settings[selected.ean] = item
                else:
                    settings.pop(selected.ean, None)
                return self.async_create_entry(
                    data=dict(self._entry.options) | {CONF_EAN_SETTINGS: settings}
                )

        use_group_price = "price" not in current
        schema: dict[Any, Any] = {
            vol.Optional("name", default=str(current.get("name") or "")):
                selector.TextSelector(),
            vol.Optional("location", default=str(current.get("location") or "")):
                selector.TextSelector(),
        }
        if selected.role == "target":
            schema[vol.Required("use_group_price", default=use_group_price)] = (
                selector.BooleanSelector()
            )
            price_schema = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step=0.01, mode=selector.NumberSelectorMode.BOX
                )
            )
            if not use_group_price:
                schema[vol.Optional("price", default=float(current["price"]))] = (
                    price_schema
                )
            else:
                schema[vol.Optional("price")] = price_schema
        return self.async_show_form(
            step_id="ean_edit",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "ean": selected.ean,
                "role": (
                    (
                        "sdílející"
                        if selected.role == "sharing"
                        else "cílový"
                    )
                    if (self.hass.config.language or "en").casefold().startswith("cs")
                    else ("sharing" if selected.role == "sharing" else "target")
                ),
            },
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        api = EdcApiClient(
            async_get_clientsession(self.hass),
            self._entry.data[CONF_USERNAME],
            self._entry.data[CONF_PASSWORD],
        )
        try:
            groups = await api.async_get_groups()
            choices = {
                str(item["sseId"]): str(item.get("name") or item["sseId"])
                for item in groups
            }
        except EdcAuthenticationError:
            return self.async_abort(reason="invalid_auth")
        except EdcApiError:
            return self.async_abort(reason="cannot_connect")

        if user_input is not None:
            user_input = {
                CONF_DAILY_REPORT: self._entry.options.get(CONF_DAILY_REPORT, False),
                CONF_WEEKLY_REPORT: self._entry.options.get(CONF_WEEKLY_REPORT, False),
                CONF_MONTHLY_REPORT: self._entry.options.get(
                    CONF_MONTHLY_REPORT, False
                ),
                CONF_YEARLY_REPORT: self._entry.options.get(CONF_YEARLY_REPORT, False),
                CONF_SUMMARY_REPORT: self._entry.options.get(
                    CONF_SUMMARY_REPORT, False
                ),
                CONF_REPORT_TIME: self._entry.options.get(
                    CONF_REPORT_TIME, DEFAULT_REPORT_TIME
                ),
                CONF_REPORT_DAY: self._entry.options.get(
                    CONF_REPORT_DAY, DEFAULT_REPORT_DAY
                ),
            } | user_input
            sse_id = str(user_input[CONF_SSE_ID])
            unique_id = config_entry_unique_id(self._entry.data[CONF_USERNAME], sse_id)
            duplicate = any(
                entry.entry_id != self._entry.entry_id and entry.unique_id == unique_id
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
                    data=dict(self._entry.options)
                    | {
                        CONF_SALE_PRICE: user_input[CONF_SALE_PRICE],
                        CONF_REPORT_TARGETS: user_input.get(CONF_REPORT_TARGETS, []),
                        CONF_DAILY_REPORT: user_input[CONF_DAILY_REPORT],
                        CONF_WEEKLY_REPORT: user_input[CONF_WEEKLY_REPORT],
                        CONF_MONTHLY_REPORT: user_input[CONF_MONTHLY_REPORT],
                        CONF_YEARLY_REPORT: user_input[CONF_YEARLY_REPORT],
                        CONF_SUMMARY_REPORT: user_input[CONF_SUMMARY_REPORT],
                        CONF_REPORT_TIME: user_input[CONF_REPORT_TIME],
                        CONF_REPORT_DAY: int(user_input[CONF_REPORT_DAY]),
                        CONF_REPORT_LANGUAGE: user_input[CONF_REPORT_LANGUAGE],
                    }
                )

        current_price = self._entry.options.get(
            CONF_SALE_PRICE, self._entry.data.get(CONF_SALE_PRICE, DEFAULT_SALE_PRICE)
        )
        current_targets = self._entry.options.get(CONF_REPORT_TARGETS, [])
        current_language = self._entry.options.get(
            CONF_REPORT_LANGUAGE,
            "cs"
            if (self.hass.config.language or "en").casefold().startswith("cs")
            else "en",
        )
        schema = {
            vol.Required(
                CONF_SSE_ID, default=str(self._entry.data[CONF_SSE_ID])
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=key, label=value)
                        for key, value in choices.items()
                    ]
                )
            ),
            vol.Required(
                CONF_SALE_PRICE, default=float(Decimal(str(current_price)))
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step=0.01, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_REPORT_TARGETS, default=current_targets
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="notify", multiple=True)
            ),
            vol.Required(
                CONF_REPORT_LANGUAGE, default=current_language
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value="cs", label="Čeština"),
                        selector.SelectOptionDict(value="en", label="English"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
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
                CONF_SUMMARY_REPORT,
                default=bool(self._entry.options.get(CONF_SUMMARY_REPORT, False)),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_REPORT_TIME,
                default=str(
                    self._entry.options.get(CONF_REPORT_TIME, DEFAULT_REPORT_TIME)
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
        }
        if CONF_REPORT_PROFILES in self._entry.options:
            schema = {
                key: value
                for key, value in schema.items()
                if str(key)
                in (
                    CONF_SSE_ID,
                    CONF_SALE_PRICE,
                    CONF_REPORT_TARGETS,
                    CONF_REPORT_LANGUAGE,
                )
            }
        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
