"""Profile CLI; switches resolve afresh and use the shared independent guard."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from monarch.backends.hyprland.commands import Hyprctl
from monarch.backends.hyprland.session import Session
from monarch.domain.layout import Layout
from monarch.domain.monitors import parse_monitors
from monarch.domain.profiles import resolve
from monarch.services.coordinator import Coordinator
from monarch.storage.managed import Managed
from monarch.storage.profiles import ProfileStore


def add_profile_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser("profile", help="Saved profiles and guarded quick switching")
    parser.add_argument(
        "--store", type=Path, help="Private profile directory (default: XDG config)"
    )
    actions = parser.add_subparsers(dest="profile_action", required=True)
    actions.add_parser("list")
    show = actions.add_parser("show", help="Print profile including monitor identities")
    show.add_argument("name")
    capture = actions.add_parser("capture", help="Save the observed layout without applying it")
    capture.add_argument(
        "--vrr-on",
        action="append",
        default=[],
        metavar="OUTPUT",
        help="Explicitly record an active output as VRR On; conditional policy is not inferred",
    )
    capture.add_argument("name")
    save = actions.add_parser("save", help="Create a profile from a private layout JSON")
    save.add_argument("name")
    save.add_argument("file", type=Path)
    update = actions.add_parser("update", help="Replace a saved profile from layout JSON")
    update.add_argument("name")
    update.add_argument("file", type=Path)
    rename = actions.add_parser("rename")
    rename.add_argument("name")
    rename.add_argument("new_name")
    delete = actions.add_parser("delete")
    delete.add_argument("name")
    imp = actions.add_parser("import", help="Import data-only JSON; reject name conflicts")
    imp.add_argument("file", type=Path)
    export = actions.add_parser("export", help="Export identities privately to a new filename")
    export.add_argument("file", type=Path)
    export.add_argument("--name")
    switch = actions.add_parser("switch", help="Open GUI confirmation; suitable for keybindings")
    switch.add_argument("name")
    switch.add_argument("--directory", type=Path, help="Owned/registered monitor storage")
    switch.add_argument("--persist", action="store_true", help="Save on login only after Keep")
    switch.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="SAVED=CONNECTED",
        help="Explicit one-to-one mapping for ambiguous identities",
    )
    switch.add_argument("--terminal", action="store_true", help="Confirm in this terminal instead")
    switch.add_argument("--seconds", type=float, default=15)


async def execute_profile(args: argparse.Namespace) -> int:
    from monarch.services.cli import confirm_preview, load_layout

    store = ProfileStore(args.store.expanduser().absolute() if args.store else None)
    action = args.profile_action
    if action == "list":
        print(json.dumps([{"id": p.id, "name": p.name} for p in store.list()]))
    elif action == "show":
        print(json.dumps(store.get(args.name).to_dict(), indent=2))
    elif action == "save":
        store.save(args.name, load_layout(args.file))
    elif action == "update":
        profile = store.get(args.name)
        store.save(profile.name, load_layout(args.file), identifier=profile.id)
    elif action == "capture":
        session = Session.from_environment()
        monitors = parse_monitors(await Hyprctl(session).read("monitors", "all"))
        store.save(
            args.name, Layout.capture(monitors, vrr_policies={name: 1 for name in args.vrr_on})
        )
    elif action == "rename":
        profile = store.get(args.name)
        store.rename(profile.id, args.new_name)
    elif action == "delete":
        store.delete(store.get(args.name).id)
    elif action == "import":
        store.import_file(args.file.expanduser().absolute())
    elif action == "export":
        key = store.get(args.name).id if args.name else None
        store.export_file(args.file.expanduser().absolute(), key)
    elif action == "switch":
        import sys

        from monarch.backends.hyprland.inspector import Inspector
        from monarch.errors import MonarchError

        if not sys.stdin.isatty():
            raise MonarchError(
                "--terminal switching requires an interactive terminal; use the GUI instead."
            )
        session = Session.from_environment()
        inspection = await Inspector(Hyprctl(session)).inspect()
        layout = resolve(store.get(args.name), inspection.monitors, parse_bindings(args.map))
        directory = args.directory
        if directory is None and inspection.config.path:
            candidate = inspection.config.path.parent / "monarch"
            directory = (
                candidate
                if (candidate / "integration.json").is_file()
                else inspection.config.path.parent
            )
        if directory is None:
            raise MonarchError("Select a verified managed directory before switching.")
        handle = await Coordinator(session).preview(
            Managed(directory.expanduser().absolute()), layout, seconds=args.seconds
        )
        result = await confirm_preview(handle, persist=args.persist)
        print(json.dumps(result))
        return 0 if result["state"] == "kept" else 1
    return 0


def parse_bindings(values: list[str]) -> dict[str, str]:
    from monarch.errors import MonarchError

    bindings: dict[str, str] = {}
    for value in values:
        before, separator, after = value.partition("=")
        if not separator or not before or not after or before in bindings:
            raise MonarchError("Use each --map SAVED=CONNECTED exactly once.")
        bindings[before] = after
    return bindings
