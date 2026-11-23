"""Read-only, redacted support snapshots. No Lua, EDID, logs or raw error messages."""

import json
import os
import platform
import re
import time
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from monarch import __version__
from monarch.backends.hyprland.commands import Hyprctl
from monarch.backends.hyprland.drm import LINK_ERROR, disabled_links
from monarch.backends.hyprland.inspector import Inspection, Inspector
from monarch.backends.hyprland.session import Session
from monarch.backends.hyprland.support import blockers
from monarch.domain.advanced import features
from monarch.errors import MonarchError
from monarch.services.reporting import report
from monarch.services.state import TERMINAL, Paths
from monarch.storage.automation import Autostart, PolicyStore, control
from monarch.storage.files import no_symlinks, read_json
from monarch.storage.managed import Managed
from monarch.storage.profiles import ProfileStore, config_home


def integration(inspection: Inspection, directory: Path | None) -> dict[str, str]:
    if directory is None and inspection.config.path:
        root = inspection.config.path
        candidate = root.parent / "monarch"
        if (candidate / "integration.json").exists():
            directory = candidate
        elif (root.parent / "monarch_monitors.lua").exists():
            directory = root.parent
    if directory is None or not directory.exists():
        return {
            "code": "not_registered",
            "action": "Set up monitor management after reviewing its basic-state contract.",
        }
    try:
        store = Managed(directory)
        # Existing storage only. Diagnostics must never create a managed directory.
        store.read()
        if not inspection.config.verified or store.root != inspection.config.path:
            return {
                "code": "target_mismatch",
                "action": "Select the registration for the compositor's verified active root.",
            }
        return {
            "code": "verified",
            "action": "Owned source hashes match; other guard checks still apply.",
        }
    except MonarchError as exc:
        message = str(exc)
        if "Desktop root changed" in message:
            code, action = (
                "root_changed",
                "Review the changed desktop root through Set up monitor management.",
            )
        elif "dependency changed" in message:
            code, action = (
                "dependency_changed",
                "Review declared dependencies before applying or recovering.",
            )
        elif "Symlinks" in message or "private" in message or "permissions" in message:
            code, action = (
                "unsafe_storage",
                "Review storage ownership, permissions and symlinks; preserve existing data.",
            )
        else:
            code, action = (
                "invalid_managed_data",
                "Review managed data and backups; do not delete recovery journals.",
            )
        return {"code": code, "action": action}
    except OSError:
        return {
            "code": "unavailable",
            "action": "Check config access and ownership; existing files were not changed.",
        }


async def collect(
    *,
    session: Session | None = None,
    env: Mapping[str, str] | None = None,
    directory: Path | None = None,
    inspection: Inspection | None = None,
    executable: str = "hyprctl",
    request_timeout: float = 3,
) -> dict[str, Any]:
    env = os.environ if env is None else env
    try:
        package_version = version("PySide6")
        match = re.match(r"^(\d+\.\d+\.\d+)(?:$|[-+.])", package_version)
        qt = match[1] if match else "unknown"
    except PackageNotFoundError:
        qt = "not_installed"
    data: dict[str, Any] = {
        "schema_version": 1,
        "redacted": True,
        "monarch": __version__,
        "python": platform.python_version(),
        "pyside": qt,
        "session": "unavailable",
        "inspection": None,
        "checks": [],
    }
    try:
        session = session or Session.from_environment(env)
    except MonarchError:
        data["checks"].append(
            {
                "code": "no_session",
                "action": "Run diagnostics inside the intended Hyprland session.",
            }
        )
    if session is not None:
        data["session"] = "selected"
        try:
            inspection = (
                inspection
                or await Inspector(
                    Hyprctl(session, executable=executable, env=env, timeout=request_timeout)
                ).inspect()
            )
            data["inspection"] = report(inspection)
            data["checks"] += [
                {"code": code, "action": action} for code, action in blockers(inspection)
            ]
            if disabled_links(inspection.monitors):
                data["checks"].append({"code": "drm_output_disabled", "action": LINK_ERROR})
            data["integration"] = integration(inspection, directory)
            data["advanced"] = [
                {"output": f"display-{i}", "features": [f.to_dict() for f in features(m.advanced)]}
                for i, m in enumerate(inspection.monitors, 1)
            ]
        except (MonarchError, OSError, ValueError):
            data["checks"].append(
                {
                    "code": "discovery_unavailable",
                    "action": "Check hyprctl, the selected session and compositor responsiveness.",
                }
            )
        try:
            state_home = Path(
                env.get(
                    "XDG_STATE_HOME", str(Path(env.get("HOME", str(Path.home()))) / ".local/state")
                )
            )
            paths = Paths.for_session(session, state_home, create=False)
            journal = paths.status()
            status = journal.get("status") if journal else "none"
            known = TERMINAL | {
                "none",
                "armed",
                "applying",
                "pending",
                "persisting",
                "recovering",
                "recovery_required",
            }
            data["transaction"] = {
                "state": status if status in known else "unknown",
                "recovery_required": bool(journal and status not in TERMINAL),
            }
            data["manual_pin"] = control(paths)["pinned"]
            status_path = paths.runtime / "automation-status.json"
            if status_path.exists():
                status_data = read_json(status_path)
                heartbeat = status_data.get("heartbeat")
                data["automatic_runner_recent"] = bool(
                    status_data.get("owner") is True
                    and type(heartbeat) in (int, float)
                    and 0 <= time.monotonic() - heartbeat < 5
                )
        except (MonarchError, OSError, ValueError, TypeError, AttributeError):
            data["checks"].append(
                {
                    "code": "session_state_invalid",
                    "action": "Review session state and retained recovery journals locally.",
                }
            )
    try:
        root = config_home(env)
        catalog = ProfileStore(root).list()
        policy = PolicyStore(root).read()
        data["profiles"] = {"count": len(catalog)}
        data["automation"] = {"enabled": policy.enabled, "rule_count": len(policy.rules)}
        data["autostart"] = "verified" if Autostart(root).active() else "not_verified"
    except (MonarchError, OSError, ValueError):
        data["checks"].append(
            {
                "code": "settings_invalid",
                "action": "Review private profile, policy or autostart data; it was not modified.",
            }
        )
    return data


def save(path: Path, data: dict[str, Any]) -> None:
    """Explicit export to a NEW private file, including in a normal documents directory."""
    content = json.dumps(data, indent=2, ensure_ascii=True, allow_nan=False).encode() + b"\n"
    no_symlinks(path)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise MonarchError("Diagnostic target exists; choose a new filename.") from exc
