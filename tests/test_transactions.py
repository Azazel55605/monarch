import asyncio
from dataclasses import replace

import pytest

from monarch.domain.layout import Layout
from monarch.domain.monitors import Mode, parse_monitors
from monarch.errors import MonarchError
from monarch.services.state import Paths, SessionLock
from monarch.services.transaction import Transaction
from monarch.storage.files import read_private
from monarch.storage.managed import Managed


class FakeBackend:
    def __init__(self, store, live):
        self.store = store
        self.live = live
        self.calls = []
        self.fail_at = None
        self.step = 0
        self.gone = False
        self.errors = False
        self.reject = False

    async def observe(self):
        if self.gone:
            raise MonarchError("Compositor gone")
        return self.live

    async def check_errors(self):
        if self.errors:
            raise MonarchError("config errors")

    async def set_output(self, output):
        self.step += 1
        self.calls.append(output)
        if self.step == self.fail_at:
            raise MonarchError("injected partial failure")
        if self.reject:
            return
        updated = []
        for m in self.live:
            if m.name == output.name:
                mode = Mode.parse(output.mode + "Hz") if output.mode != "preferred" else m.modes[0]
                m = replace(
                    m,
                    width=mode.width,
                    height=mode.height,
                    refresh_hz=mode.refresh_hz,
                    x=output.x,
                    y=output.y,
                    transform=output.transform,
                    scale=output.scale,
                    disabled=not output.enabled,
                    mirror_of=output.mirror or None,
                    advanced=replace(m.advanced, vrr_active=bool(output.vrr)),
                )
            updated.append(m)
        self.live = tuple(updated)

    async def reload(self):
        if self.gone:
            raise MonarchError("Compositor gone")
        layout, _ = self.store.read()
        for output in layout.outputs:
            await self.set_output(output)
        await self.check_errors()


@pytest.fixture
def setup_transaction(tmp_path, monitors):
    monitors[0]["scale"] = 1
    live = parse_monitors(monitors)
    baseline = Layout.capture(live)
    store = Managed(tmp_path / "owned")
    store.create(baseline)
    paths = Paths(tmp_path / "locks", tmp_path / "state")
    paths.runtime.mkdir(mode=0o700)
    paths.state.mkdir(mode=0o700)
    backend = FakeBackend(store, live)
    transaction = Transaction(backend, paths, lambda: "same-session")
    desired = Layout((replace(baseline.outputs[0], scale=2, x=-1280), baseline.outputs[1]))
    return transaction, backend, store, baseline, desired


def test_runtime_keep_then_next_preview_recovers_confirmed_runtime(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction

    async def run():
        await tx.prepare(store, desired, store.root, 15)
        assert tx.paths.status()["status"] == "armed"
        await tx.apply()
        await tx.keep(False)
        assert desired.matches(backend.live)
        assert store.read()[0] == baseline
        second = Transaction(backend, tx.paths, lambda: "same-session")
        await second.prepare(store, baseline, store.root, 15)
        await second.apply()
        await second.rollback("test")
        assert desired.matches(backend.live)

    asyncio.run(run())


def test_persist_and_recover_backup(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction
    original = read_private(store.monitors)

    async def run():
        await tx.prepare(store, desired, store.root, 15)
        await tx.apply()
        await tx.keep(True)
        assert store.read()[0] == desired
        assert desired.matches(backend.live)
        assert list(tx.paths.state.glob("backup-*.lua"))[0].read_bytes() == original

    asyncio.run(run())


@pytest.mark.parametrize("point", range(1, 9))
def test_failure_after_each_individual_mutation_restores_baseline(setup_transaction, point):
    tx, backend, store, baseline, desired = setup_transaction

    async def run():
        await tx.prepare(store, desired, store.root, 15)
        backend.fail_at = point
        try:
            await tx.apply()
        except MonarchError:
            pass
        await tx.rollback("injected")
        assert baseline.matches(backend.live)
        assert tx.paths.status()["status"] == "reverted"
        assert store.read()[0] == baseline

    asyncio.run(run())


def test_file_conflict_preserved_and_next_transaction_blocked(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction

    async def run():
        await tx.prepare(store, desired, store.root, 15)
        await tx.apply()
        external = read_private(store.monitors) + b"-- external\n"
        store.monitors.write_bytes(external)
        await tx.rollback("conflict")
        assert read_private(store.monitors) == external
        assert tx.paths.status()["status"] == "recovery_required"
        with pytest.raises(MonarchError, match="unfinished"):
            await Transaction(backend, tx.paths, lambda: "same-session").prepare(
                store, desired, store.root, 15
            )

    asyncio.run(run())


def test_changed_session_never_replays_or_writes(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction

    async def run():
        await tx.prepare(store, desired, store.root, 15)
        await tx.apply()
        backend.calls.clear()
        tx.token = lambda: "new-session"
        await tx.rollback("stale")
        assert not backend.calls
        assert tx.paths.status()["status"] == "recovery_required"
        recovery = Transaction(backend, tx.paths, lambda: "new-session")
        with pytest.raises(MonarchError, match="different"):
            await recovery.recover()
        assert not backend.calls

    asyncio.run(run())


def test_compositor_loss_retains_journal_then_manual_recovery(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction

    async def run():
        await tx.prepare(store, desired, store.root, 15)
        await tx.apply()
        backend.gone = True
        await tx.rollback("lost")
        assert tx.paths.status()["status"] == "recovery_required"
        backend.gone = False
        await Transaction(backend, tx.paths, lambda: "same-session").recover()
        assert baseline.matches(backend.live)
        assert tx.paths.status()["status"] == "reverted"

    asyncio.run(run())


def test_topology_change_keeps_a_usable_available_output(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction

    async def run():
        await tx.prepare(store, desired, store.root, 15)
        await tx.apply()
        backend.live = (backend.live[1],)
        await tx.rollback("hotplug")
        assert tx.paths.status()["status"] == "degraded"
        assert backend.live[0].disabled is False
        assert not backend.live[0].mirror_of

    asyncio.run(run())


def test_lock_and_unverified_config_rejected(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction
    with SessionLock(tx.paths):
        with pytest.raises(MonarchError, match="Another"):
            with SessionLock(tx.paths):
                pass

    async def run():
        with pytest.raises(MonarchError, match="verified"):
            await tx.prepare(store, desired, None, 15)
        assert not backend.calls

    asyncio.run(run())


def test_failed_persistence_reload_restores_file_and_runtime(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction

    async def run():
        await tx.prepare(store, desired, store.root, 15)
        await tx.apply()
        original_reload = backend.reload
        failed = False

        async def fail_candidate_reload():
            nonlocal failed
            await original_reload()
            if store.read()[0] == desired and not failed:
                failed = True
                raise MonarchError("injected candidate reload failure")

        backend.reload = fail_candidate_reload
        with pytest.raises(MonarchError, match="candidate"):
            await tx.keep(True)
        assert store.read()[0] == desired
        await tx.rollback("persist_failed")
        assert failed
        assert baseline.matches(backend.live)
        assert store.read()[0] == baseline
        assert tx.paths.status()["status"] == "reverted"

    asyncio.run(run())


def test_rejected_destination_never_disables_source(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction
    # Switch from the currently enabled first output to the second output.
    desired = Layout(
        (replace(baseline.outputs[0], enabled=False), replace(baseline.outputs[1], enabled=True))
    )

    async def run():
        await tx.prepare(store, desired, store.root, 15)
        original_set = backend.set_output

        async def reject_destination(output):
            if output.name == desired.outputs[1].name and output.enabled:
                backend.calls.append(output)
                return
            await original_set(output)

        backend.set_output = reject_destination
        with pytest.raises(MonarchError, match="not observed"):
            await tx.apply()
        assert not any(not o.enabled and o.name == baseline.outputs[0].name for o in backend.calls)
        await tx.rollback("rejected")
        assert baseline.matches(backend.live)

    asyncio.run(run())


def test_known_disk_baseline_is_accepted_after_runtime_keep_and_reload(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction

    async def run():
        await tx.prepare(store, desired, store.root, 15)
        await tx.apply()
        await tx.keep(False)
        await backend.reload()
        second = Transaction(backend, tx.paths, lambda: "same-session")
        await second.prepare(store, desired, store.root, 15)
        await second.apply()
        await second.rollback("test")
        assert baseline.matches(backend.live)

    asyncio.run(run())


def test_unknown_runtime_override_is_rejected_before_first_mutation(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction
    backend.live = (replace(backend.live[0], x=999), backend.live[1])

    async def run():
        with pytest.raises(MonarchError, match="Runtime differs"):
            await tx.prepare(store, desired, store.root, 15)
        assert not backend.calls
        assert tx.paths.status() is None

    asyncio.run(run())


def test_foreign_session_journal_blocks_same_owned_root(setup_transaction):
    from monarch.storage.files import write_json

    tx, backend, store, baseline, desired = setup_transaction
    foreign = tx.paths.state.parent / "old-session"
    foreign.mkdir(mode=0o700)
    write_json(
        foreign / "active.json",
        {"schema_version": 1, "root": str(store.directory), "status": "pending", "id": "old"},
    )
    assert tx.paths.foreign_unfinished() == 1

    async def run():
        with pytest.raises(MonarchError, match="another session"):
            await tx.prepare(store, desired, store.root, 15)
        assert not backend.calls

    asyncio.run(run())


def test_guard_refuses_logically_matching_mode_with_disabled_drm_connector(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction
    backend.live = (
        replace(backend.live[0], dpms_on=True, connector_enabled=False),
        backend.live[1],
    )

    async def run():
        await tx.prepare(store, desired, store.root, 15)
        with pytest.raises(MonarchError, match="Linux still reports"):
            await tx.apply()
        assert not tx.pending
        await tx.rollback("apply_failed")
        assert baseline.matches(backend.live)
        assert tx.paths.status()["status"] == "reverted"

    asyncio.run(run())
