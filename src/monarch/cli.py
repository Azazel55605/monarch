"""Inspection, Qt editor and guarded profile switching entry points."""

import argparse
import asyncio
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path

from monarch import __version__
from monarch.backends.hyprland.commands import Hyprctl
from monarch.backends.hyprland.events import EventWatcher
from monarch.backends.hyprland.inspector import Inspection, Inspector
from monarch.backends.hyprland.session import Session
from monarch.errors import MonarchError
from monarch.services.automation_cli import add_automation_commands, execute_automation
from monarch.services.cli import add_commands, execute
from monarch.services.diagnostics import collect, save
from monarch.services.profiles import add_profile_commands, execute_profile
from monarch.services.reporting import report as report


def render(inspection: Inspection, *, json_output: bool, identifiers: bool) -> None:
    data = report(inspection, identifiers=identifiers)
    if json_output:
        print(json.dumps(data, indent=None, ensure_ascii=True), flush=True)
        return
    caps = data["capabilities"]
    display_version = json.dumps(caps["version"] or "unknown", ensure_ascii=True)[1:-1]
    print(f"Hyprland {display_version} | provider: {caps['provider']} | read-only")
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
    help_command = commands.add_parser("help", help="Read the bundled quick start or notices")
    help_command.add_argument("--notices", action="store_true", help="Show dependency notices")
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
    diagnose = commands.add_parser(
        "diagnose", help="Collect a redacted read-only JSON support report"
    )
    diagnose.add_argument("--output", type=Path, help="Export privately to a new JSON filename")
    diagnose.add_argument(
        "--directory", type=Path, help="Inspect existing owned/registered storage"
    )
    gui = commands.add_parser("gui", help="Open the Qt monitor editor")
    gui.add_argument("--directory", type=Path, help="Owned or registered monitor storage")
    gui.add_argument("--tray", action="store_true", help="Show an optional profile tray menu")
    add_commands(commands)
    add_profile_commands(commands)
    add_automation_commands(commands)
    args = parser.parse_args(argv)
    if args.command == "help":
        from monarch.resources import text

        print(text("notices.md" if args.notices else "guide.md"))
        return 0
    if (
        args.command == "profile"
        and args.profile_action == "switch"
        and not args.terminal
        and (args.map or args.seconds != 15)
    ):
        parser.error("--map and --seconds require --terminal; GUI switches offer a mapping dialog.")
    if (
        (args.command == "automation" and args.automation_action == "run")
        or args.command == "gui"
        or (args.command == "profile" and args.profile_action == "switch" and not args.terminal)
    ):
        try:
            from monarch.ui.app import launch

            if args.command == "automation":
                Session.from_environment()  # Login entries exit without Qt outside Hyprland.
                return launch(tray=True, background=True, profile_directory=args.store)
            if args.command == "profile":
                # Resolve the profile before opening a window. The worker will
                # resolve it again against live topology before preview.
                from monarch.storage.profiles import ProfileStore

                profile = ProfileStore(
                    args.store.expanduser().absolute() if args.store else None
                ).get(args.name)
                return launch(
                    args.directory,
                    profile=profile.id,
                    persist=args.persist,
                    profile_directory=args.store,
                )
            return launch(args.directory, tray=args.tray)
        except (MonarchError, OSError) as exc:
            print(f"Monarch: {exc}", file=sys.stderr)
            return 2
        except ModuleNotFoundError:
            print(
                "Monarch GUI needs PySide6. Run uv run --extra gui monarch gui.",
                file=sys.stderr,
            )
            return 2
    try:
        if args.command == "diagnose":
            directory = args.directory.expanduser().absolute() if args.directory else None
            data = asyncio.run(collect(directory=directory))
            if args.output:
                save(args.output.expanduser().absolute(), data)
                print("Saved a redacted diagnostic report to a new private file.")
            else:
                print(json.dumps(data, indent=2, ensure_ascii=True, allow_nan=False))
            return 0
        if args.command == "automation":
            return execute_automation(args)
        return asyncio.run(
            inspect_command(args)
            if args.command == "inspect"
            else execute_profile(args)
            if args.command == "profile"
            else execute(args)
        )
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
