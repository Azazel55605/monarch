"""Observed advanced state and evidence gates; these are not write capabilities."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from monarch.errors import MonarchError

if TYPE_CHECKING:
    from monarch.domain.monitors import Monitor

FORMATS = {
    "XRGB8888": 8,
    "ARGB8888": 8,
    "XBGR8888": 8,
    "ABGR8888": 8,
    "XRGB2101010": 10,
    "ARGB2101010": 10,
    "XBGR2101010": 10,
    "ABGR2101010": 10,
    "ABGR16161616F": 16,
    "XBGR16161616F": 16,
}
PRESETS = {"auto", "srgb", "wide", "edid", "hdr", "hdredid", "dcip3", "dp3", "adobe"}


@dataclass(frozen=True)
class AdvancedState:
    vrr_active: bool | None = None
    vrr_capable: bool | None = None
    current_format: str | None = None
    color_preset: str | None = None
    hdr_metadata: bool | None = None
    bt2020: bool | None = None
    sdr_brightness: float | None = None
    sdr_saturation: float | None = None
    sdr_min_luminance: float | None = None
    sdr_max_luminance: float | None = None

    @property
    def bit_depth(self) -> int | None:
        return FORMATS.get(self.current_format or "")

    def to_dict(self) -> dict[str, Any]:
        return dict(asdict(self), observed_bit_depth=self.bit_depth, icc_state="not_reported")

    @classmethod
    def parse(cls, data: dict[str, Any]) -> AdvancedState:
        hardware = data.get("hardwareDetails")
        hardware = hardware if isinstance(hardware, dict) else {}

        def boolean(value: object) -> bool | None:
            return value if type(value) is bool else None

        def number(key: str) -> float | None:
            value = data.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                try:
                    if math.isfinite(value) and 0 <= value <= 100000:
                        return float(value)
                except OverflowError:
                    pass
            return None

        raw_format = data.get("currentFormat")
        raw_preset = data.get("colorManagementPreset")
        return cls(
            boolean(data.get("vrr")),
            boolean(hardware.get("vrrCapable")),
            raw_format if isinstance(raw_format, str) and raw_format in FORMATS else None,
            raw_preset if isinstance(raw_preset, str) and raw_preset in PRESETS else None,
            boolean(hardware.get("hdr")),
            boolean(hardware.get("bt2020")),
            number("sdrBrightness"),
            number("sdrSaturation"),
            number("sdrMinLuminance"),
            number("sdrMaxLuminance"),
        )


@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    observation: str
    writable: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def yes_no(value: bool | None) -> str:
    return "Unknown" if value is None else "Yes" if value else "No"


def features(state: AdvancedState) -> tuple[Feature, ...]:
    deferred = "Hardware apply and rollback have not been validated; control is unavailable."
    return (
        Feature(
            "vrr",
            "Variable refresh rate",
            f"Active: {yes_no(state.vrr_active)}; capable: {yes_no(state.vrr_capable)}",
            state.vrr_capable is True and state.vrr_active is not None,
            "Off/On policies are configured in the display editor and use guarded preview. "
            "Conditional modes remain unavailable; active state does not reveal their policy.",
        ),
        Feature(
            "bit_depth",
            "Bit depth",
            f"Current: {state.bit_depth or 'Unknown'}; format: {state.current_format or 'Unknown'}",
            False,
            "Current format does not advertise supported bit depths. " + deferred,
        ),
        Feature("color", "Color preset", state.color_preset or "Unknown", False, deferred),
        Feature(
            "hdr",
            "HDR",
            "EDID HDR metadata: " + yes_no(state.hdr_metadata),
            False,
            "Advertised metadata does not prove working HDR output or recovery. " + deferred,
        ),
        Feature(
            "icc",
            "ICC profile",
            "Not reported by monitor IPC",
            False,
            "The active ICC file/contents cannot be reconstructed from these observations. "
            + deferred,
        ),
    )


def basic_issues(monitors: tuple[Monitor, ...]) -> tuple[str, ...]:
    """SDR gate; known VRR On/Off is verified separately against each layout."""
    issues: set[str] = set()
    for monitor in monitors:
        if monitor.disabled is True:
            continue
        state = monitor.advanced
        if state.vrr_active is None:
            issues.add("VRR state is unknown; policy application and recovery cannot be verified.")
        if state.bit_depth != 8:
            issues.add("The current pixel format is not verified 8-bit SDR.")
        if state.color_preset != "srgb":
            issues.add("The color preset is not verified sRGB.")
        values = (
            (state.sdr_brightness, 1),
            (state.sdr_saturation, 1),
            (state.sdr_min_luminance, 0.2),
            (state.sdr_max_luminance, 80),
        )
        if any(value is None or abs(value - expected) > 0.0001 for value, expected in values):
            issues.add("SDR color parameters differ from the basic baseline or are unknown.")
    return tuple(sorted(issues))


def require_basic(monitors: tuple[Monitor, ...]) -> None:
    issues = basic_issues(monitors)
    if issues:
        raise MonarchError(
            "Advanced display state cannot be restored by the basic guard. " + " ".join(issues)
        )


def hdr_available(monitor: Monitor) -> bool:
    return (
        monitor.disabled is False
        and monitor.mirror_known
        and not monitor.mirror_of
        and monitor.dpms_on is not False
        and monitor.advanced.hdr_metadata is True
        and monitor.advanced.bt2020 is True
    )
