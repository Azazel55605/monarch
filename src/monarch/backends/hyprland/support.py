"""Explain the verified write boundary independently of configuration ownership."""

from monarch.backends.hyprland.inspector import Inspection
from monarch.domain.advanced import basic_issues


def blockers(
    inspection: Inspection, *, include_advanced: bool = True
) -> tuple[tuple[str, str], ...]:
    issues = []
    if not inspection.capabilities.stable_baseline:
        issues.append(
            (
                "unsupported_build",
                "Writes require the clean Hyprland 0.57.2 release; this build remains inspectable.",
            )
        )
    if inspection.capabilities.provider != "lua":
        issues.append(
            (
                "legacy_provider"
                if inspection.capabilities.provider == "hyprlang"
                else "unknown_provider",
                "Monitor writes require Lua. Legacy hyprlang editing and automatic conversion "
                "are not supported.",
            )
        )
    if not inspection.config.verified:
        issues.append(
            (
                "unverified_config",
                "The active config target is unverified. Check the compositor launch path "
                "and supported XDG resolver.",
            )
        )
    if not inspection.monitors:
        issues.append(("no_outputs", "No connected outputs are available."))
    if include_advanced:
        for reason in basic_issues(inspection.monitors):
            issues.append(
                ("advanced_state", reason + " Resolve this state before guarded changes.")
            )
    return tuple(issues)
