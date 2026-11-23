"""Read kernel connector state for unambiguous native DRM outputs."""

import re
from dataclasses import replace
from pathlib import Path

from monarch.domain.monitors import Monitor

CONNECTOR = re.compile(r"card[0-9]+-(.+)")
LINK_ERROR = (
    "Linux still reports a requested display disabled after modesetting. "
    "Check the display input, cable, or compositor/driver log."
)


def read_connector_states(
    monitors: tuple[Monitor, ...], directory: Path = Path("/sys/class/drm")
) -> tuple[Monitor, ...]:
    states: dict[str, list[bool | None]] = {}
    try:
        for connector in directory.iterdir():
            match = CONNECTOR.fullmatch(connector.name)
            if not match:
                continue
            try:
                status = (connector / "status").read_text().strip()
            except OSError:
                status = "unknown"
            if status == "disconnected":
                continue
            enabled = None
            if status == "connected":
                try:
                    value = (connector / "enabled").read_text().strip()
                except OSError:
                    value = ""
                enabled = {"enabled": True, "disabled": False}.get(value)
            states.setdefault(match[1], []).append(enabled)
    except OSError:
        return monitors
    unique = {name: values[0] for name, values in states.items() if len(values) == 1}
    return tuple(replace(m, connector_enabled=unique.get(m.name)) for m in monitors)


def disabled_links(monitors: tuple[Monitor, ...]) -> tuple[str, ...]:
    return tuple(
        m.name
        for m in monitors
        if m.disabled is False and m.dpms_on is True and m.connector_enabled is False
    )
