"""Phase 2 owns an exact minimal config root, not arbitrary user Lua."""

import json
from dataclasses import dataclass
from pathlib import Path

from monarch.domain.layout import Layout, ordered, rule
from monarch.errors import MonarchError
from monarch.storage.files import atomic_write, digest, private_dir, read_private

ROOT = (
    b"-- Monarch owned configuration v1. No external rules or side effects.\n"
    b'require("monarch_monitors")\n'
)
HEADER = "-- Monarch monitor data v1: "


def render(layout: Layout) -> bytes:
    Layout.parse(layout.to_dict())
    data = json.dumps(layout.to_dict(), ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    fallback = 'hl.monitor({output="",mode="preferred",scale=1,position="auto"})\n'
    return (
        HEADER + data + "\n" + fallback + "\n".join(rule(o) for o in ordered(layout)) + "\n"
    ).encode()


@dataclass(frozen=True)
class Managed:
    directory: Path

    @property
    def root(self) -> Path:
        return self.directory / "hyprland.lua"

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
        if read_private(self.root) != ROOT:
            raise MonarchError("Configuration root is not the exact Monarch-owned template.")
        content = read_private(self.monitors)
        layout = parse_content(content)
        return layout, content

    def check(self, expected: str) -> None:
        _, content = self.read()
        if digest(content) != expected:
            raise MonarchError("Managed configuration changed during the transaction.")


def parse_content(content: bytes) -> Layout:
    try:
        header = content.decode().splitlines()[0]
        if not header.startswith(HEADER):
            raise ValueError("Missing header")
        layout = Layout.parse(json.loads(header[len(HEADER) :]))
    except (ValueError, UnicodeError, IndexError) as exc:
        raise MonarchError("Invalid managed monitor file.") from exc
    if render(layout) != content:
        raise MonarchError("Managed Lua differs from its data; external edits are preserved.")
    return layout
