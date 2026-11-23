import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from monarch.errors import MonarchError

MAX_FILE = 1024 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def no_symlinks(path: Path) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise MonarchError("Storage paths must be absolute and normalized.")
    for item in (path, *path.parents):
        if item.is_symlink():
            raise MonarchError("Symlinks are not allowed in managed storage paths.")


def private_dir(path: Path) -> None:
    no_symlinks(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise MonarchError("Managed storage directory must be private and owned by this user.")


def read_private(path: Path) -> bytes:
    no_symlinks(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink not in (0, 1)
                or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_size > MAX_FILE
            ):
                raise MonarchError("Managed files must be private regular files with one link.")
            return stream.read(MAX_FILE + 1)
    except OSError as exc:
        raise MonarchError("Cannot read managed storage; check ownership and permissions.") from exc


def atomic_write(
    path: Path, data: bytes, *, expected: str | None = None, create: bool = False
) -> None:
    private_dir(path.parent)
    no_symlinks(path)
    if len(data) > MAX_FILE:
        raise MonarchError("Managed storage size limit exceeded.")
    if expected is not None and digest(read_private(path)) != expected:
        raise MonarchError("Managed file changed externally; refusing to overwrite it.")
    if create and path.exists():
        raise MonarchError("Refusing to replace an existing file.")
    fd, temporary = tempfile.mkstemp(prefix=".monarch-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if create:
            os.link(temporary, path)  # Exclusive creation, no clobber race.
            os.unlink(temporary)
        else:
            if expected is not None and digest(read_private(path)) != expected:
                raise MonarchError("Managed file changed while writing; edit preserved.")
            os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path: Path) -> Any:
    try:
        return json.loads(read_private(path))
    except (ValueError, UnicodeError) as exc:
        raise MonarchError("Invalid managed JSON data.") from exc


def write_json(path: Path, data: object, *, create: bool = False) -> None:
    atomic_write(
        path, json.dumps(data, allow_nan=False, sort_keys=True).encode() + b"\n", create=create
    )
