"""Resolve exact stable HA/test-plugin pairs for dashboard integration tests."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from functools import cache
from urllib.request import Request, urlopen


@cache
def fetch_metadata(package: str, version: str | None = None) -> dict:
    """Bounded requests to public PyPI metadata only."""
    suffix = f"/{version}" if version else ""
    request = Request(f"https://pypi.org/pypi/{package}{suffix}/json", headers={
        "Accept": "application/json", "User-Agent": "edc-sharing-stats-ci",
    })
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def resolve_environment(
    version: str | None = None, fetch: Callable = fetch_metadata,
) -> dict[str, str]:
    """Never downgrade latest stable HA to accommodate a beta-targeting plugin."""
    core = fetch("homeassistant", version)["info"]
    version = core["version"]
    if re.fullmatch(r"\d{4}\.\d+\.\d+", version) is None:
        raise ValueError("Home Assistant must be an exact stable release")
    plugin = fetch("pytest-homeassistant-custom-component", None)
    candidates = sorted(
        (v for v, files in plugin["releases"].items()
         if re.fullmatch(r"\d+\.\d+\.\d+", v)
         and any(not f.get("yanked", False) for f in files)),
        key=lambda v: tuple(map(int, v.split("."))), reverse=True,
    )
    for candidate in candidates[:40]:
        info = plugin["info"] if candidate == plugin["info"]["version"] else fetch(
            "pytest-homeassistant-custom-component", candidate
        )["info"]
        dependencies = {d.partition(";")[0].replace(" ", "") for d in info.get("requires_dist") or []}
        if f"homeassistant=={version}" not in dependencies:
            continue
        versions = []
        for requirement in (core["requires_python"], info["requires_python"]):
            match = re.search(r">=\s*(\d+)\.(\d+)", requirement)
            if match is None:
                raise ValueError("Cannot determine required Python version")
            versions.append((int(match[1]), int(match[2])))
        major, minor = max(versions)
        return {"homeassistant": version, "test_plugin": candidate, "python": f"{major}.{minor}"}
    raise ValueError(f"No matching test plugin for stable HA {version}; no beta or older substitution allowed")


if __name__ == "__main__":
    print(json.dumps({"include": [resolve_environment("2026.8.0"), resolve_environment()]}))
