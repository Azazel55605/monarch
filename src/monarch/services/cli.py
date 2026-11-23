"""Phase 2 CLI entry points use the same independent guard as future GUI clients."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from monarch.backends.hyprland.commands import Hyprctl
from monarch.backends.hyprland.session import Session
from monarch.domain.layout import Layout
from monarch.domain.monitors import parse_monitors
from monarch.errors import MonarchError
from monarch.services.coordinator import Coordinator
from monarch.services.state import TERMINAL
from monarch.storage.files import read_json, write_json
from monarch.storage.managed import Managed


def add_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    layout = commands.add_parser("layout", help="Capture or validate a data-only layout")
    layouts = layout.add_subparsers(dest="layout_action", required=True)
    capture = layouts.add_parser("capture", help="Capture identities and current settings")
    capture.add_argument("--output", type=Path, help="Private file; otherwise print JSON to stdout")
    validate = layouts.add_parser("validate")
    validate.add_argument("file", type=Path)
    managed = commands.add_parser("managed", help="Create an isolated owned configuration")
    managed_actions = managed.add_subparsers(dest="managed_action", required=True)
    create = managed_actions.add_parser("create")
    create.add_argument("--directory", required=True, type=Path)
    create.add_argument("--layout", required=True, type=Path)
    preview = commands.add_parser(
        "preview", help="Guarded preview in a verified owned session only"
    )
    preview.add_argument("file", type=Path)
    preview.add_argument("--directory", required=True, type=Path)
    preview.add_argument("--seconds", default=15, type=float)
    preview.add_argument("--persist", action="store_true", help="Persist only if Keep is confirmed")
    commands.add_parser("recover", help="Recover an unfinished transaction in this same session")
    transaction = commands.add_parser("transaction", help="Inspect the recovery journal")
    transaction.add_argument("transaction_action", choices=["status"])


def load_layout(path: Path) -> Layout:
    return Layout.parse(read_json(path.expanduser().absolute()))


async def terminal_line() -> str:
    loop = asyncio.get_running_loop()
    result: asyncio.Future[str] = loop.create_future()

    def ready() -> None:
        if not result.done():
            result.set_result(sys.stdin.readline().strip())

    descriptor = sys.stdin.fileno()
    loop.add_reader(descriptor, ready)
    try:
        return await result
    finally:
        loop.remove_reader(descriptor)


async def execute(args: argparse.Namespace) -> int:
    if args.command == "managed":
        store = Managed(args.directory.expanduser().absolute())
        store.create(load_layout(args.layout))
        print("Created a dedicated owned config. No active configuration was changed.")
        print(
            "This root is for an explicitly started isolated session; "
            "desktop integration is Phase 3."
        )
        return 0
    session = Session.from_environment()
    if args.command == "layout":
        monitors = parse_monitors(await Hyprctl(session).read("monitors", "all"))
        if args.layout_action == "capture":
            layout = Layout.capture(monitors)
            if args.output:
                write_json(args.output.expanduser().absolute(), layout.to_dict(), create=True)
                print("Captured a private layout file containing monitor identities.")
            else:
                print(json.dumps(layout.to_dict(), indent=2))
        else:
            load_layout(args.file).validate(monitors)
            print("Layout is valid for the currently connected outputs.")
        return 0
    coordinator = Coordinator(session)
    if args.command == "transaction":
        status = coordinator.paths.status()
        print(
            json.dumps(
                {
                    "id": status.get("id") if status else None,
                    "status": status.get("status") if status else "none",
                    "reason": status.get("reason") if status else "",
                    "recovery_required": bool(status and status.get("status") not in TERMINAL),
                    "other_sessions_unfinished": coordinator.paths.foreign_unfinished(),
                }
            )
        )
        return 0
    if args.command == "recover":
        result = await coordinator.recover()
    else:
        handle = await coordinator.preview(
            Managed(args.directory.expanduser().absolute()),
            load_layout(args.file),
            seconds=args.seconds,
        )
        try:
            print(
                "Preview active. Type keep to confirm, or revert to restore. "
                "The independent guard enforces the deadline.",
                flush=True,
            )
            if not sys.stdin.isatty():
                print("No interactive terminal: preview will expire and revert.", flush=True)
                result = await handle.wait()
            else:
                waiting = asyncio.create_task(handle.wait())
                input_task = asyncio.create_task(terminal_line())
                try:
                    done, _ = await asyncio.wait(
                        [waiting, input_task], return_when=asyncio.FIRST_COMPLETED
                    )
                    if waiting in done:
                        result = await waiting
                    else:
                        result = await handle.decide(
                            keep=(await input_task) == "keep", persist=args.persist
                        )
                finally:
                    input_task.cancel()
                    await asyncio.gather(input_task, return_exceptions=True)
        finally:
            if handle.process.stdin:
                handle.process.stdin.close()
    print(json.dumps(result))
    if result["state"] not in ("kept", "reverted", "degraded"):
        raise MonarchError(
            "Recovery is unfinished. Inspect transaction status; do not delete its journal."
        )
    return 0
