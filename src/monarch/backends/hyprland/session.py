"""Resolve one session; never select another compositor implicitly."""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from monarch.errors import MonarchError


@dataclass(frozen=True)
class ConfigLocation:
    path: Path | None
    source: str
    verified: bool = False


@dataclass(frozen=True)
class Session:
    runtime_dir: Path
    signature: str

    @property
    def directory(self) -> Path:
        return self.runtime_dir / "hypr" / self.signature

    @property
    def event_socket(self) -> Path:
        return self.directory / ".socket2.sock"

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> "Session":
        env = os.environ if env is None else env
        signature = env.get("HYPRLAND_INSTANCE_SIGNATURE", "")
        runtime = env.get("XDG_RUNTIME_DIR", "")
        if not signature:
            raise MonarchError("No Hyprland session. Run Monarch from a running Hyprland session.")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", signature) or signature in (".", ".."):
            raise MonarchError("Invalid Hyprland session signature.")
        if not runtime or not Path(runtime).is_absolute():
            raise MonarchError("XDG_RUNTIME_DIR must be an absolute session runtime directory.")
        return cls(Path(runtime), signature)


def config_location(
    session: Session,
    explicit: Path | None = None,
    *,
    proc_root: Path = Path("/proc"),
    resolve_xdg: bool = False,
) -> ConfigLocation:
    """Use the compositor's process metadata, not this CLI's environment guesses.

    A user-selected path is recorded as unverified. We never open/execute Lua.
    Process metadata may be inaccessible in a sandbox: uncertainty stays explicit.
    """
    if explicit is not None:
        return ConfigLocation(explicit.expanduser().absolute(), "user selection")
    try:
        pid = int((session.directory / "hyprland.lock").read_text().splitlines()[0])
        if pid <= 0:
            raise ValueError("Invalid process ID")
        proc = proc_root / str(pid)
        args = (proc / "cmdline").read_bytes().decode().rstrip("\0").split("\0")
        # Restrict metadata interpretation to the actual compositor executable.
        if Path(args[0]).name not in ("Hyprland", "Hyprlandd"):
            return ConfigLocation(None, "compositor process unavailable")
        if "--safe-mode" in args:
            return ConfigLocation(session.directory / "recoverycfg.lua", "safe mode", True)
        for index, arg in enumerate(args):
            if arg in ("--config", "-c") and index + 1 < len(args):
                path = Path(args[index + 1])
                if not path.is_absolute():
                    path = (proc / "cwd").resolve(strict=True) / path
                return ConfigLocation(path, "compositor command line", True)
        environment = dict(
            field.split("=", 1)
            for field in (proc / "environ").read_bytes().decode().split("\0")
            if "=" in field
        )
        if environment.get("HYPRLAND_CONFIG"):
            path = Path(environment["HYPRLAND_CONFIG"])
            if not path.is_absolute():
                path = (proc / "cwd").resolve(strict=True) / path
            return ConfigLocation(path, "compositor environment", True)
        roots = []
        xdg = environment.get("XDG_CONFIG_HOME", "")
        home = environment.get("HOME", "")
        if xdg and Path(xdg).is_absolute():
            roots.append(Path(xdg))
        if home and Path(home).is_absolute():
            roots.append(Path(home) / ".config")
        search: list[Path | None] = list(roots)
        if "XDG_CONFIG_DIRS" in environment:
            for item in environment["XDG_CONFIG_DIRS"].split(":"):
                search.append(Path(item) if item and Path(item).is_absolute() else None)
        search.append(Path("/etc/xdg"))
        program = "hyprlandd" if Path(args[0]).name == "Hyprlandd" else "hyprland"
        if resolve_xdg:
            # Tagged 0.57.2 full-reset repeats the hyprutils search. The guard
            # must use full-reset for this target; ordinary reload caches its path.
            for directory in search:
                if directory is None:
                    return ConfigLocation(
                        None, "Unsupported relative or empty XDG config search entry"
                    )
                candidate = directory / "hypr" / f"{program}.lua"
                if candidate.is_file():
                    return ConfigLocation(candidate, "compositor XDG reload search", True)
        if roots:
            return ConfigLocation(roots[0] / "hypr" / f"{program}.lua", "XDG candidate")
    except (OSError, ValueError, IndexError, UnicodeError):
        pass
    return ConfigLocation(None, "unavailable; select --config explicitly")
