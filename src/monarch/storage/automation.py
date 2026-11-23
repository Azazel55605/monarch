"""Private policy, session override controls and explicit user autostart registration."""

import json
import os
import sys
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from monarch.domain.policy import Policy, Rule
from monarch.errors import MonarchError
from monarch.services.state import Paths, SessionLock
from monarch.storage.files import (
    atomic_write,
    digest,
    no_symlinks,
    read_json,
    read_private,
    write_json,
)
from monarch.storage.integration import read_config
from monarch.storage.profiles import ProfileStore, config_home


class PolicyStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory if directory is not None else config_home()
        self.path = self.directory / "automation.json"

    def read(self) -> Policy:
        no_symlinks(self.path)
        return Policy.parse(read_json(self.path)) if self.path.exists() else Policy()

    def _change(self, transform: Callable[[Policy], Policy]) -> None:
        with ProfileStore(self.directory).locked():
            expected = digest(read_private(self.path)) if self.path.exists() else None
            policy = transform(self.read())
            Policy.parse(policy.to_dict())
            atomic_write(
                self.path,
                json.dumps(policy.to_dict(), sort_keys=True).encode() + b"\n",
                expected=expected,
                create=expected is None,
            )

    def write(self, policy: Policy) -> None:
        self._change(lambda previous: policy)

    def enabled(self, enabled: bool) -> None:
        self._change(lambda previous: replace(previous, enabled=enabled))

    def rule(self, rule: Rule | None, identifier: str) -> None:
        self._change(
            lambda previous: replace(
                previous,
                rules=tuple(r for r in previous.rules if r.profile != identifier)
                + ((rule,) if rule else ()),
            )
        )


def control(paths: Paths) -> dict[str, Any]:
    path = paths.runtime / "automation-control.json"
    if not path.exists():
        return {"generation": "initial", "pinned": False}
    data = read_json(path)
    if (
        not isinstance(data, dict)
        or set(data) not in ({"generation", "pinned"}, {"generation", "pinned", "connections"})
        or ("connections" in data and not isinstance(data["connections"], str))
        or not isinstance(data["generation"], str)
        or type(data["pinned"]) is not bool
    ):
        raise MonarchError("Invalid automation session control; automatic writes are paused.")
    return data


def pin(paths: Paths, pinned: bool = True, *, connections: str = "") -> str:
    path = paths.runtime / "automation-control.json"
    lock = SessionLock(paths)
    lock.path = paths.runtime / "automation-control.lock"
    with lock:
        previous = control(paths)
        # Edits must never shorten a deliberately requested session-wide pause.
        if connections and previous["pinned"] and not previous.get("connections"):
            return str(previous["generation"])
        generation = uuid.uuid4().hex
        data = {"generation": generation, "pinned": pinned}
        if pinned and connections:
            data["connections"] = connections
        write_json(path, data)
        return generation


def resume_on_connection_change(paths: Paths, connections: str) -> dict[str, Any]:
    state = control(paths)
    if not state["pinned"] or state.get("connections") in (None, "", connections):
        return state
    path = paths.runtime / "automation-control.json"
    lock = SessionLock(paths)
    lock.path = paths.runtime / "automation-control.lock"
    with lock:
        # Recheck after taking the lock so a concurrent explicit pause wins.
        state = control(paths)
        if state["pinned"] and state.get("connections") not in (None, "", connections):
            state = {"generation": uuid.uuid4().hex, "pinned": False}
            write_json(path, state)
    return state


def profile_snapshot(path: Path) -> bytes:
    no_symlinks(path)
    return read_private(path) if path.exists() else b'{"schema_version":2,"profiles":[]}'


def permit(
    paths: Paths,
    generation: str,
    policy_path: Path,
    policy_digest: str,
    profiles_path: Path,
    profiles_digest: str,
) -> None:
    state = control(paths)
    if state["pinned"] or state["generation"] != generation:
        raise MonarchError("Automatic preview superseded by manual control.")
    if digest(profile_snapshot(profiles_path)) != profiles_digest:
        raise MonarchError("Profile catalog changed during automatic preview.")
    data = read_private(policy_path)
    if digest(data) != policy_digest or not Policy.parse(json.loads(data)).enabled:
        raise MonarchError("Automation policy changed or was disabled.")


MARKER = b"# Monarch owned automation autostart v1\n"


def desktop_entry(executable: str, profiles_directory: Path | None = None) -> bytes:
    if not Path(executable).is_absolute() or any(c in executable for c in "\n\r\x00="):
        raise MonarchError(
            "Autostart requires an absolute Python executable without control characters."
        )
    arguments = [executable, "-m", "monarch", "automation"]
    if profiles_directory is not None:
        arguments += ["--store", str(profiles_directory)]
    arguments += ["run"]
    quoted_arguments = []
    for argument in arguments:
        if any(c in argument for c in "\n\r\x00"):
            raise MonarchError("Autostart arguments cannot contain control characters.")
        quoted = argument.replace("%", "%%")
        for character in ("\\", '"', "`", "$"):
            quoted = quoted.replace(character, "\\" + character)
        quoted_arguments.append('"' + quoted + '"')
    command = " ".join(quoted_arguments).replace("\\", "\\\\")
    return (
        MARKER
        + (
            "[Desktop Entry]\nType=Application\nName=Monarch monitor profiles\n"
            "Comment=Guarded opt-in monitor profile switching\n"
            f"Exec={command}\nTerminal=false\n"
        ).encode()
    )


class Autostart:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory if directory is not None else config_home()
        self.path = self.directory.parent / "autostart" / "monarch-automation.desktop"
        self.receipt = self.directory / "autostart.json"

    def active(self) -> bool:
        if not self.receipt.exists():
            return False
        receipt = read_json(self.receipt)
        if (
            not isinstance(receipt, dict)
            or set(receipt) != {"path", "digest"}
            or receipt["path"] != str(self.path)
        ):
            raise MonarchError("Invalid autostart receipt; existing entry is preserved.")
        return self.path.exists() and digest(read_config(self.path)) == receipt["digest"]

    def set(
        self,
        enabled: bool,
        *,
        executable: str | None = None,
        profiles_directory: Path | None = None,
    ) -> None:
        with ProfileStore(self.directory).locked():
            if enabled:
                data = desktop_entry(executable or sys.executable, profiles_directory)
                if self.path.exists():
                    if self.active() and read_config(self.path) == data:
                        return
                    raise MonarchError("Autostart entry exists or changed; it was not overwritten.")
                no_symlinks(self.path)
                self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if (
                    self.path.parent.stat().st_uid != os.getuid()
                    or self.path.parent.stat().st_mode & 0o022
                ):
                    raise MonarchError(
                        "Autostart directory must be user owned and not group/world writable."
                    )
                fd, temporary = tempfile.mkstemp(prefix=".monarch-", dir=self.path.parent)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.link(temporary, self.path)
                finally:
                    os.unlink(temporary)
                write_json(self.receipt, {"path": str(self.path), "digest": digest(data)})
            elif self.path.exists():
                if not self.active():
                    raise MonarchError(
                        "Autostart entry changed; it was preserved for manual review."
                    )
                self.path.unlink()
                self.receipt.unlink()
            elif self.receipt.exists():
                self.receipt.unlink()
