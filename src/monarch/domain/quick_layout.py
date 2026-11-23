"""Build guarded layout candidates for external display shortcuts."""

from dataclasses import replace

from monarch.domain.layout import Layout, Output, capture_output
from monarch.domain.monitors import Monitor
from monarch.errors import MonarchError


def external(name: str) -> bool:
    return not name.casefold().startswith(("edp-", "lvds-", "dsi-"))


def identity(output: Output | Monitor) -> tuple[str, str, str, str]:
    return output.name, output.make, output.model, output.serial


def best_mode(output: Output, monitor: Monitor) -> Output:
    if not monitor.modes:
        raise MonarchError("The external display has no advertised modes.")
    mode = max(monitor.modes, key=lambda m: (m.width * m.height, m.refresh_hz, m.width))
    scale = output.scale
    if any(abs(n / scale - round(n / scale)) > 0.001 for n in (mode.width, mode.height)):
        scale = 1
    return replace(output, mode=f"{mode.width}x{mode.height}@{mode.refresh_hz}", scale=scale)


def new_display_layout(
    monitors: tuple[Monitor, ...], baseline: Layout, added: tuple[Monitor, ...]
) -> Layout:
    policies = {identity(o): o.vrr for o in baseline.outputs}
    current = {m.name: capture_output(m, policy=policies.get(identity(m), 0)) for m in monitors}
    names = {m.name for m in added}
    existing = [o for o in current.values() if o.name not in names and o.enabled and not o.mirror]
    if not existing:
        raise MonarchError(
            "Connect an existing independent display before extending automatically."
        )
    x = max(o.x + o.size[0] for o in existing)
    y = min(o.y for o in existing)
    for monitor in sorted(added, key=lambda m: m.name):
        output = best_mode(current[monitor.name], monitor)
        current[monitor.name] = replace(output, enabled=True, mirror="", x=x, y=y)
        x += output.size[0]
    layout = Layout(tuple(current.values()))
    layout.validate(monitors)
    return layout


def arrange_external(
    current: Layout, monitors: tuple[Monitor, ...], target: str, anchor: str, action: str
) -> Layout:
    outputs = {o.name: o for o in current.outputs}
    display, reference = outputs.get(target), outputs.get(anchor)
    if (
        not display
        or not reference
        or display == reference
        or not external(target)
        or not reference.enabled
        or reference.mirror
    ):
        raise MonarchError("Choose an external display and a different independent reference.")
    if display.mode == "preferred":
        monitor = next(m for m in monitors if m.name == target)
        display = best_mode(display, monitor)
    if action == "duplicate":
        if any(o.mirror == target for o in current.outputs):
            raise MonarchError(
                "Another display already mirrors this output. Change it in the editor."
            )
        updated = replace(display, enabled=True, mirror=anchor)
    elif action in {"left", "right", "above", "below"}:
        width, height = display.size
        ref_width, ref_height = reference.size
        x, y = {
            "left": (reference.x - width, reference.y),
            "right": (reference.x + ref_width, reference.y),
            "above": (reference.x, reference.y - height),
            "below": (reference.x, reference.y + ref_height),
        }[action]
        updated = replace(display, enabled=True, mirror="", x=x, y=y)
        for other in current.outputs:
            if other.name == target or not other.enabled or other.mirror:
                continue
            w, h = other.size
            if x < other.x + w and x + width > other.x and y < other.y + h and y + height > other.y:
                raise MonarchError(
                    "That placement overlaps another display. Pick another edge or use the editor."
                )
    else:
        raise MonarchError("Unknown external display shortcut.")
    layout = Layout(tuple(updated if o.name == target else o for o in current.outputs))
    layout.validate(monitors)
    return layout
