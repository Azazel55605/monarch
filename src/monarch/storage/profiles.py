"""Locked, versioned private catalog; imports are data, never executable rules."""

import fcntl
import json
import os
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from monarch.domain.layout import Layout
from monarch.domain.profiles import Profile, profile_name
from monarch.errors import MonarchError
from monarch.storage.files import (
    MAX_FILE,
    atomic_write,
    digest,
    no_symlinks,
    private_dir,
    read_json,
    read_private,
)
from monarch.storage.integration import read_config


def config_home(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    value = env.get("XDG_CONFIG_HOME") or str(Path(env.get("HOME", str(Path.home()))) / ".config")
    path = Path(value)
    if not path.is_absolute():
        raise MonarchError("XDG_CONFIG_HOME must be absolute.")
    return path / "monarch"


def decode(value: object) -> tuple[Profile, ...]:
    if not isinstance(value, dict) or set(value) != {"schema_version", "profiles"}:
        raise MonarchError("Invalid profile catalog.")
    version = value["schema_version"]
    if type(version) is not int or version not in (1, 2):
        raise MonarchError("Unsupported profile schema; this file was not changed.")
    rows = value["profiles"]
    if not isinstance(rows, list) or len(rows) > 128:
        raise MonarchError("A catalog supports at most 128 profiles.")
    profiles = []
    for row in rows:
        keys = {"name", "layout"} if version == 1 else {"id", "name", "layout"}
        if not isinstance(row, dict) or set(row) != keys:
            raise MonarchError("Invalid profile fields.")
        name = profile_name(row["name"])
        identifier = row.get("id") if version == 2 else uuid.uuid5(uuid.NAMESPACE_URL, name).hex
        if not isinstance(identifier, str) or len(identifier) != 32:
            raise MonarchError("Invalid profile identifier.")
        try:
            if uuid.UUID(hex=identifier).hex != identifier:
                raise ValueError
        except ValueError as exc:
            raise MonarchError("Invalid profile identifier.") from exc
        profiles.append(Profile(identifier, name, Layout.parse(row["layout"])))
    if len({p.id for p in profiles}) != len(profiles) or len(
        {p.name.casefold() for p in profiles}
    ) != len(profiles):
        raise MonarchError("Duplicate profile names or identifiers.")
    return tuple(profiles)


def encode(profiles: tuple[Profile, ...]) -> bytes:
    value = {"schema_version": 2, "profiles": [p.to_dict() for p in profiles]}
    decode(value)
    return json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2).encode() + b"\n"


class ProfileStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory if directory is not None else config_home()
        self.path = self.directory / "profiles.json"

    @contextmanager
    def locked(self) -> Iterator[str | None]:
        private_dir(self.directory)
        path = self.directory / "profiles.lock"
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            read_private(path)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield digest(read_private(self.path)) if self.path.exists() else None
        except BlockingIOError as exc:
            raise MonarchError(
                "Another client is editing profiles; refresh and try again."
            ) from exc
        finally:
            os.close(descriptor)

    def list(self) -> tuple[Profile, ...]:
        no_symlinks(self.path)
        return decode(read_json(self.path)) if self.path.exists() else ()

    def get(self, key: str) -> Profile:
        matches = [p for p in self.list() if p.id == key or p.name.casefold() == key.casefold()]
        if len(matches) != 1:
            raise MonarchError("Profile was not found or its name conflicts with an identifier.")
        return matches[0]

    def _write(self, profiles: tuple[Profile, ...], *, expected: str | None) -> None:
        data = encode(profiles)
        if self.path.exists():
            previous = read_private(self.path)
            if digest(previous) != expected:
                raise MonarchError("Profile catalog changed externally; refresh before editing.")
            if json.loads(previous)["schema_version"] == 1:
                backup = self.directory / f"schema-1-backup-{digest(previous)}.json"
                if not backup.exists():
                    atomic_write(backup, previous, create=True)
                elif read_private(backup) != previous:
                    raise MonarchError("Migration backup conflicts with existing data.")
        atomic_write(self.path, data, expected=expected, create=expected is None)

    def save(self, name: str, layout: Layout, *, identifier: str | None = None) -> Profile:
        name = profile_name(name)
        Layout.parse(layout.to_dict())
        with self.locked() as expected:
            profiles = self.list()
            if identifier is not None and not any(p.id == identifier for p in profiles):
                raise MonarchError("Profile changed or was deleted; refresh before saving.")
            profile = Profile(identifier or uuid.uuid4().hex, name, layout)
            updated = tuple(p for p in profiles if p.id != profile.id) + (profile,)
            self._write(updated, expected=expected)
            return profile

    def rename(self, identifier: str, name: str) -> None:
        name = profile_name(name)
        with self.locked() as expected:
            profiles = self.list()
            if not any(p.id == identifier for p in profiles):
                raise MonarchError("Profile no longer exists.")
            updated = tuple(
                Profile(p.id, name, p.layout) if p.id == identifier else p for p in profiles
            )
            self._write(updated, expected=expected)

    def delete(self, identifier: str) -> None:
        with self.locked() as expected:
            profiles = self.list()
            if not any(p.id == identifier for p in profiles):
                raise MonarchError("Profile no longer exists.")
            self._write(tuple(p for p in profiles if p.id != identifier), expected=expected)

    def import_file(self, path: Path) -> tuple[Profile, ...]:
        try:
            imported = decode(json.loads(read_config(path)))
        except (ValueError, UnicodeError) as exc:
            raise MonarchError("Invalid imported profile JSON.") from exc
        with self.locked() as expected:
            current = self.list()
            names = {p.name.casefold() for p in current}
            if any(p.name.casefold() in names for p in imported):
                raise MonarchError("An imported name already exists; rename it before importing.")
            # Imported identifiers cannot replace local entries, even for exported copies.
            added = tuple(Profile(uuid.uuid4().hex, p.name, p.layout) for p in imported)
            self._write(current + added, expected=expected)
        return added

    def export_file(self, path: Path, identifier: str | None = None) -> None:
        profiles = (self.get(identifier),) if identifier else self.list()
        data = encode(profiles)
        if len(data) > MAX_FILE:
            raise MonarchError("Export exceeds the file size limit.")
        no_symlinks(path)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as exc:
            raise MonarchError("Export target exists; choose a new filename.") from exc
