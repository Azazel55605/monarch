"""Inspection and guarded CLI previews; the Qt editor is a later phase."""

import argparse
import asyncio
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from monarch import __version__
from monarch.backends.hyprland.commands import Hyprctl
from monarch.backends.hyprland.events import EventWatcher
from monarch.backends.hyprland.inspector import Inspection, Inspector
from monarch.backends.hyprland.session import Session
from monarch.errors import MonarchError
from monarch.services.cli import add_commands, execute


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
                    monitor.mirror_of
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
                "warnings": monitor.warnings,
            }
        )
    capabilities = asdict(inspection.capabilities)
    # Unknown backend strings are not trusted free-form report content.
    if not identifiers and capabilities["backend"] not in ("drm", "wayland", "unknown"):
        capabilities["backend"] = "unknown"
    if not identifiers and capabilities["version"] is not None:
        import re

        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][\w.-]+)?", capabilities["version"]):
            capabilities["version"] = "unknown"
    return {
        "schema_version": 1,
        "capabilities": capabilities,
        "config": {
            "path": str(inspection.config.path)
            if identifiers and inspection.config.path
            else "[redacted]"
            if inspection.config.path
            else None,
            "source": inspection.config.source,
            "verified": inspection.config.verified,
        },
        "monitors": monitors,
        "diagnostics": inspection.diagnostics,
    }


def render(inspection: Inspection, *, json_output: bool, identifiers: bool) -> None:
    data = report(inspection, identifiers=identifiers)
    if json_output:
        print(json.dumps(data, indent=None, ensure_ascii=True), flush=True)
        return
    caps = data["capabilities"]
    print(f"Hyprland {caps['version'] or 'unknown'} | provider: {caps['provider']} | read-only")
    for monitor in data["monitors"]:
        state = {True: "disabled", False: "enabled", None: "unknown"}[monitor["disabled"]]
        # Escape control sequences even with --show-identifiers.
        output = json.dumps(monitor["output"], ensure_ascii=True)
        print(
            f"  {output}: {monitor['width']}x{monitor['height']} "
            f"@ {monitor['refresh_hz']} Hz | scale {monitor['scale']} | {state}"
        )
        for warning in monitor["warnings"]:
            print(f"    {warning}")
    for message in data["diagnostics"]:
        print(f"  Note: {message}")
    print("  Writes disabled: " + caps["mutation_reason"], flush=True)


async def inspect_command(args: argparse.Namespace) -> int:
    session = Session.from_environment()
    inspector = Inspector(Hyprctl(session, timeout=args.timeout), args.config)
    render(await inspector.inspect(), json_output=args.json, identifiers=args.show_identifiers)
    if args.watch:
        async for reason in EventWatcher(session).invalidations():
            try:
                render(
                    await inspector.inspect(),
                    json_output=args.json,
                    identifiers=args.show_identifiers,
                )
            except MonarchError as exc:
                print(f"Monarch: {reason}: {exc}", file=sys.stderr, flush=True)
    return 0


def positive_timeout(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Timeout must be a number") from exc
    if not math.isfinite(number) or not 0 < number <= 60:
        raise argparse.ArgumentTypeError("Timeout must be between 0 and 60 seconds")
    return number


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Monarch: Hyprland monitor inspection and guarded previews"
    )
    parser.add_argument("--version", action="version", version=f"Monarch {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Inspect connected and disabled outputs")
    inspect.add_argument(
        "--json", action="store_true", help="JSON; one object per line with --watch"
    )
    inspect.add_argument(
        "--watch", action="store_true", help="Refresh on topology events; Ctrl+C exits"
    )
    inspect.add_argument(
        "--show-identifiers",
        action="store_true",
        help="Include output names, monitor identities, and config path",
    )
    inspect.add_argument(
        "--config", type=Path, help="Select config path without opening/executing it"
    )
    inspect.add_argument(
        "--timeout",
        type=positive_timeout,
        default=3.0,
        help="Per-command timeout in seconds (default: 3)",
    )
    gui = commands.add_parser("gui", help="Open the Qt monitor editor")
    gui.add_argument("--directory", type=Path, help="Owned or registered monitor storage")
    add_commands(commands)
    args = parser.parse_args(argv)
    if args.command == "gui":
        try:
            from monarch.ui.app import launch

            return launch(args.directory)
        except ModuleNotFoundError:
            print(
                "Monarch GUI needs PySide6. Run uv run --extra gui monarch gui.",
                file=sys.stderr,
            )
            return 2
    try:
        return asyncio.run(inspect_command(args) if args.command == "inspect" else execute(args))
    except OSError:
        print("Monarch: storage or session access failed; check permissions.", file=sys.stderr)
        return 2
    except MonarchError as exc:
        print(f"Monarch: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0
