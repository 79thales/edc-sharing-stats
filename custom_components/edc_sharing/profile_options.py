"""UI for creating, editing, previewing and sending report profiles."""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .report_profiles import (
    CONF_REPORT_PROFILES,
    PERIODS,
    configured_profiles,
    default_profile,
    validate_profile,
)


def _select(options: tuple | list, *, multiple: bool = False):
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(options),
            multiple=multiple,
            translation_key="report_profile",
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def profile_schema(profile: dict) -> vol.Schema:
    """Use native selectors; never ask for SMTP passwords here."""
    fields = {
        "name": selector.TextSelector(),
        "enabled": selector.BooleanSelector(),
        "targets": selector.EntitySelector(
            selector.EntitySelectorConfig(domain="notify", multiple=True)
        ),
        "language": _select(("cs", "en")),
        "periods": _select(PERIODS, multiple=True),
        "combined": selector.BooleanSelector(),
        "period_mode": _select(("current", "previous", "legacy")),
        "frequency": _select(("daily", "weekly", "monthly", "yearly")),
        "time": selector.TimeSelector(),
        "weekdays": _select(tuple(str(i) for i in range(7)), multiple=True),
        "day": selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=28, step=1, mode=selector.NumberSelectorMode.BOX
            )
        ),
        "month": selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=12, step=1, mode=selector.NumberSelectorMode.BOX
            )
        ),
        "only_new": selector.BooleanSelector(),
        "energy": selector.BooleanSelector(),
        "finance": selector.BooleanSelector(),
        "ean_mode": _select(("hidden", "masked", "full")),
    }
    return vol.Schema(
        {
            vol.Required(key, default=profile[key]): value
            for key, value in fields.items()
        }
    )


class ProfileOptionsMixin:
    """Multi-step profile management in the existing integration options flow."""

    def _profiles(self) -> list[dict]:
        return deepcopy(
            configured_profiles(
                self._entry.options,
                "cs" if (self.hass.config.language or "en").startswith("cs") else "en",
            )
        )

    def _save_profile(self, profile: dict, *, delete: bool = False):
        profiles = [p for p in self._profiles() if p["id"] != profile["id"]]
        if not delete:
            profiles.append(profile)
        return self.async_create_entry(
            data=dict(self._entry.options) | {CONF_REPORT_PROFILES: profiles}
        )

    async def async_step_profiles(self, user_input=None):
        if user_input is not None:
            selected = user_input["profile"]
            if selected == "new":
                self._selected_profile = default_profile(uuid4().hex)
                self._selected_profile["language"] = (
                    "cs"
                    if (self.hass.config.language or "en").startswith("cs")
                    else "en"
                )
                return await self.async_step_profile_edit()
            self._selected_profile = next(
                p for p in self._profiles() if p["id"] == selected
            )
            return await self.async_step_profile_manage()
        choices = [selector.SelectOptionDict(value="new", label="＋")]
        choices += [
            selector.SelectOptionDict(value=p["id"], label=p["name"])
            for p in self._profiles()
        ]
        return self.async_show_form(
            step_id="profiles",
            data_schema=vol.Schema(
                {
                    vol.Required("profile"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=choices, mode=selector.SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
        )

    async def async_step_profile_edit(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                profile = validate_profile(self._selected_profile | user_input)
            except (ValueError, TypeError):
                errors["base"] = "invalid_profile"
                self._selected_profile.update(user_input)
            else:
                return self._save_profile(profile)
        return self.async_show_form(
            step_id="profile_edit",
            data_schema=profile_schema(self._selected_profile),
            errors=errors,
        )

    async def async_step_profile_manage(self, user_input=None):
        return self.async_show_menu(
            step_id="profile_manage",
            menu_options=[
                "profile_edit",
                "profile_toggle",
                "profile_duplicate",
                "profile_preview",
                "profile_send",
                "profile_delete",
                "profile_status",
            ],
        )

    async def async_step_profile_toggle(self, user_input=None):
        profile = self._selected_profile | {
            "enabled": not self._selected_profile["enabled"]
        }
        return self._save_profile(profile)

    async def async_step_profile_duplicate(self, user_input=None):
        self._selected_profile = self._selected_profile | {
            "id": uuid4().hex,
            "name": self._selected_profile["name"][:70] + " (copy)",
            "enabled": False,
        }
        return await self.async_step_profile_edit()

    async def async_step_profile_delete(self, user_input=None):
        if user_input is not None:
            if user_input["confirm"]:
                return self._save_profile(self._selected_profile, delete=True)
            return await self.async_step_profile_manage()
        return self.async_show_form(
            step_id="profile_delete",
            data_schema=vol.Schema(
                {vol.Required("confirm", default=False): selector.BooleanSelector()}
            ),
            description_placeholders={"name": self._selected_profile["name"]},
        )

    async def async_step_profile_preview(self, user_input=None):
        if user_input is not None:
            return await self.async_step_profile_manage()
        try:
            messages = await self._entry.runtime_data.reporter.profiles.preview(
                self._selected_profile
            )
            preview = "\n\n---\n\n".join(message for _, message in messages)
        except (HomeAssistantError, ValueError, KeyError, TypeError, OSError):
            return self.async_show_form(
                step_id="profile_preview",
                data_schema=vol.Schema({}),
                errors={"base": "report_failed"},
                description_placeholders={"preview": "–"},
            )
        return self.async_show_form(
            step_id="profile_preview",
            data_schema=vol.Schema({}),
            description_placeholders={"preview": preview},
        )

    async def async_step_profile_send(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self._entry.runtime_data.reporter.profiles.async_send(
                    self._selected_profile
                )
            except HomeAssistantError:
                errors["base"] = "report_failed"
            else:
                return await self.async_step_profile_status()
        return self.async_show_form(
            step_id="profile_send",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"name": self._selected_profile["name"]},
        )

    async def async_step_profile_status(self, user_input=None):
        if user_input is not None:
            return await self.async_step_profile_manage()
        state = self._entry.runtime_data.reporter.profiles.status(
            self._selected_profile
        )
        czech = (self.hass.config.language or "en").startswith("cs")
        labels = {
            "not_sent": ("Zatím neodesláno", "Not sent yet"),
            "sending": ("Odesílání probíhá", "Sending"),
            "interrupted": (
                "Přerušeno restartem nebo změnou nastavení",
                "Interrupted by restart or settings reload",
            ),
            "sent": ("Předáno příjemcům", "Handed off to recipients"),
            "failed": ("Selhalo", "Failed"),
            "partial_failure": (
                "Některým příjemcům se odeslání nezdařilo",
                "Some recipients failed",
            ),
            "no_new_data": (
                "Přeskočeno: nezměněná data nebo již odesláno",
                "Skipped: unchanged data or already sent",
            ),
        }
        state["result"] = labels.get(
            state["result"], (state["result"], state["result"])
        )[0 if czech else 1]
        return self.async_show_form(
            step_id="profile_status",
            data_schema=vol.Schema({}),
            description_placeholders={key: str(value) for key, value in state.items()},
        )
