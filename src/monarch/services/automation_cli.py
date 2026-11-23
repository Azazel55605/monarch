"""Explicit opt-in controls; the runner always retains a visible Qt confirmation surface."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from monarch.backends.hyprland.session import Session
from monarch.domain.policy import Rule
from monarch.services.state import Paths
from monarch.storage.automation import Autostart, PolicyStore, control, pin
from monarch.storage.files import read_json
from monarch.storage.profiles import ProfileStore


def add_automation_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser("automation", help="Opt-in topology policy and session overrides")
    parser.add_argument("--store", type=Path, help="Private profile/policy directory")
    actions = parser.add_subparsers(dest="automation_action", required=True)
    for action in ("status", "enable", "disable", "pin", "resume", "run"):
        actions.add_parser(action)
    rule = actions.add_parser("set-rule")
    rule.add_argument("profile")
    rule.add_argument("--match", choices=["exact", "subset"], default="exact")
    rule.add_argument("--priority", type=int, default=0)
    rule.add_argument(
        "--bind-connectors",
        action="store_true",
        help="Explicitly bind displays to saved ports; requires fixed cabling",
    )
    remove = actions.add_parser("remove-rule")
    remove.add_argument("profile")
    startup = actions.add_parser("autostart")
    startup.add_argument("startup_action", choices=["enable", "disable", "status"])


def execute_automation(args: argparse.Namespace) -> int:
    directory = args.store.expanduser().absolute() if args.store else None
    store = PolicyStore(directory)
    action = args.automation_action
    if action == "enable":
        store.enabled(True)
    elif action == "disable":
        store.enabled(False)
    elif action in {"pin", "resume"}:
        pin(Paths.for_session(Session.from_environment()), action == "pin")
    elif action in {"set-rule", "remove-rule"}:
        profile = ProfileStore(directory).get(args.profile)
        rule = (
            Rule(profile.id, args.match, args.priority, args.bind_connectors)
            if action == "set-rule"
            else None
        )
        if rule:
            Rule.parse(rule.to_dict())
        store.rule(rule, profile.id)
    elif action == "autostart":
        startup = Autostart()
        if args.startup_action != "status":
            startup.set(args.startup_action == "enable", profiles_directory=directory)
        print(json.dumps({"autostart": startup.active()}))
    elif action == "status":
        data = {
            "policy": store.read().to_dict(),
            "autostart": Autostart().active(),
            "runner": None,
            "session": None,
        }
        from monarch.errors import MonarchError

        try:
            paths = Paths.for_session(Session.from_environment())
            data["session"] = control(paths)
            path = paths.runtime / "automation-status.json"
            if path.exists():
                status = read_json(path)
                status["running"] = (
                    bool(status.get("owner")) and time.monotonic() - status["heartbeat"] < 5
                )
                data["runner"] = status
        except MonarchError:
            pass
        print(json.dumps(data))
    return 0
