"""One session owner, stable-topology selection, durable suppression and bounded retries."""

import json
import math
import time
from typing import Any

from monarch.backends.hyprland.inspector import Inspection
from monarch.domain.policy import Policy, Selection, choose, topology
from monarch.errors import MonarchError
from monarch.services.coordinator import Coordinator
from monarch.services.state import SessionLock, session_token
from monarch.storage.automation import PolicyStore, control, permit
from monarch.storage.files import digest, read_json, read_private, write_json
from monarch.storage.profiles import ProfileStore, decode


class Automation:
    def __init__(self, coordinator: Coordinator, profiles: ProfileStore) -> None:
        self.coordinator = coordinator
        self.profiles = profiles
        self.store = PolicyStore(profiles.directory)
        self.paths = coordinator.paths
        self.token = session_token(coordinator.session)
        self.owner: SessionLock | None = None
        self.stable_key = ""
        self.stable_since = 0.0
        self.attempt: dict[str, Any] = {
            "key": "",
            "outcome": "",
            "failures": 0,
            "retry": 0.0,
            "topology": "",
        }
        self.selection = Selection("Waiting for topology discovery.")
        self.generation = ""
        self.policy_digest = ""
        self.profiles_digest = ""
        self.reason = "Automatic switching is disabled."
        self.status_path = self.paths.runtime / "automation-status.json"
        self.attempt_path = self.paths.runtime / "automation-attempt.json"
        if self.attempt_path.exists():
            value = read_json(self.attempt_path)
            if (
                not isinstance(value, dict)
                or set(value) != set(self.attempt)
                or not isinstance(value["key"], str)
                or not isinstance(value["outcome"], str)
                or not isinstance(value["topology"], str)
                or type(value["failures"]) is not int
                or type(value["retry"]) not in (int, float)
                or not math.isfinite(value["retry"])
                or not 0 <= value["failures"] <= 3
                or value["outcome"]
                not in {"", "offered", "kept", "declined", "blocked", "satisfied", "failed"}
            ):
                raise MonarchError("Invalid automatic attempt history; writes paused.")
            self.attempt = value

    def acquire(self) -> bool:
        if self.owner is not None:
            return True
        lock = SessionLock(self.paths)
        lock.path = self.paths.runtime / "automation.lock"
        try:
            lock.__enter__()
        except MonarchError:
            return False
        self.owner = lock
        return True

    def close(self) -> None:
        if self.owner is not None:
            try:
                write_json(
                    self.status_path,
                    {
                        "schema_version": 1,
                        "heartbeat": time.monotonic(),
                        "reason": "Automatic watcher stopped.",
                        "owner": False,
                    },
                )
            finally:
                self.owner.__exit__()
            self.owner = None

    def status(self, reason: str, *, now: float) -> dict[str, Any]:
        self.reason = reason
        data = {
            "schema_version": 1,
            "heartbeat": now,
            "reason": reason,
            "owner": self.owner is not None,
            "pinned": control(self.paths)["pinned"],
            "attempt": self.attempt,
            "rejected": list(self.selection.rejected),
        }
        if self.owner is not None:
            write_json(self.status_path, data)
        return data

    def evaluate(
        self, inspection: Inspection, *, idle: bool, ready: bool, now: float | None = None
    ) -> tuple[dict[str, Any], Selection | None]:
        now = time.monotonic() if now is None else now
        policy_content = read_private(self.store.path) if self.store.path.exists() else None
        policy = Policy.parse(json.loads(policy_content)) if policy_content else Policy()
        if not policy.enabled:
            self.stable_key = ""
            if self.owner is not None:
                self.close()
            return self.status("Automatic switching is disabled.", now=now), None
        if not self.acquire():
            return self.status("Another Monarch window owns automatic switching.", now=now), None
        if session_token(self.coordinator.session) != self.token:
            raise MonarchError("The compositor generation changed; restart Monarch.")
        observed_topology = digest(repr(topology(inspection.monitors)).encode())
        if self.attempt["topology"] != observed_topology:
            self.attempt = {
                "key": "",
                "outcome": "",
                "failures": 0,
                "retry": 0.0,
                "topology": observed_topology,
            }
            self.stable_key = ""
            self.save_attempt()
        state = control(self.paths)
        self.generation = state["generation"]
        catalog = (
            read_private(self.profiles.path)
            if self.profiles.path.exists()
            else b'{"schema_version":2,"profiles":[]}'
        )
        profiles = decode(json.loads(catalog))
        self.profiles_digest = digest(catalog)
        self.selection = choose(policy, profiles, inspection.monitors)
        if state["pinned"]:
            self.stable_key = ""
            return self.status(
                "Manual override is pinned for this session. Resume to allow automatic switching.",
                now=now,
            ), None
        if not ready or not idle:
            self.stable_key = ""
            return self.status(
                "Waiting for a ready, idle editor and recoverable configuration.", now=now
            ), None
        if self.selection.layout is None:
            self.stable_key = ""
            return self.status(self.selection.reason, now=now), None
        assert policy_content is not None
        self.policy_digest = digest(policy_content)
        key = digest(
            repr(
                (
                    topology(inspection.monitors),
                    policy.to_dict(),
                    [p.to_dict() for p in profiles],
                    self.generation,
                )
            ).encode()
        )
        if key != self.stable_key:
            self.stable_key, self.stable_since = key, now
            return self.status("Waiting for the connected topology to settle.", now=now), None
        if now - self.stable_since < 1.5:
            return self.status("Waiting for the connected topology to settle.", now=now), None
        if self.attempt["key"] != key:
            self.attempt = {
                "key": key,
                "outcome": "",
                "failures": 0,
                "retry": 0.0,
                "topology": observed_topology,
            }
        outcome = self.attempt["outcome"]
        if outcome in {"offered", "kept", "declined", "blocked", "satisfied"}:
            return self.status(
                f"{self.selection.reason} Current attempt: {outcome}.", now=now
            ), None
        if now < self.attempt["retry"]:
            return self.status("Automatic apply failed; waiting for retry backoff.", now=now), None
        if self.selection.layout.matches(inspection.monitors):
            self.attempt["outcome"] = "satisfied"
            self.save_attempt()
            return self.status(
                "The selected profile already matches the current layout.", now=now
            ), None
        self.attempt["outcome"] = "offered"
        self.save_attempt()
        return self.status(
            self.selection.reason + " Starting a guarded preview.", now=now
        ), self.selection

    def save_attempt(self) -> None:
        write_json(self.attempt_path, self.attempt)

    def authorize(self) -> dict[str, str]:
        permit(
            self.paths,
            self.generation,
            self.store.path,
            self.policy_digest,
            self.profiles.path,
            self.profiles_digest,
        )
        return {
            "generation": self.generation,
            "policy_path": str(self.store.path),
            "policy_digest": self.policy_digest,
            "profiles_path": str(self.profiles.path),
            "profiles_digest": self.profiles_digest,
        }

    def finish(self, result: dict[str, Any], *, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if result.get("state") == "kept":
            self.attempt["outcome"] = "kept"
        elif result.get("reason") in {"user_revert", "deadline_elapsed", "client_disconnected"}:
            self.attempt["outcome"] = "declined"
        else:
            failures = self.attempt["failures"] + 1
            self.attempt.update(
                failures=failures,
                outcome="blocked" if failures >= 3 else "failed",
                retry=now + min(600, 30 * 2 ** (failures - 1)),
            )
        self.save_attempt()
