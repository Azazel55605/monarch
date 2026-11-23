"""Portable profile data and conservative, one-to-one physical output resolution."""

from dataclasses import dataclass, replace
from typing import Any

from monarch.domain.layout import Layout, Output
from monarch.domain.monitors import Monitor
from monarch.errors import MonarchError


class MappingRequired(MonarchError):
    """An explicit physical mapping is needed for this topology."""


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    layout: Layout

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "layout": self.layout.to_dict()}


def profile_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 80:
        raise MonarchError("Profile names must contain 1–80 characters.")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise MonarchError("Profile names cannot contain control characters.")
    return value.strip()


def candidates_for(output: Output, monitors: tuple[Monitor, ...]) -> list[Monitor]:
    serial = output.serial.strip()
    usable = serial.casefold() not in {"", "0", "unknown", "none", "n/a"}
    return [
        m
        for m in monitors
        if (m.make, m.model) == (output.make, output.model)
        and (not usable or m.serial == output.serial)
    ]


def resolve(
    profile: Profile, monitors: tuple[Monitor, ...], bindings: dict[str, str] | None = None
) -> Layout:
    """Require the exact physical set; never guess a duplicate/absent serial mapping.

    Unique serial identities survive connector renames. Without a usable serial,
    only a unique make/model AND the original connector are accepted. Ambiguous
    twins require explicit per-switch bindings; connector equality cannot identify them.
    """
    if len(profile.layout.outputs) != len(monitors):
        raise MonarchError("Profile needs its exact display set; outputs are missing or extra.")
    bindings = bindings or {}
    if set(bindings) - {o.name for o in profile.layout.outputs}:
        raise MonarchError("Mapping contains an unknown saved connector.")
    mapping: dict[str, str] = {}
    claimed: set[str] = set()
    for output in profile.layout.outputs:
        serial = output.serial.strip()
        usable = serial.casefold() not in {"", "0", "unknown", "none", "n/a"}
        candidates = candidates_for(output, monitors)
        saved_twins = [
            o
            for o in profile.layout.outputs
            if (o.make, o.model) == (output.make, output.model)
            and (not usable or o.serial == output.serial)
        ]
        explicit = bindings.get(output.name)
        if explicit:
            candidates = [m for m in candidates if m.name == explicit]
        if not candidates:
            raise MonarchError("A required profile display is missing or has changed identity.")
        if len(candidates) != 1 or (len(saved_twins) != 1 and not explicit):
            raise MappingRequired(
                "Display identity is ambiguous; map each physical output explicitly."
            )
        monitor = candidates[0]
        if not usable and monitor.name != output.name and not explicit:
            raise MappingRequired(
                "A display without a serial changed connector; map it explicitly."
            )
        if monitor.name in claimed:
            raise MonarchError("Profile identities do not map one-to-one to connected displays.")
        claimed.add(monitor.name)
        mapping[output.name] = monitor.name
    live = {m.name: m for m in monitors}
    outputs = []
    for output in profile.layout.outputs:
        monitor = live[mapping[output.name]]
        outputs.append(
            replace(
                output,
                name=monitor.name,
                make=monitor.make,
                model=monitor.model,
                serial=monitor.serial,
                mirror=mapping.get(output.mirror, ""),
            )
        )
    layout = Layout(tuple(outputs))
    layout.validate(monitors)
    return layout
