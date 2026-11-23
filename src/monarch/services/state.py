"""Session-scoped locks and durable recovery journals."""

import fcntl
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from monarch.backends.hyprland.session import Session
from monarch.errors import MonarchError
from monarch.storage.files import digest, no_symlinks, private_dir, read_json

TERMINAL = {"kept", "reverted", "degraded"}


def session_token(session: Session) -> str:
    try:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        info = (session.directory / ".socket.sock").stat()
        return digest(f"{boot}:{session.signature}:{info.st_dev}:{info.st_ino}".encode())
    except OSError as exc:
        raise MonarchError(
            "Original compositor session is unavailable; recovery is retained."
        ) from exc


@dataclass(frozen=True)
class Paths:
    runtime: Path
    state: Path

    @classmethod
    def for_session(
        cls, session: Session, state_home: Path | None = None, *, create: bool = True
    ) -> "Paths":
        key = digest((str(session.runtime_dir) + "/" + session.signature).encode())[:24]
        if state_home is None:
            state_home = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        paths = cls(session.runtime_dir / "monarch" / key, state_home / "monarch" / key)
        if create:
            private_dir(paths.runtime)
            private_dir(paths.state)
        return paths

    @property
    def journal(self) -> Path:
        return self.state / "active.json"

    @property
    def confirmed(self) -> Path:
        return self.state / "confirmed.json"

    def status(self) -> dict[str, Any] | None:
        if not self.journal.exists():
            return None
        data = read_json(self.journal)
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise MonarchError("Unsupported recovery journal; do not discard it.")
        return data

    def foreign_unfinished(self, root: Path | None = None) -> int:
        count = 0
        for path in self.state.parent.glob("*/active.json"):
            if path == self.journal:
                continue
            data = read_json(path)
            if not isinstance(data, dict) or data.get("schema_version") != 1:
                raise MonarchError("An unknown recovery journal needs manual review.")
            if data.get("status") not in TERMINAL and (
                root is None or data.get("root") == str(root)
            ):
                count += 1
        return count


class SessionLock:
    def __init__(self, paths: Paths) -> None:
        self.path = paths.runtime / "transaction.lock"
        self.fd: int | None = None

    def __enter__(self) -> "SessionLock":
        no_symlinks(self.path)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if os.fstat(fd).st_uid != os.getuid():
                raise MonarchError("Session lock is not owned by this user.")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise MonarchError("Another monitor transaction or recovery is active.") from exc
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd
        return self

    def __exit__(self, *args: object) -> None:
        assert self.fd is not None
        os.close(self.fd)
        self.fd = None
