"""Qt-independent draft state, geometry and stale-edit policy."""

from dataclasses import replace
from decimal import Decimal
from typing import Any

from monarch.backends.hyprland.inspector import Inspection
from monarch.domain.layout import Layout, Output
from monarch.domain.monitors import Monitor
from monarch.errors import MonarchError


def fingerprint(monitors: tuple[Monitor, ...]) -> tuple[object, ...]:
    return tuple(
        (
            m.name,
            m.make,
            m.model,
            m.serial,
            m.width,
            m.height,
            round(m.refresh_hz, 2) if m.refresh_hz else None,
            m.x,
            m.y,
            m.scale,
            m.transform,
            m.disabled,
            m.mirror_of,
            m.modes,
        )
        for m in monitors
    )


def draft_layout(monitors: tuple[Monitor, ...]) -> Layout:
    outputs = []
    for m in monitors:
        modes = [mode for mode in m.modes if (mode.width, mode.height) == (m.width, m.height)]
        if m.refresh_hz is not None:
            refresh = m.refresh_hz
            modes.sort(key=lambda mode: abs(mode.refresh_hz - refresh))
        mode = next(
            (
                mode
                for mode in modes
                if m.refresh_hz is not None and abs(mode.refresh_hz - m.refresh_hz) < Decimal(".1")
            ),
            None,
        )
        if mode is None and m.disabled:
            mode = next(iter(m.modes), None)
        observed_mode = (
            f"{m.width}x{m.height}@{m.refresh_hz}"
            if m.width and m.height and m.refresh_hz
            else "preferred"
        )
        outputs.append(
            Output(
                m.name,
                m.make,
                m.model,
                m.serial,
                f"{mode.width}x{mode.height}@{mode.refresh_hz}" if mode else observed_mode,
                m.scale or 1,
                m.transform or 0,
                m.x or 0,
                m.y or 0,
                m.disabled is not True,
                m.mirror_of or "",
            )
        )
    return Layout(tuple(outputs))


class EditorModel:
    def __init__(self) -> None:
        self.inspection: Inspection | None = None
        self.observed: Layout | None = None
        self.draft: Layout | None = None
        self.stale = False
        self.busy = False
        self.selected = ""
        self._fingerprint: tuple[object, ...] = ()

    @property
    def dirty(self) -> bool:
        return self.draft is not None and self.draft != self.observed

    def receive(self, inspection: Inspection, *, discard: bool = False) -> None:
        changed = fingerprint(inspection.monitors) != self._fingerprint
        if self.dirty and not discard:
            self.stale = self.stale or changed
        else:
            self.draft = draft_layout(inspection.monitors)
            self.observed = self.draft
            self.stale = False
        self.inspection = inspection
        self._fingerprint = fingerprint(inspection.monitors)
        names = {o.name for o in self.draft.outputs} if self.draft else set()
        if self.selected not in names:
            self.selected = next(iter(o.name for o in self.draft.outputs), "") if self.draft else ""

    def update(self, name: str, **changes: Any) -> None:
        if self.busy or self.draft is None:
            return
        self.draft = Layout(
            tuple(replace(o, **changes) if o.name == name else o for o in self.draft.outputs)
        )

    def error(self) -> str:
        if self.inspection is None or self.draft is None:
            return "Waiting for monitor discovery."
        try:
            self.draft.validate(self.inspection.monitors)
        except (MonarchError, ValueError) as exc:
            return str(exc)
        if self.stale:
            return "The connected layout changed. Revalidate your edits or discard them."
        return ""

    def revalidate(self) -> None:
        if self.inspection is None or self.draft is None:
            raise MonarchError("No connected topology is available.")
        self.draft.validate(self.inspection.monitors)
        self.observed = draft_layout(self.inspection.monitors)
        self.stale = False

    def output(self, name: str) -> Output | None:
        return next((o for o in self.draft.outputs if o.name == name), None) if self.draft else None


def size(output: Output) -> tuple[float, float]:
    if output.mode == "preferred":
        return 1280, 720
    from monarch.domain.monitors import Mode

    mode = Mode.parse(output.mode + "Hz")
    width, height = mode.width / output.scale, mode.height / output.scale
    return (height, width) if output.transform % 2 else (width, height)


def snap(layout: Layout, name: str, x: int, y: int, threshold: int = 24) -> tuple[int, int]:
    moving = next(o for o in layout.outputs if o.name == name)
    width, height = size(moving)
    x_targets = []
    y_targets = []
    for other in layout.outputs:
        if other.name == name or not other.enabled or other.mirror:
            continue
        w, h = size(other)
        x_targets.extend([other.x, other.x + w, other.x - width, other.x + w - width])
        y_targets.extend([other.y, other.y + h, other.y - height, other.y + h - height])
    if x_targets:
        nearest = min(x_targets, key=lambda value: abs(value - x))
        if abs(nearest - x) <= threshold:
            x = round(nearest)
    if y_targets:
        nearest = min(y_targets, key=lambda value: abs(value - y))
        if abs(nearest - y) <= threshold:
            y = round(nearest)
    return x, y
