"""Sdílitelný export pouze předem povolených provozních údajů bez identit."""

from __future__ import annotations

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass, entry) -> dict:
    """Neexportovat config/options, EANy, zprávy, účty, tokeny ani uložené doklady.

    Export je whitelist, proto nové interní atributy nejsou automaticky veřejné.
    Soukromý čtecí příkaz pro správce vrací více detailů než tento export.
    """
    runtime = getattr(entry, "runtime_data", None)
    startup = (
        hass.data.get(DOMAIN, {}).get("startup_diagnostics", {}).get(entry.entry_id, {})
    )
    coordinator = (
        runtime.coordinator if runtime is not None else startup.get("coordinator")
    )
    api = runtime.api if runtime is not None else startup.get("api")
    if coordinator is None or api is None:
        return {"ready": False, "startup_stage": "loading_local_policy"}
    quality = coordinator.data_quality
    state = getattr(api, "account_state", None)
    # Znovu whitelist i interní záznam: budoucí přidaný atribut se nesmí stát
    # automaticky součástí veřejného exportu. Text byl už dříve mapován na kód.
    failure = state.diagnostic_failure() if state is not None else None
    return {
        "ready": runtime is not None,
        "cached_startup": getattr(coordinator, "cached_startup", False),
        "history_available": bool(getattr(coordinator, "has_available_history", False)),
        # Pouze stav a místní kalendářní rozsahy s pevnými důvody. Mezery
        # nejsou důkaz nulových kWh ani počátku platnosti sdílecí skupiny.
        "history_backfill": {
            "status": getattr(coordinator, "history_backfill_status", "not_started"),
            "pending_ranges": getattr(coordinator, "history_backfill_pending_ranges", []),
        },
        "profile_revision": getattr(coordinator, "profile_revision_diagnostics", {}),
        "original_failure": failure,
        "wait_persistence_failed": state.persistence_failed
        if state is not None
        else None,
        "result": coordinator.last_attempt_result,
        "http_status": api.last_status,
        "failure_category": api.last_failure_category,
        "last_success": coordinator.last_success_at.isoformat()
        if coordinator.last_success_at
        else None,
        "next_attempt": coordinator.next_attempt_at.isoformat()
        if coordinator.next_attempt_at
        else None,
        "data_quality": {
            key: quality.get(key)
            for key in (
                "requested_selection",
                "actual_calculation_type",
                "profile_as_of",
                "profile_date_from",
                "profile_date_to_exclusive",
                "quality_basis",
                "quality_counts",
                "quality_cells",
                "provisional_quality_percent",
                "resolution",
                "incomplete_days",
                "incomplete_hours",
                "incomplete_blocks",
                "queued_hours",
                "queued_target_hours",
                "latest_data_day",
                "hourly_reason",
                "cached_only",
                "missing_measurement_days",
                "missing_measurement_intervals",
            )
        },
    }
