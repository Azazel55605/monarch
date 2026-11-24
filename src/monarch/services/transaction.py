"""The sole transaction state machine; invoked under a session lock by the guard."""

import asyncio
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

from monarch.backends.hyprland.drm import LINK_ERROR, disabled_links
from monarch.domain.advanced import basic_issues, hdr_available, require_basic
from monarch.domain.layout import Layout, Output, ordered, unique_hdr_target
from monarch.domain.monitors import Monitor
from monarch.domain.quick_layout import hotplug_baseline, identity
from monarch.errors import MonarchError
from monarch.services.baseline import known_baseline
from monarch.services.state import TERMINAL, Paths
from monarch.storage.files import atomic_write, digest, read_private, write_json
from monarch.storage.managed import ROOT, Managed, parse_content, render


class Backend(Protocol):
    async def observe(self) -> tuple[Monitor, ...]: ...
    async def set_output(self, output: Output) -> None: ...
    async def set_hdr(
        self, output: Output, enabled: bool, *, by_identity: bool = False
    ) -> None: ...
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
        self._vrr_policies: dict[str, int] = {}
        self._prepared_monitors: tuple[Monitor, ...] | None = None
        self._hdr_scope: set[tuple[str, str, str, str]] = set()

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
        topology_snapshot: Layout | None = None,
        hdr_target: str | None = None,
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
        if topology_snapshot is not None and not topology_snapshot.matches(monitors):
            raise MonarchError(
                "The observed layout changed before preview. Open the shortcut again."
            )
        desired.validate(monitors)
        baseline, disk_bytes = known_baseline(
            managed,
            self.paths,
            self.token(),
            monitors,
            allow_topology_rebase=allow_topology_rebase,
        )
        require_basic(monitors, hdr=baseline.owned_hdr_identities(monitors))
        disk = parse_content(disk_bytes)
        saved_set = {(o.name, o.make, o.model, o.serial) for o in baseline.outputs}
        connected_set = {(m.name, m.make, m.model, m.serial) for m in monitors}
        rebased = allow_topology_rebase and saved_set != connected_set
        if rebased:
            # Use the live topology, retaining VRR policies for identified
            # outputs. A stale timing on a reused port is not a recovery mode.
            baseline = hotplug_baseline(monitors, baseline, disk)
        baseline.validate(monitors)
        if not rebased and not baseline.matches(monitors):
            raise MonarchError(
                "Runtime differs from the owned baseline; external overrides are unknown."
            )
        if hdr_target is not None:
            require_basic(monitors)
            target = next((m for m in monitors if m.name == hdr_target), None)
            if not desired.matches(monitors):
                raise MonarchError("The monitor layout changed. Reopen Advanced settings.")
            if target is None or not hdr_available(target) or not self.hdr_link_ok(target):
                raise MonarchError("HDR requires an active display advertising HDR and BT.2020.")
            if any(o.enabled and o.mirror == hdr_target for o in baseline.outputs):
                raise MonarchError("Disable mirroring before testing HDR on this display.")
            if not any(
                m.name != hdr_target
                and m.disabled is False
                and not m.mirror_of
                and m.dpms_on is not False
                and self.hdr_link_ok(m)
                for m in monitors
            ):
                raise MonarchError("Keep another independent display active for the HDR preview.")
            desired = baseline
        self._hdr_scope = (
            baseline.hdr_identities | desired.hdr_identities | disk.owned_hdr_identities(monitors)
        )
        self._prepared_monitors = monitors
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
        if hdr_target is not None:
            self.record.update(hdr_target=hdr_target, hdr_write_started=False)
        # An immutable backup and durable journal exist before the first mutation.
        atomic_write(self.paths.state / f"backup-{self.record['id']}.lua", disk_bytes, create=True)
        self.save("armed")

    async def reload(self) -> None:
        self._vrr_policies.clear()
        await self.backend.reload()

    async def set_layout(self, layout: Layout) -> None:
        assert self.record is not None
        for output in ordered(layout):
            live = await self.backend.observe()
            require_basic(
                live, hdr=self._hdr_scope, recovering=self.record["status"] == "recovering"
            )
            layout.validate(live)
            monitor = next(m for m in live if m.name == output.name)
            if (
                getattr(self.backend, "vrr_refresh_required", False)
                and output.enabled
                and not output.mirror
                and monitor.advanced.vrr_capable is True
                and self._vrr_policies.get(output.name) != output.vrr
            ):
                # A VRR-only change is ignored by 0.57.2's rule comparison.
                # First observe a soft-property change so its active rule adopts
                # the policy; the final write triggers VRR using that active rule.
                # Position is owned/journaled, unlike global options or work areas.
                x = output.x + 1 if output.x < 2**31 - 1 else output.x - 1
                await self.set_one(layout, replace(output, x=x), verify_vrr=False)
            await self.set_one(layout, output)
            self._vrr_policies[output.name] = output.vrr

    async def set_one(self, layout: Layout, output: Output, *, verify_vrr: bool = True) -> None:
        self.check_session()
        if self.authorize is not None and self.record and self.record["status"] != "recovering":
            self.authorize()
        assert self.record is not None
        self.managed.check(self.record["disk_digest"])
        live_before = await self.backend.observe()
        recovering = self.record["status"] == "recovering"
        require_basic(live_before, hdr=self._hdr_scope, recovering=recovering)
        layout.validate(live_before)
        color_write = identity(output) in self._hdr_scope
        if color_write:
            if not unique_hdr_target(output, live_before):
                raise MonarchError("The HDR display identity is ambiguous.")
            await self.backend.set_hdr(output, output.hdr, by_identity=True)
        else:
            await self.backend.set_output(output)
        deadline = time.monotonic() + 2
        while True:
            self.check_session()
            live = await self.backend.observe()
            if color_write:
                require_basic(
                    tuple(m for m in live if m.name != output.name),
                    hdr=self._hdr_scope,
                    recovering=recovering,
                )
            else:
                require_basic(live, hdr=self._hdr_scope, recovering=recovering)
            layout.validate(live)
            selected = tuple(m for m in live if m.name == output.name)
            expected = output
            if not verify_vrr:
                # Only the intermediate soft refresh may defer VRR verification.
                # Its exact geometry and identity must already be observed.
                expected = replace(output, vrr=int(selected[0].advanced.vrr_active is True))
            if Layout((expected,)).matches(selected):
                require_basic(live, hdr=self._hdr_scope, recovering=recovering)
                break
            if time.monotonic() >= deadline:
                detail = (
                    " (HDR/SDR preset, bit depth, or SDR tone controls did not settle)"
                    if color_write
                    else ""
                )
                if verify_vrr and selected[0].advanced.vrr_active is not bool(output.vrr):
                    requested = "On" if output.vrr else "Off"
                    observed = "On" if selected[0].advanced.vrr_active else "Off"
                    detail = f" (VRR requested {requested}, observed {observed})"
                raise MonarchError(
                    "A monitor update was not observed"
                    + detail
                    + "; stopping before further writes."
                )
            await asyncio.sleep(0.1)

    async def settle(
        self, layout: Layout, *, settling_seconds: float = 2, verify_links: bool = False
    ) -> None:
        deadline = time.monotonic() + settling_seconds
        while True:
            self.check_session()
            live = await self.backend.observe()
            # Topology and identity changes fail immediately, not after settling.
            layout.validate(live)
            matched = layout.matches(live)
            blocked_links = (
                self.layout_link_errors(layout, live) if verify_links and matched else ()
            )
            if matched and not blocked_links:
                require_basic(live, hdr=self._hdr_scope)
                await self.backend.check_errors()
                return
            if time.monotonic() >= deadline:
                raise MonarchError(
                    LINK_ERROR
                    if blocked_links
                    else "Observed monitor state did not match the requested layout."
                )
            await asyncio.sleep(0.1)

    def hdr_output(self, layout: Layout) -> Output:
        assert self.record is not None
        if type(self.record.get("hdr_write_started")) is not bool:
            raise MonarchError("Invalid HDR recovery journal.")
        output = next((o for o in layout.outputs if o.name == self.record["hdr_target"]), None)
        if output is None or not output.enabled or output.mirror:
            raise MonarchError("Invalid HDR recovery target.")
        return output

    def hdr_link_ok(self, monitor: Monitor) -> bool:
        return (
            monitor.connector_enabled is True
            if getattr(self.backend, "native_drm", False)
            else monitor.connector_enabled is not False
        )

    def layout_link_errors(self, layout: Layout, live: tuple[Monitor, ...]) -> tuple[str, ...]:
        return disabled_links(live) + tuple(
            m.name for m in live if identity(m) in layout.hdr_identities and not self.hdr_link_ok(m)
        )

    def hdr_matches(
        self, live: tuple[Monitor, ...], output: Output, enabled: bool, layout: Layout | None
    ) -> bool:
        target = next((m for m in live if identity(m) == identity(output)), None)
        if (
            target is None
            or target.dpms_on is False
            or not self.hdr_link_ok(target)
            or not Layout((output,)).matches((target,), check_color=False)
        ):
            return False
        if enabled:
            if (
                not hdr_available(target)
                or target.advanced.color_preset != "hdr"
                or target.advanced.bit_depth != 10
                or not output.sdr_tuning_matches(target.advanced)
            ):
                return False
            require_basic(tuple(m for m in live if m.name != target.name), hdr=self._hdr_scope)
        elif basic_issues((target,)):
            return False
        return layout is None or (
            layout.matches(live, check_color=False) and not disabled_links(live)
        )

    async def settle_hdr(
        self, output: Output, enabled: bool, layout: Layout | None = None
    ) -> tuple[Monitor, ...]:
        deadline = time.monotonic() + 3
        while True:
            self.check_session()
            live = await self.backend.observe()
            if layout is not None:
                layout.validate(live)
            if self.hdr_matches(live, output, enabled, layout):
                await self.backend.check_errors()
                return live
            if time.monotonic() >= deadline:
                state = "10-bit HDR" if enabled else "8-bit SDR"
                raise MonarchError(f"Could not verify {state} and an active display link.")
            await asyncio.sleep(0.1)

    async def restore_hdr(self, live: tuple[Monitor, ...], reason: str) -> None:
        assert self.record is not None
        baseline = Layout.parse(self.record["baseline"])
        output = self.hdr_output(baseline)
        if self.record["hdr_write_started"] and any(identity(m) == identity(output) for m in live):
            self.check_session()
            self.managed.check(self.record["disk_digest"])
            await self.backend.set_hdr(output, False)
            live = await self.settle_hdr(output, False)
        require_basic(live, hdr=self._hdr_scope)
        if not baseline.matches(live) or disabled_links(live):
            if not any(
                m.disabled is False
                and not m.mirror_of
                and m.dpms_on is not False
                and self.hdr_link_ok(m)
                for m in live
            ):
                raise MonarchError("No active SDR output could be verified after HDR recovery.")
            self.save("degraded", "layout_changed_during_hdr")
            return
        self.save("reverted", reason)

    async def apply(self) -> None:
        if self.authorize is not None:
            self.authorize()
        assert self.record is not None
        self.check_session()
        self.managed.check(self.record["disk_digest"])
        self.save("applying")
        baseline = Layout.parse(self.record["baseline"])
        live = await self.backend.observe()
        require_basic(live, hdr=self._hdr_scope)
        if not baseline.matches(live) and live != self._prepared_monitors:
            raise MonarchError("The captured layout changed before the preview started.")
        if "hdr_target" in self.record:
            output = self.hdr_output(baseline)
            self.record["hdr_write_started"] = True
            self.save("applying")
            await self.backend.set_hdr(output, True)
            await self.settle_hdr(output, True, baseline)
            self.save("pending")
            self.pending = True
            return
        # Reloading a saved rule for a reused connector can modeset the new
        # display with the old display's timing before the preview even starts.
        if not self.saved_connector_reused(live) and not (
            self._hdr_scope and baseline.matches(live)
        ):
            await self.reload()
            await self.set_layout(baseline)
            await self.settle(baseline)
        self.managed.check(self.record["disk_digest"])
        desired = Layout.parse(self.record["desired"])
        await self.set_layout(desired)
        await self.settle(desired, verify_links=True)
        self.save("pending")
        self.pending = True

    def saved_connector_reused(self, monitors: tuple[Monitor, ...]) -> bool:
        assert self.record is not None
        disk = parse_content(self.record["disk_content"].encode())
        saved = {o.name: identity(o) for o in disk.outputs}
        return any(m.name in saved and saved[m.name] != identity(m) for m in monitors)

    async def check_pending(self) -> None:
        if self.authorize is not None:
            self.authorize()
        assert self.record is not None
        self.check_session()
        self.managed.check(self.record["disk_digest"])
        desired = Layout.parse(self.record["desired"])
        live = await self.backend.observe()
        if "hdr_target" in self.record:
            if not self.hdr_matches(live, self.hdr_output(desired), True, desired):
                raise MonarchError("The HDR preview no longer matches the requested display state.")
            await self.backend.check_errors()
            return
        require_basic(live, hdr=self._hdr_scope)
        if desired.hdr_identities:
            desired.validate(live)
        if not desired.matches(live):
            raise MonarchError("Monitor topology or layout changed during preview.")
        if self.layout_link_errors(desired, live):
            raise MonarchError(LINK_ERROR)
        await self.backend.check_errors()

    async def keep(self, persist: bool) -> None:
        assert self.record is not None
        if "hdr_target" in self.record:
            raise MonarchError("The HDR preview must return to SDR.")
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
            await self.reload()
            await self.settle(desired, verify_links=True)
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
            if "hdr_target" in self.record:
                self.managed.check(self.record["disk_digest"])
                await self.restore_hdr(await self.backend.observe(), reason)
                return
            current = read_private(self.managed.monitors)
            if digest(current) not in (self.record["disk_digest"], self.record["candidate_digest"]):
                raise MonarchError("External monitor file edit is preserved.")
            if digest(current) != self.record["disk_digest"]:
                atomic_write(
                    self.managed.monitors,
                    self.record["disk_content"].encode(),
                    expected=digest(current),
                )
            live = await self.backend.observe()
            require_basic(live, hdr=self._hdr_scope, recovering=True)
            if not self.saved_connector_reused(live):
                await self.reload()
                live = await self.backend.observe()
            baseline = Layout.parse(self.record["baseline"])
            try:
                baseline.validate(live)
            except MonarchError:
                if self._hdr_scope:
                    live = await self.restore_surviving_hdr(baseline, live)
                await self.fallback(live)
                self.save("degraded", "topology_changed")
                return
            await self.set_layout(baseline)
            await self.settle(baseline, verify_links=bool(baseline.hdr_identities))
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
        usable = [m for m in live if m.disabled is False and not m.mirror_of]
        if self._hdr_scope and any(m.dpms_on is not False and self.hdr_link_ok(m) for m in usable):
            return
        m = next(iter(usable), live[0])
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

    async def restore_surviving_hdr(
        self, baseline: Layout, live: tuple[Monitor, ...]
    ) -> tuple[Monitor, ...]:
        assert self.record is not None
        for output in baseline.outputs:
            if identity(output) not in self._hdr_scope or not output.enabled or output.mirror:
                continue
            target = next((m for m in live if identity(m) == identity(output)), None)
            if target is None or target.disabled is not False or target.mirror_of:
                continue
            if output.hdr and not hdr_available(target):
                continue
            if not unique_hdr_target(output, live):
                raise MonarchError("The HDR recovery target is ambiguous.")
            self.check_session()
            self.managed.check(self.record["disk_digest"])
            await self.backend.set_hdr(output, output.hdr, by_identity=True)
            live = await self.settle_hdr(output, output.hdr)
        return live

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
        baseline = Layout.parse(record["baseline"])
        desired = Layout.parse(record["desired"])
        disk = parse_content(record["disk_content"].encode())
        if digest(record["disk_content"].encode()) != record["disk_digest"]:
            raise MonarchError("Recovery backup digest mismatch.")
        if (
            digest(render(desired, legacy=record["desired"]["schema_version"] == 1))
            != record["candidate_digest"]
        ):
            raise MonarchError("Recovery candidate digest mismatch.")
        self.record = record
        if "hdr_target" in record:
            self.hdr_output(baseline)
            if desired != baseline or record.get("automation") is not None:
                raise MonarchError("Invalid HDR recovery journal.")
        self.check_session()
        self._hdr_scope = (
            baseline.hdr_identities
            | desired.hdr_identities
            | disk.owned_hdr_identities(await self.backend.observe())
        )
        await self.rollback("manual_recovery")
