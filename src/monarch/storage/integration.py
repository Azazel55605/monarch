"""Explicit registration of a desktop root and its operator-declared dependencies."""

import difflib
import os
import stat
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from monarch.domain.layout import Layout
from monarch.errors import MonarchError
from monarch.storage.files import (
    MAX_FILE,
    atomic_write,
    digest,
    no_symlinks,
    read_json,
    read_private,
    write_json,
)

BLOCK = (
    b'\n-- BEGIN MONARCH MONITORS\nrequire("monarch.monarch_monitors")\n-- END MONARCH MONITORS\n'
)


def read_config(path: Path) -> bytes:
    no_symlinks(path)
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink not in (0, 1)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o022
                or info.st_size > MAX_FILE
            ):
                raise MonarchError(
                    "Config files must be user-owned regular files, not group/world writable."
                )
            data = stream.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                raise MonarchError("Config file is too large.")
            return data
    except OSError as exc:
        raise MonarchError("Configuration is unavailable; check permissions.") from exc


def replace_config(path: Path, data: bytes, expected: str) -> None:
    """Preserve mode and unrelated bytes in a normal (not necessarily private) root."""
    if digest(read_config(path)) != expected:
        raise MonarchError(
            "Configuration changed since the integration preview. Nothing was replaced."
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    fd, temporary = tempfile.mkstemp(prefix=".monarch-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        if digest(read_config(path)) != expected:
            raise MonarchError(
                "Configuration changed during integration; external edits are preserved."
            )
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass(frozen=True)
class IntegrationPlan:
    root: Path
    original: bytes
    dependencies: tuple[tuple[Path, str], ...]
    previous_contract: str | None = None
    previous_monitors_digest: str | None = None
    baseline_preview: Layout | None = None

    @classmethod
    def prepare(cls, root: Path, dependencies: tuple[Path, ...] = ()) -> "IntegrationPlan":
        original = read_config(root)
        directory = root.parent / "monarch"
        previous = contract(directory) if directory.exists() else None
        if b"BEGIN MONARCH MONITORS" in original or b"monarch.monarch_monitors" in original:
            if previous is None or previous["root"] != str(root) or not original.endswith(BLOCK):
                raise MonarchError(
                    "Existing include is not a complete registered block at the end of this root."
                )
        elif previous is not None:
            raise MonarchError("The registered include was removed; restore or review it manually.")
        if len(dependencies) > 128:
            raise MonarchError("Too many configuration dependencies.")
        if any(path == root for path in dependencies) or len(set(dependencies)) != len(
            dependencies
        ):
            raise MonarchError("Dependency list contains the root or duplicate paths.")
        pins = tuple((path, digest(read_config(path))) for path in dependencies)
        if directory.exists() and previous is None:
            raise MonarchError(
                "The config directory already contains unregistered monarch storage."
            )
        previous_hash = digest(read_private(directory / "integration.json")) if previous else None
        return cls(
            root,
            original,
            pins,
            previous_hash,
            digest(read_private(directory / "monarch_monitors.lua")) if previous else None,
        )

    @property
    def installed(self) -> bytes:
        return self.original if self.previous_contract else self.original + BLOCK

    def diff(self) -> str:
        return "".join(
            difflib.unified_diff(
                self.original.decode("utf-8").splitlines(True),
                self.installed.decode("utf-8").splitlines(True),
                fromfile=str(self.root),
                tofile=str(self.root),
            )
        )

    def install(self, layout: Layout) -> Path:
        from monarch.storage.managed import Managed, render

        if digest(read_config(self.root)) != digest(self.original):
            raise MonarchError("Config changed after preview; prepare integration again.")
        for path, expected in self.dependencies:
            if digest(read_config(path)) != expected:
                raise MonarchError("A declared dependency changed after preview.")
        store = Managed(self.root.parent / "monarch")
        if self.previous_contract:
            if (
                digest(read_private(store.directory / "integration.json")) != self.previous_contract
                or digest(read_private(store.monitors)) != self.previous_monitors_digest
            ):
                raise MonarchError(
                    "Integration or monitor data changed after preview; prepare it again."
                )
        if self.previous_contract:
            from monarch.storage.managed import parse_content

            previous_monitors = read_private(store.monitors)
            parse_content(previous_monitors)
            atomic_write(
                store.directory / f"root-reviewed-{uuid.uuid4().hex}.lua",
                self.original,
                create=True,
            )
        else:
            store.create(layout)
            atomic_write(
                store.directory / "root-before-integration.lua", self.original, create=True
            )
        contract = {
            "schema_version": 1,
            "root": str(self.root),
            "root_digest": digest(self.installed),
            "dependencies": [{"path": str(p), "digest": d} for p, d in self.dependencies],
        }
        # Registration is durable before the root is modified. Interrupted installs
        # fail closed because the registered root hash won't match yet.
        if self.previous_contract:
            import json

            atomic_write(
                store.directory / f"monitors-reviewed-{uuid.uuid4().hex}.lua",
                previous_monitors,
                create=True,
            )
            atomic_write(store.monitors, render(layout), expected=digest(previous_monitors))
            atomic_write(
                store.directory / "integration.json",
                json.dumps(contract, sort_keys=True).encode() + b"\n",
                expected=self.previous_contract,
            )
        else:
            write_json(store.directory / "integration.json", contract, create=True)
            replace_config(self.root, self.installed, digest(self.original))
        return store.directory


def contract(directory: Path) -> dict[str, Any] | None:
    path = directory / "integration.json"
    if not path.exists():
        return None
    value = read_json(path)
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "root", "root_digest", "dependencies"}
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or not isinstance(value["root"], str)
        or not isinstance(value["root_digest"], str)
        or not isinstance(value["dependencies"], list)
        or len(value["dependencies"]) > 128
    ):
        raise MonarchError("Invalid desktop integration contract.")
    return value


def verify_contract(directory: Path) -> None:
    value = contract(directory)
    if value is None:
        raise MonarchError("Desktop integration is not registered.")
    root = Path(value["root"])
    if root.parent / "monarch" != directory:
        raise MonarchError("Integration path does not match its registered root.")
    content = read_config(root)
    if digest(content) != value["root_digest"] or not content.endswith(BLOCK):
        raise MonarchError(
            "Desktop root changed; review integration before applying or recovering."
        )
    for entry in value["dependencies"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"path", "digest"}
            or not isinstance(entry["path"], str)
            or not isinstance(entry["digest"], str)
        ):
            raise MonarchError("Invalid declared config dependency.")
        if digest(read_config(Path(entry["path"]))) != entry["digest"]:
            raise MonarchError(
                "A registered config dependency changed; external edits are preserved."
            )
