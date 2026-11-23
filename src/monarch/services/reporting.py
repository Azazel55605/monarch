"""Allowlisted diagnostic fields; no arbitrary compositor text in shared reports."""

from dataclasses import asdict
from typing import Any

from monarch.backends.hyprland.inspector import Inspection

SAFE_NOTES = {
    "compositor command line",
    "compositor environment",
    "compositor XDG reload search",
    "XDG candidate",
    "safe mode",
    "user selection",
    "compositor process unavailable",
    "unavailable; select --config explicitly",
    "Unsupported relative or empty XDG config search entry",
    "Version is outside the verified stable baseline; inspection only.",
    "Config provider is unknown; no provider inferred from filename.",
    "Active configuration path is unverified; no files will be modified.",
    "No connected outputs reported by Hyprland.",
    "hyprctl timed out; the compositor may be unavailable.",
    "hyprctl was not found. Install Hyprland and check PATH.",
    "Cannot start hyprctl. Check executable permissions.",
    "hyprctl request failed. Check the selected Hyprland session.",
    "hyprctl response exceeded the configured size limit.",
    "Missing or invalid scale",
    "Missing or invalid refreshRate",
    "Missing or invalid disabled state",
    "Available modes missing",
    "Unrecognized available mode omitted",
    "Unrecognized mirror target",
    "Unresolved mirror target",
    "Unsupported transform",
}
SAFE_NOTES.update("Missing or invalid " + key for key in ("width", "height", "transform", "x", "y"))
SAFE_NOTES.update(
    "hyprctl returned invalid JSON for " + key + "."
    for key in ("version", "status", "monitors all")
)
SAFE_NOTES.update("Unexpected " + key + " response shape." for key in ("version", "status"))


def safe_note(value: str) -> str:
    return value if value in SAFE_NOTES else "Unrecognized diagnostic detail omitted."


def report(inspection: Inspection, *, identifiers: bool = False) -> dict[str, Any]:
    """Reports redact identities and paths by default, including free-form fields."""
    monitors = []
    labels = {monitor.name: f"display-{i}" for i, monitor in enumerate(inspection.monitors, 1)}
    for monitor in inspection.monitors:
        monitors.append(
            {
                "output": monitor.name if identifiers else labels[monitor.name],
                "description": monitor.description if identifiers else "[redacted]",
                "make": monitor.make if identifiers else "[redacted]",
                "model": monitor.model if identifiers else "[redacted]",
                "serial": monitor.serial if identifiers else "[redacted]",
                "width": monitor.width,
                "height": monitor.height,
                "refresh_hz": str(monitor.refresh_hz) if monitor.refresh_hz is not None else None,
                "x": monitor.x,
                "y": monitor.y,
                "scale": monitor.scale,
                "transform": monitor.transform,
                "disabled": monitor.disabled,
                "mirror_of": (
                    "unresolved"
                    if not monitor.mirror_known
                    else monitor.mirror_of
                    if identifiers
                    else labels.get(monitor.mirror_of or "", "unresolved")
                    if monitor.mirror_of
                    else None
                ),
                "logical_size": monitor.logical_size,
                "modes": [
                    {"width": m.width, "height": m.height, "refresh_hz": str(m.refresh_hz)}
                    for m in monitor.modes
                ],
                "warnings": [safe_note(note) for note in monitor.warnings],
                "advanced": monitor.advanced.to_dict(),
            }
        )
    capabilities = asdict(inspection.capabilities)
    if not identifiers:
        capabilities["mutation_reason"] = (
            "Inspection is read-only; writes require a verified owned config and guard."
        )
        if capabilities["provider"] not in ("lua", "hyprlang", "unknown"):
            capabilities["provider"] = "unknown"
    # Unknown backend strings are not trusted free-form report content.
    if not identifiers and capabilities["backend"] not in ("drm", "wayland", "unknown"):
        capabilities["backend"] = "unknown"
    if not identifiers and capabilities["version"] is not None:
        import re

        match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:[-+][\w.-]+)?", capabilities["version"])
        capabilities["version"] = match[1] if match else "unknown"
    return {
        "schema_version": 1,
        "capabilities": capabilities,
        "config": {
            "path": str(inspection.config.path)
            if identifiers and inspection.config.path
            else "[redacted]"
            if inspection.config.path
            else None,
            "source": safe_note(inspection.config.source),
            "verified": inspection.config.verified,
        },
        "monitors": monitors,
        "diagnostics": [safe_note(note) for note in inspection.diagnostics],
    }
