"""Deterministic, data-only topology policy; no guessing and no mutations."""

from dataclasses import dataclass
from typing import Any

from monarch.domain.advanced import basic_issues
from monarch.domain.layout import Layout, capture_output
from monarch.domain.monitors import Monitor
from monarch.domain.profiles import Profile, candidates_for, resolve
from monarch.errors import MonarchError


@dataclass(frozen=True)
class Rule:
    profile: str
    mode: str = "exact"
    priority: int = 0
    connectors: bool = False

    @classmethod
    def parse(cls, value: object) -> "Rule":
        if not isinstance(value, dict) or set(value) not in (
            {"profile", "mode", "priority"},
            {"profile", "mode", "priority", "connectors"},
        ):
            raise MonarchError("Invalid automation rule fields.")
        if not isinstance(value["profile"], str) or len(value["profile"]) != 32:
            raise MonarchError("An automation rule requires a saved profile ID.")
        if value["mode"] not in ("exact", "subset"):
            raise MonarchError("Matching must be exact or subset.")
        if type(value["priority"]) is not int or not -1000 <= value["priority"] <= 1000:
            raise MonarchError("Priority must be an integer between -1000 and 1000.")
        if type(value.get("connectors", False)) is not bool:
            raise MonarchError("Connector binding must be explicitly true or false.")
        return cls(
            value["profile"], value["mode"], value["priority"], value.get("connectors", False)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "mode": self.mode,
            "priority": self.priority,
            "connectors": self.connectors,
        }


@dataclass(frozen=True)
class Policy:
    enabled: bool = False
    rules: tuple[Rule, ...] = ()

    @classmethod
    def parse(cls, value: object) -> "Policy":
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "enabled", "rules"}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or type(value["enabled"]) is not bool
            or not isinstance(value["rules"], list)
            or len(value["rules"]) > 128
        ):
            raise MonarchError("Invalid or unsupported automation policy.")
        rules = tuple(Rule.parse(row) for row in value["rules"])
        if len({r.profile for r in rules}) != len(rules):
            raise MonarchError("Each profile may have only one automatic matching rule.")
        return cls(value["enabled"], rules)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "enabled": self.enabled,
            "rules": [r.to_dict() for r in self.rules],
        }


@dataclass(frozen=True)
class Selection:
    reason: str
    profile: Profile | None = None
    layout: Layout | None = None
    rejected: tuple[str, ...] = ()


def topology(monitors: tuple[Monitor, ...]) -> tuple[object, ...]:
    # Exclude geometry, scale and enabled state: our own previews must not create
    # a new topology/feedback cycle. Include advertised modes for fresh capability checks.
    return tuple(
        sorted(
            (
                m.name,
                m.make,
                m.model,
                m.serial,
                tuple((x.width, x.height, str(x.refresh_hz)) for x in m.modes),
            )
            for m in monitors
        )
    )


def match(profile: Profile, rule: Rule, monitors: tuple[Monitor, ...]) -> Layout:
    bindings = {o.name: o.name for o in profile.layout.outputs} if rule.connectors else None
    if rule.mode == "exact":
        return resolve(profile, monitors, bindings)
    selected = []
    for output in profile.layout.outputs:
        candidates = candidates_for(output, monitors)
        if rule.connectors:
            candidates = [m for m in candidates if m.name == output.name]
        if len(candidates) != 1:
            raise MonarchError("Subset identity is missing or ambiguous.")
        selected.append(candidates[0])
    if len({m.name for m in selected}) != len(selected):
        raise MonarchError("Subset identities are not one-to-one.")
    wanted = resolve(profile, tuple(selected), bindings)
    # Unknown extras retain their CURRENT settings, including enabled state.
    extras = tuple(m for m in monitors if m.name not in {o.name for o in wanted.outputs})
    current = Layout(tuple(capture_output(m) for m in extras))
    names = {o.name for o in wanted.outputs}
    layout = Layout(wanted.outputs + tuple(o for o in current.outputs if o.name not in names))
    layout.validate(monitors)
    return layout


def choose(
    policy: Policy, profiles: tuple[Profile, ...], monitors: tuple[Monitor, ...]
) -> Selection:
    if not policy.enabled:
        return Selection("Automatic switching is disabled.")
    advanced = basic_issues(monitors)
    if advanced:
        return Selection(
            "Advanced state is outside the verified basic guard; preserving layout.",
            rejected=advanced,
        )
    by_id = {p.id: p for p in profiles}
    eligible = []
    rejected = []
    for rule in policy.rules:
        profile = by_id.get(rule.profile)
        if profile is None:
            rejected.append("A rule references a deleted profile.")
            continue
        try:
            layout = match(profile, rule, monitors)
        except MonarchError as exc:
            rejected.append(f"{profile.name}: {exc}")
            continue
        rank = (rule.priority, rule.mode == "exact", len(profile.layout.outputs))
        eligible.append((rank, profile, layout))
    if not eligible:
        return Selection(
            "No eligible profile; preserving the current layout.", rejected=tuple(rejected)
        )
    best = max(row[0] for row in eligible)
    winners = [row for row in eligible if row[0] == best]
    if len(winners) != 1:
        return Selection(
            "Matching profiles tie; preserving the current layout.", rejected=tuple(rejected)
        )
    _, profile, layout = winners[0]
    return Selection(
        f"Selected {profile.name} by priority, exactness and specificity.",
        profile,
        layout,
        tuple(rejected),
    )
