"""Parse monitor observations without executing compositor or Qt code."""

import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from monarch.errors import MonarchError

_MODE = re.compile(r"(?P<w>\d+)x(?P<h>\d+)@(?P<r>\d+(?:\.\d+)?)Hz")


@dataclass(frozen=True)
class Mode:
    width: int
    height: int
    refresh_hz: Decimal

    @classmethod
    def parse(cls, value: str) -> "Mode":
        match = _MODE.fullmatch(value)
        if not match:
            raise ValueError("Unsupported mode format")
        mode = cls(int(match["w"]), int(match["h"]), Decimal(match["r"]))
        if mode.width <= 0 or mode.height <= 0 or mode.refresh_hz <= 0:
            raise ValueError("Mode dimensions and refresh must be positive")
        return mode


@dataclass(frozen=True)
class Monitor:
    name: str
    description: str
    make: str
    model: str
    serial: str
    width: int | None
    height: int | None
    refresh_hz: Decimal | None
    x: int | None
    y: int | None
    scale: float | None
    transform: int | None
    disabled: bool | None
    mirror_of: str | None
    modes: tuple[Mode, ...]
    warnings: tuple[str, ...] = ()

    @property
    def logical_size(self) -> tuple[float, float] | None:
        if not self.width or not self.height or not self.scale or self.transform is None:
            return None
        w, h = self.width, self.height
        if self.transform % 2:
            w, h = h, w
        size = w / self.scale, h / self.scale
        return size if all(math.isfinite(value) for value in size) else None


def _integer(data: dict[str, Any], key: str, warnings: list[str]) -> int | None:
    value = data.get(key)
    if type(value) is int and -(2**31) <= value < 2**31:
        return int(value)
    warnings.append(f"Missing or invalid {key}")
    return None


def _positive_finite(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


def parse_monitors(data: object) -> tuple[Monitor, ...]:
    if not isinstance(data, list):
        raise MonarchError("Monitor response must be a JSON array; discovery is unavailable.")
    monitors: list[Monitor] = []
    names: set[str] = set()
    for item in data:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"]:
            raise MonarchError("Monitor response contains an invalid output name.")
        name = item["name"]
        if name in names:
            raise MonarchError("Monitor response contains duplicate output names.")
        names.add(name)
        warnings: list[str] = []
        width = _integer(item, "width", warnings)
        height = _integer(item, "height", warnings)
        transform = _integer(item, "transform", warnings)
        if width is not None and width <= 0:
            width = None
        if height is not None and height <= 0:
            height = None
        if transform is not None and not 0 <= transform <= 7:
            warnings.append("Unsupported transform")
            transform = None
        raw_scale = item.get("scale")
        scale = None
        if isinstance(raw_scale, (int, float)) and _positive_finite(raw_scale):
            scale = float(raw_scale)
        else:
            warnings.append("Missing or invalid scale")
        raw_refresh = item.get("refreshRate")
        refresh = None
        if isinstance(raw_refresh, (int, float)) and _positive_finite(raw_refresh):
            refresh = Decimal(str(raw_refresh))
        else:
            warnings.append("Missing or invalid refreshRate")
        disabled = item.get("disabled")
        if type(disabled) is not bool:
            disabled = None
            warnings.append("Missing or invalid disabled state")
        modes: list[Mode] = []
        raw_modes = item.get("availableModes")
        if not isinstance(raw_modes, list):
            warnings.append("Available modes missing")
            raw_modes = []
        for raw in raw_modes:
            try:
                if not isinstance(raw, str):
                    raise ValueError("Expected a mode string")
                mode = Mode.parse(raw)
                if mode not in modes:
                    modes.append(mode)
            except ValueError:
                warnings.append("Unrecognized available mode omitted")
        mirror = item.get("mirrorOf")
        if mirror in ("none", "", None):
            mirror = None
        elif not isinstance(mirror, str):
            mirror = None
            warnings.append("Unrecognized mirror target")

        def text(key: str, data: dict[str, Any] = item) -> str:
            value = data.get(key)
            return value if isinstance(value, str) else ""

        monitors.append(
            Monitor(
                name=name,
                description=text("description"),
                make=text("make"),
                model=text("model"),
                serial=text("serial"),
                width=width,
                height=height,
                refresh_hz=refresh,
                x=_integer(item, "x", warnings),
                y=_integer(item, "y", warnings),
                scale=scale,
                transform=transform,
                disabled=disabled,
                mirror_of=mirror,
                modes=tuple(modes),
                warnings=tuple(warnings),
            )
        )
    return tuple(monitors)
