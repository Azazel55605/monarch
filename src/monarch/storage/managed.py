"""Owned monitor data with exact minimal-root or explicitly registered-root verification."""

import json
from dataclasses import dataclass
from pathlib import Path

from monarch.domain.layout import Layout, ordered, rule
from monarch.errors import MonarchError
from monarch.storage.files import atomic_write, digest, private_dir, read_private
from monarch.storage.integration import contract, verify_contract

ROOT = (
    b"-- Monarch owned configuration v1. No external rules or side effects.\n"
    b'require("monarch_monitors")\n'
)
HEADER = "-- Monarch monitor data v1: "


def render(layout: Layout, *, legacy: bool = False) -> bytes:
    Layout.parse(layout.to_dict())
    value = layout.to_dict()
    if legacy:
        if any(o.vrr for o in layout.outputs):
            raise MonarchError("Legacy monitor data cannot represent VRR On.")
        value["schema_version"] = 1
        for output in value["outputs"]:
            output.pop("vrr")
    data = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    fallback = 'hl.monitor({output="",mode="preferred",scale=1,position="auto"})\n'
    return (
        HEADER
        + data
        + "\n"
        + fallback
        + "\n".join(rule(o, legacy=legacy) for o in ordered(layout))
        + "\n"
    ).encode()


@dataclass(frozen=True)
class Managed:
    directory: Path

    @property
    def root(self) -> Path:
        registered = contract(self.directory)
        return Path(registered["root"]) if registered else self.directory / "hyprland.lua"

    @property
    def monitors(self) -> Path:
        return self.directory / "monarch_monitors.lua"

    def create(self, layout: Layout) -> None:
        # New dedicated directory only: never adopt or rewrite an existing root.
        if self.directory.exists():
            raise MonarchError("Choose a new directory for the owned configuration.")
        private_dir(self.directory)
        atomic_write(self.monitors, render(layout), create=True)
        atomic_write(self.root, ROOT, create=True)

    def read(self) -> tuple[Layout, bytes]:
        private_dir(self.directory)
        self.verify_root()
        content = read_private(self.monitors)
        layout = parse_content(content)
        return layout, content

    def verify_root(self) -> None:
        if contract(self.directory) is not None:
            verify_contract(self.directory)
        elif read_private(self.root) != ROOT:
            raise MonarchError("Configuration root is not the exact Monarch-owned template.")

    def root_fingerprint(self) -> str:
        self.verify_root()
        registered = contract(self.directory)
        if registered is not None:
            import json

            return digest(json.dumps(registered, sort_keys=True).encode())
        return digest(ROOT)

    def check(self, expected: str) -> None:
        _, content = self.read()
        if digest(content) != expected:
            raise MonarchError("Managed configuration changed during the transaction.")


def parse_content(content: bytes) -> Layout:
    try:
        header = content.decode().splitlines()[0]
        if not header.startswith(HEADER):
            raise ValueError("Missing header")
        value = json.loads(header[len(HEADER) :])
        layout = Layout.parse(value)
    except (ValueError, UnicodeError, IndexError) as exc:
        raise MonarchError("Invalid managed monitor file.") from exc
    if render(layout, legacy=value["schema_version"] == 1) != content:
        raise MonarchError("Managed Lua differs from its data; external edits are preserved.")
    return layout
