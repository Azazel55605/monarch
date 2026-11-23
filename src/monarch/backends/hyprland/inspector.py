"""Observe capabilities independently; all mutation remains disabled."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from monarch.backends.hyprland.commands import Hyprctl
from monarch.backends.hyprland.session import ConfigLocation, config_location
from monarch.domain.monitors import Monitor, parse_monitors
from monarch.errors import MonarchError


@dataclass(frozen=True)
class Capabilities:
    version: str | None
    provider: str
    backend: str
    stable_baseline: bool
    lua_advertised: bool
    mutation_allowed: bool = False
    mutation_reason: str = (
        "Inspection is read-only; writes require a verified owned config and guard."
    )


@dataclass(frozen=True)
class Inspection:
    capabilities: Capabilities
    config: ConfigLocation
    monitors: tuple[Monitor, ...]
    diagnostics: tuple[str, ...]


class Inspector:
    def __init__(self, client: Hyprctl, config: Path | None = None) -> None:
        self.client = client
        self.config = config

    async def inspect(self) -> Inspection:
        diagnostics: list[str] = []

        async def optional(command: str) -> dict[str, Any]:
            try:
                value = await self.client.read(command)
                if not isinstance(value, dict):
                    raise MonarchError(f"Unexpected {command} response shape.")
                return value
            except MonarchError as exc:
                diagnostics.append(str(exc))
                return {}

        # Deliberately sequential: hyprctl requests are synchronous in Hyprland.
        version_data = await optional("version")
        status = await optional("status")
        monitors = parse_monitors(await self.client.read("monitors", "all"))
        version = version_data.get("version")
        version = version if isinstance(version, str) else None
        raw_provider = status.get("configProvider")
        provider = raw_provider if raw_provider in ("lua", "hyprlang") else "unknown"
        backend = status.get("backend")
        backend = backend if isinstance(backend, str) else "unknown"
        stable = (
            version == "0.57.2"
            and version_data.get("tag") == "v0.57.2"
            and version_data.get("dirty") is False
        )
        if not stable:
            diagnostics.append("Version is outside the verified stable baseline; inspection only.")
        if provider == "unknown":
            diagnostics.append("Config provider is unknown; no provider inferred from filename.")
        location = config_location(self.client.session, self.config)
        if not location.verified:
            diagnostics.append(
                "Active configuration path is unverified; no files will be modified."
            )
        if not monitors:
            diagnostics.append("No connected outputs reported by Hyprland.")
        return Inspection(
            Capabilities(version, provider, backend, stable, provider == "lua"),
            location,
            monitors,
            tuple(diagnostics),
        )
