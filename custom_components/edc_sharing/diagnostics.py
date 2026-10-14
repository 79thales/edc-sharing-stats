"""Sdílitelný export pouze předem povolených provozních údajů bez identit."""

from __future__ import annotations


async def async_get_config_entry_diagnostics(hass, entry) -> dict:
    """Neexportovat config/options, EANy, zprávy, účty, tokeny ani uložené doklady.

    Export je whitelist, proto nové interní atributy nejsou automaticky veřejné.
    Soukromý čtecí příkaz pro správce vrací více detailů než tento export.
    """
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None:
        return {"ready": False}
    coordinator = runtime.coordinator
    quality = coordinator.data_quality
    return {
        "ready": True,
        "result": coordinator.last_attempt_result,
        "http_status": runtime.api.last_status,
        "failure_category": runtime.api.last_failure_category,
        "last_success": coordinator.last_success_at.isoformat()
        if coordinator.last_success_at
        else None,
        "next_attempt": coordinator.next_attempt_at.isoformat()
        if coordinator.next_attempt_at
        else None,
        "data_quality": {
            key: quality.get(key)
            for key in (
                "resolution",
                "incomplete_days",
                "incomplete_hours",
                "incomplete_blocks",
                "queued_hours",
                "queued_target_hours",
                "latest_data_day",
                "hourly_reason",
            )
        },
    }
