"""UI for creating, editing, previewing and sending report profiles."""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .profile_overview import delivery_label, format_overview
from .ean_settings import ean_location, ean_name

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


def profile_schema(
    profile: dict, *, target_ean_options: tuple[dict, ...] = ()
) -> vol.Schema:
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
        "report_scope": _select(("group", "target")),
        "target_eans": selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(target_ean_options),
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
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

    def _target_ean_options(self) -> tuple[dict, ...]:
        """Build stable, human-readable target-EAN choices for a profile."""
        runtime = getattr(self._entry, "runtime_data", None)
        coordinator = getattr(runtime, "coordinator", None)
        current = {
            item.ean
            for item in getattr(coordinator, "eans", ())
            if item.role == "target"
        }
        selected = set(getattr(self, "_selected_profile", {}).get("target_eans", []))
        czech = (self.hass.config.language or "en").startswith("cs")
        choices: list[dict] = []
        for ean in sorted(current | selected):
            label = ean_name(ean, self._entry.options)
            if label != ean:
                label = f"{label} ({ean})"
            if location := ean_location(ean, self._entry.options):
                label = f"{label} — {location}"
            if ean not in current:
                label += " — nedostupné" if czech else " — unavailable"
            choices.append(selector.SelectOptionDict(value=ean, label=label))
        return tuple(choices)

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
        czech = (self.hass.config.language or "en").startswith("cs")
        profiles = self._profiles()
        recipients = {}
        for profile in profiles:
            for target in profile["targets"]:
                state = self.hass.states.get(target)
                if state is not None:
                    name = state.name
                    # Notify entities with no previous handoff can be unknown
                    # while still available for sending.
                    if state.state == "unavailable":
                        name += " — nedostupné" if czech else " — unavailable"
                    recipients[target] = name
        runtime = getattr(self._entry, "runtime_data", None)
        reporter = getattr(runtime, "reporter", None)
        manager = getattr(reporter, "profiles", None)
        statuses = {p["id"]: manager.status(p) for p in profiles} if manager else {}
        overview = format_overview(
            profiles,
            recipients,
            statuses,
            czech=czech,
            local_tz=dt_util.now().tzinfo,
        )
        choices = [
            selector.SelectOptionDict(
                value="new", label="＋ Přidat profil" if czech else "＋ Add profile"
            )
        ]
        choices += [
            selector.SelectOptionDict(
                value=p["id"],
                label=p["name"]
                + " — "
                + (
                    ("Zapnuto" if czech else "Enabled")
                    if p["enabled"]
                    else ("Pozastaveno" if czech else "Paused")
                ),
            )
            for p in profiles
        ]
        return self.async_show_form(
            step_id="profiles",
            description_placeholders={"overview": overview},
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
            data_schema=profile_schema(
                self._selected_profile,
                target_ean_options=self._target_ean_options(),
            ),
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
                "profiles",
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
        state["result"] = delivery_label(state["result"], czech)
        return self.async_show_form(
            step_id="profile_status",
            data_schema=vol.Schema({}),
            description_placeholders={key: str(value) for key, value in state.items()},
        )
