"""The sole transaction state machine; invoked under a session lock by the guard."""

import asyncio
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from monarch.domain.advanced import require_basic
from monarch.domain.layout import Layout, Output, ordered
from monarch.domain.monitors import Monitor
from monarch.errors import MonarchError
from monarch.services.baseline import known_baseline
from monarch.services.state import TERMINAL, Paths
from monarch.storage.files import atomic_write, digest, read_private, write_json
from monarch.storage.managed import ROOT, Managed, parse_content, render


class Backend(Protocol):
    async def observe(self) -> tuple[Monitor, ...]: ...
    async def set_output(self, output: Output) -> None: ...
    async def reload(self) -> None: ...
    async def check_errors(self) -> None: ...


class Transaction:
    def __init__(self, backend: Backend, paths: Paths, token: Callable[[], str]) -> None:
        self.backend = backend
        self.paths = paths
        self.token = token
        self.record: dict[str, Any] | None = None
        self.pending = False
        self.authorize: Callable[[], None] | None = None

    def save(self, status: str, reason: str = "") -> None:
        assert self.record is not None
        self.record.update(status=status, reason=reason)
        write_json(self.paths.journal, self.record)

    @property
    def managed(self) -> Managed:
        assert self.record is not None
        return Managed(Path(self.record["root"]))

    def check_session(self) -> None:
        assert self.record is not None
        if self.record.get("root_fingerprint", digest(ROOT)) != self.managed.root_fingerprint():
            raise MonarchError("Configuration registration changed during the transaction.")
        if self.record["session_token"] != self.token():
            raise MonarchError(
                "Recovery belongs to a different compositor generation; refusing replay."
            )

    async def prepare(
        self,
        managed: Managed,
        desired: Layout,
        active_config: Path | None,
        seconds: float,
        *,
        allow_topology_rebase: bool = False,
    ) -> None:
        previous = self.paths.status()
        if previous and previous.get("status") not in TERMINAL:
            raise MonarchError("An unfinished recovery journal exists. Run monarch recover first.")
        if self.paths.foreign_unfinished(managed.directory):
            raise MonarchError(
                "This configuration has an unfinished transaction from another session; "
                "review its backup without replaying stale commands."
            )
        if active_config != managed.root:
            raise MonarchError("Active config is not the verified Monarch-owned root.")
        monitors = await self.backend.observe()
        require_basic(monitors)
        desired.validate(monitors)
        baseline, disk_bytes = known_baseline(
            managed,
            self.paths,
            self.token(),
            monitors,
            allow_topology_rebase=allow_topology_rebase,
        )
        saved_set = {(o.name, o.make, o.model, o.serial) for o in baseline.outputs}
        connected_set = {(m.name, m.make, m.model, m.serial) for m in monitors}
        if allow_topology_rebase and saved_set != connected_set:
            # Explicit automation ownership permits only topology-driven basic
            # snapshots, never adoption of unexplained drift on the same set.
            baseline = Layout.capture(
                monitors,
                vrr_policies={
                    o.name: o.vrr
                    for o in baseline.outputs
                    if (o.name, o.make, o.model, o.serial) in connected_set
                },
            )
        baseline.validate(monitors)
        if not baseline.matches(monitors):
            raise MonarchError(
                "Runtime differs from the owned baseline; external overrides are unknown."
            )
        await self.backend.check_errors()
        self.record = {
            "schema_version": 1,
            "guard_pid": os.getpid(),
            "id": uuid.uuid4().hex,
            "root": str(managed.directory),
            "session_token": self.token(),
            "deadline": time.monotonic() + seconds,
            "baseline": baseline.to_dict(),
            "desired": desired.to_dict(),
            "disk_content": disk_bytes.decode(),
            "root_fingerprint": managed.root_fingerprint(),
            "disk_digest": digest(disk_bytes),
            "candidate_digest": digest(render(desired)),
        }
        # An immutable backup and durable journal exist before the first mutation.
        atomic_write(self.paths.state / f"backup-{self.record['id']}.lua", disk_bytes, create=True)
        self.save("armed")

    async def set_layout(self, layout: Layout) -> None:
        for output in ordered(layout):
            self.check_session()
            if self.authorize is not None and self.record and self.record["status"] != "recovering":
                self.authorize()
            assert self.record is not None
            self.managed.check(self.record["disk_digest"])
            live_before = await self.backend.observe()
            require_basic(live_before)
            layout.validate(live_before)
            await self.backend.set_output(output)
            # A successful IPC reply is not proof that a destination became
            # usable. Observe it before proceeding to any source disable.
            deadline = time.monotonic() + 2
            while True:
                self.check_session()
                live = await self.backend.observe()
                require_basic(live)
                layout.validate(live)
                selected = tuple(m for m in live if m.name == output.name)
                if Layout((output,)).matches(selected):
                    break
                if time.monotonic() >= deadline:
                    raise MonarchError(
                        "A monitor update was not observed; stopping before further writes."
                    )
                await asyncio.sleep(0.1)

    async def settle(self, layout: Layout, *, settling_seconds: float = 2) -> None:
        deadline = time.monotonic() + settling_seconds
        while True:
            self.check_session()
            live = await self.backend.observe()
            require_basic(live)
            # Topology and identity changes fail immediately, not after settling.
            layout.validate(live)
            if layout.matches(live):
                await self.backend.check_errors()
                return
            if time.monotonic() >= deadline:
                raise MonarchError("Observed monitor state did not match the requested layout.")
            await asyncio.sleep(0.1)

    async def apply(self) -> None:
        if self.authorize is not None:
            self.authorize()
        assert self.record is not None
        self.check_session()
        self.managed.check(self.record["disk_digest"])
        self.save("applying")
        # Reload only the verified owned or explicitly reviewed registered root.
        # Registration approval covers executing that user Lua again.
        await self.backend.reload()
        baseline = Layout.parse(self.record["baseline"])
        await self.set_layout(baseline)
        await self.settle(baseline)
        self.managed.check(self.record["disk_digest"])
        desired = Layout.parse(self.record["desired"])
        await self.set_layout(desired)
        await self.settle(desired)
        self.save("pending")
        self.pending = True

    async def check_pending(self) -> None:
        if self.authorize is not None:
            self.authorize()
        assert self.record is not None
        self.check_session()
        self.managed.check(self.record["disk_digest"])
        desired = Layout.parse(self.record["desired"])
        live = await self.backend.observe()
        require_basic(live)
        if not desired.matches(live):
            raise MonarchError("Monitor topology or layout changed during preview.")
        await self.backend.check_errors()

    async def keep(self, persist: bool) -> None:
        assert self.record is not None
        await self.check_pending()
        self.pending = False
        desired = Layout.parse(self.record["desired"])
        disk_digest = self.record["disk_digest"]
        if persist:
            self.save("persisting")
            atomic_write(self.managed.monitors, render(desired), expected=disk_digest)
            disk_digest = self.record["candidate_digest"]
            self.check_session()
            self.managed.check(disk_digest)
            await self.backend.reload()
            await self.settle(desired)
            self.managed.check(disk_digest)
        self.check_session()
        if time.monotonic() >= self.record["deadline"]:
            raise MonarchError("Confirmation deadline elapsed before commit finished.")
        write_json(
            self.paths.confirmed,
            {
                "root": self.record["root"],
                "disk_digest": disk_digest,
                "layout": desired.to_dict(),
                "session_token": self.record["session_token"],
            },
        )
        self.save("kept", "persisted" if persist else "runtime_only")

    async def rollback(self, reason: str) -> None:
        for _ in range(2):
            await self._rollback_once(reason)
            assert self.record is not None
            if self.record["status"] != "recovery_required":
                return
            await asyncio.sleep(0.1)

    async def _rollback_once(self, reason: str) -> None:
        assert self.record is not None
        self.pending = False
        self.save("recovering", reason)
        try:
            self.check_session()
            self.managed.verify_root()
            current = read_private(self.managed.monitors)
            if digest(current) not in (self.record["disk_digest"], self.record["candidate_digest"]):
                raise MonarchError("External monitor file edit is preserved.")
            if digest(current) != self.record["disk_digest"]:
                atomic_write(
                    self.managed.monitors,
                    self.record["disk_content"].encode(),
                    expected=digest(current),
                )
            require_basic(await self.backend.observe())
            await self.backend.reload()
            baseline = Layout.parse(self.record["baseline"])
            live = await self.backend.observe()
            try:
                baseline.validate(live)
            except MonarchError:
                await self.fallback(live)
                self.save("degraded", "topology_changed")
                return
            await self.set_layout(baseline)
            await self.settle(baseline)
            self.managed.check(self.record["disk_digest"])
            write_json(
                self.paths.confirmed,
                {
                    "root": self.record["root"],
                    "disk_digest": self.record["disk_digest"],
                    "layout": baseline.to_dict(),
                    "session_token": self.record["session_token"],
                },
            )
            self.save("reverted", reason)
        except (MonarchError, OSError):
            # Do not overwrite conflicts or replay into another session. The durable
            # journal remains actionable and blocks new transactions until recovery.
            self.save("recovery_required", reason)

    async def fallback(self, live: tuple[Monitor, ...]) -> None:
        self.check_session()
        if not live:
            raise MonarchError("No connected output is available for recovery.")
        # No disabling during degraded recovery. Clear mirroring on an available
        # output and enable a preferred-mode root, then verify a usable result.
        m = next((m for m in live if m.disabled is False and not m.mirror_of), live[0])
        await self.backend.set_output(
            Output(m.name, m.make, m.model, m.serial, "preferred", 1, 0, 0, 0)
        )
        for _ in range(20):
            self.check_session()
            observed = await self.backend.observe()
            if any(
                m.disabled is False
                and not m.mirror_of
                and m.width
                and m.height
                and m.width > 0
                and m.height > 0
                for m in observed
            ):
                return
            await asyncio.sleep(0.1)
        raise MonarchError("Degraded recovery could not verify a usable output.")

    async def recover(self) -> None:
        record = self.paths.status()
        if not record or record.get("status") in TERMINAL:
            raise MonarchError("No unfinished transaction exists for this session.")
        for key in (
            "id",
            "root",
            "session_token",
            "disk_content",
            "disk_digest",
            "candidate_digest",
            "baseline",
            "desired",
        ):
            if key not in record:
                raise MonarchError("Incomplete recovery journal; manual recovery required.")
        # Validate journal-contained data before allowing any mutation.
        Layout.parse(record["baseline"])
        Layout.parse(record["desired"])
        parse_content(record["disk_content"].encode())
        if digest(record["disk_content"].encode()) != record["disk_digest"]:
            raise MonarchError("Recovery backup digest mismatch.")
        if (
            digest(
                render(
                    Layout.parse(record["desired"]), legacy=record["desired"]["schema_version"] == 1
                )
            )
            != record["candidate_digest"]
        ):
            raise MonarchError("Recovery candidate digest mismatch.")
        self.record = record
        self.check_session()
        await self.rollback("manual_recovery")
