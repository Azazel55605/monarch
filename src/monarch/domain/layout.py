"""Strict data-only layouts. Names are session connectors, identities prevent rebinding."""

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from monarch.domain.monitors import Mode, Monitor
from monarch.errors import MonarchError


@dataclass(frozen=True)
class Output:
    name: str
    make: str
    model: str
    serial: str
    mode: str
    scale: float
    transform: int
    x: int
    y: int
    enabled: bool = True
    mirror: str = ""
    vrr: int = 0

    @classmethod
    def parse(cls, row: object, *, allow_preferred: bool = False) -> "Output":
        fields = set(cls.__dataclass_fields__)
        if not isinstance(row, dict) or set(row) != fields:
            raise MonarchError("Each output must provide exactly the documented layout fields.")
        for key in ("name", "make", "model", "serial", "mode", "mirror"):
            if not isinstance(row[key], str) or len(row[key]) > 512 or "\x00" in row[key]:
                raise MonarchError("Invalid output text field.")
        if not row["name"] or row["name"].startswith("desc:"):
            raise MonarchError("An explicit output connector name is required.")
        for key in ("x", "y", "transform"):
            if type(row[key]) is not int or not -(2**31) < row[key] < 2**31:
                raise MonarchError("Invalid output coordinate or transform.")
        if not 0 <= row["transform"] <= 7 or type(row["enabled"]) is not bool:
            raise MonarchError("Invalid output transform or enabled state.")
        if type(row["vrr"]) is not int or row["vrr"] not in (0, 1):
            raise MonarchError("VRR policy must be Off (0) or On (1).")
        scale = row["scale"]
        if type(scale) not in (int, float) or not 0.25 <= scale <= 8:
            raise MonarchError("Scale must be finite and between 0.25 and 8.")
        if not math.isfinite(scale):
            raise MonarchError("Scale must be finite.")
        if row["mode"] != "preferred":
            try:
                mode = Mode.parse(row["mode"] + "Hz")
            except ValueError as exc:
                raise MonarchError("Use an advertised WIDTHxHEIGHT@HZ mode.") from exc
            if mode.width > 65536 or mode.height > 65536 or mode.refresh_hz > 10000:
                raise MonarchError("Mode exceeds the supported limits.")
            if any(abs(v / scale - round(v / scale)) > 0.001 for v in (mode.width, mode.height)):
                raise MonarchError("Scale must produce integer logical dimensions.")
        elif row["enabled"] and not allow_preferred:
            raise MonarchError(
                "Select an advertised resolution and refresh rate for each enabled display."
            )
        return cls(**row)

    @property
    def size(self) -> tuple[int, int]:
        mode = Mode.parse(self.mode + "Hz")
        w, h = mode.width, mode.height
        if self.transform % 2:
            w, h = h, w
        return round(w / self.scale), round(h / self.scale)


@dataclass(frozen=True)
class Layout:
    outputs: tuple[Output, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 2, "outputs": [asdict(output) for output in self.outputs]}

    @classmethod
    def parse(cls, data: object) -> "Layout":
        if not isinstance(data, dict) or set(data) != {"schema_version", "outputs"}:
            raise MonarchError("Layout must contain schema_version and outputs only.")
        if type(data["schema_version"]) is not int or data["schema_version"] not in (1, 2):
            raise MonarchError("Unsupported layout schema version.")
        if not isinstance(data["outputs"], list) or not 1 <= len(data["outputs"]) <= 32:
            raise MonarchError("Layout must contain between 1 and 32 outputs.")
        outputs = []
        for row in data["outputs"]:
            if data["schema_version"] == 1:
                if not isinstance(row, dict) or "vrr" in row:
                    raise MonarchError("Legacy layouts cannot contain VRR policy.")
                row = dict(row, vrr=0)
            outputs.append(Output.parse(row))
        layout = cls(tuple(outputs))
        layout.validate_structure()
        return layout

    def validate_structure(self) -> None:
        names = {output.name for output in self.outputs}
        if len(names) != len(self.outputs):
            raise MonarchError("Duplicate output connectors.")
        enabled = {o.name: o for o in self.outputs if o.enabled}
        if not any(not o.mirror for o in enabled.values()):
            raise MonarchError("A layout must leave at least one usable unmirrored output.")
        for output in self.outputs:
            if output.mirror:
                target = enabled.get(output.mirror)
                if not output.enabled or target is None or target is output or target.mirror:
                    raise MonarchError(
                        "Mirror targets must be enabled roots; chains/cycles are invalid."
                    )

    def validate(self, monitors: tuple[Monitor, ...]) -> None:
        # Reparse even programmatically constructed layouts at the trust boundary.
        Layout.parse(self.to_dict())
        live = {monitor.name: monitor for monitor in monitors}
        if set(live) != {output.name for output in self.outputs}:
            raise MonarchError("Connected topology changed or layout omits connected outputs.")
        for output in self.outputs:
            monitor = live[output.name]
            if not monitor.mirror_known:
                raise MonarchError(
                    "The compositor mirror target is unresolved; refresh before applying."
                )
            if (output.make, output.model, output.serial) != (
                monitor.make,
                monitor.model,
                monitor.serial,
            ):
                raise MonarchError("Output identity changed; capture a new layout.")
            if output.enabled:
                if output.vrr and monitor.advanced.vrr_capable is not True:
                    raise MonarchError("VRR On requires a display reporting VRR capability.")
                desired = Mode.parse(output.mode + "Hz")
                if not any(
                    mode.width == desired.width
                    and mode.height == desired.height
                    and abs(mode.refresh_hz - desired.refresh_hz) <= Decimal(".02")
                    for mode in monitor.modes
                ):
                    raise MonarchError("Requested mode is not advertised by the connected output.")

    def matches(self, monitors: tuple[Monitor, ...]) -> bool:
        live = {monitor.name: monitor for monitor in monitors}
        if set(live) != {o.name for o in self.outputs}:
            return False
        for output in self.outputs:
            m = live[output.name]
            if not m.mirror_known:
                return False
            if (output.make, output.model, output.serial) != (m.make, m.model, m.serial):
                return False
            if m.disabled is None or output.enabled == m.disabled:
                return False
            if not output.enabled:
                continue
            mode = Mode.parse(output.mode + "Hz")
            if (
                m.width != mode.width
                or m.height != mode.height
                or m.refresh_hz is None
                or abs(m.refresh_hz - mode.refresh_hz) > Decimal(".1")
                or m.scale is None
                or abs(m.scale - output.scale) > 0.001
                or m.transform != output.transform
                or (m.mirror_of or "") != output.mirror
                or m.advanced.vrr_active is not bool(output.vrr)
            ):
                return False
            if not output.mirror and (m.x, m.y) != (output.x, output.y):
                return False
        return True

    @classmethod
    def capture(
        cls, monitors: tuple[Monitor, ...], *, vrr_policies: Mapping[str, int] | None = None
    ) -> "Layout":
        vrr_policies = vrr_policies or {}
        if set(vrr_policies) - {m.name for m in monitors}:
            raise MonarchError("VRR policy refers to an unknown output.")
        outputs = tuple(capture_output(m, policy=vrr_policies.get(m.name, 0)) for m in monitors)
        return cls.parse(cls(outputs).to_dict())


def capture_output(m: Monitor, *, policy: int = 0) -> Output:
    if not m.mirror_known:
        raise MonarchError("Cannot capture an unresolved compositor mirror target.")
    if m.disabled is None:
        raise MonarchError("Cannot capture an output with unknown enabled state.")
    if not m.disabled and m.advanced.vrr_active is not bool(policy):
        raise MonarchError(
            "Cannot infer VRR policy from active state. Use an owned Off/On policy "
            "or explicitly select VRR in the editor and save the edited draft."
        )
    candidates = [
        mode
        for mode in m.modes
        if mode.width == m.width
        and mode.height == m.height
        and m.refresh_hz is not None
        and abs(mode.refresh_hz - m.refresh_hz) < Decimal(".1")
    ]
    if not m.disabled and (
        not candidates or m.scale is None or m.transform is None or m.x is None or m.y is None
    ):
        raise MonarchError("Current output settings cannot be represented safely.")
    mode = candidates[0] if candidates else None
    output = Output(
        m.name,
        m.make,
        m.model,
        m.serial,
        f"{mode.width}x{mode.height}@{mode.refresh_hz}" if mode else "preferred",
        m.scale or 1,
        m.transform or 0,
        m.x or 0,
        m.y or 0,
        not m.disabled,
        m.mirror_of or "",
        policy,
    )
    return Output.parse(asdict(output), allow_preferred=not output.enabled)


def lua_string(value: str) -> str:
    """Lua short strings use decimal byte escapes, not JSON's incompatible \\u."""
    return (
        '"'
        + "".join(
            chr(b) if 32 <= b < 127 and b not in (34, 92) else f"\\{b:03d}"
            for b in value.encode("utf-8")
        )
        + '"'
    )


def rule(output: Output, *, legacy: bool = False) -> str:
    Output.parse(asdict(output), allow_preferred=True)
    if legacy and output.vrr:
        raise MonarchError("Legacy monitor rules cannot represent VRR On.")
    return (
        "hl.monitor({"
        + ",".join(
            [
                "output=" + lua_string(output.name),
                "mode=" + lua_string(output.mode),
                "scale=" + repr(float(output.scale)),
                "transform=" + str(output.transform),
                "position=" + lua_string(f"{output.x}x{output.y}"),
                "disabled=" + ("false" if output.enabled else "true"),
                "mirror=" + lua_string(output.mirror),
            ]
            + ([] if legacy else ["vrr=" + str(output.vrr)])
        )
        + "})"
    )


def ordered(layout: Layout) -> tuple[Output, ...]:
    # Enabled roots, enabled mirrors, disabled outputs: never disable destinations first.
    return tuple(sorted(layout.outputs, key=lambda o: (not o.enabled, bool(o.mirror))))
