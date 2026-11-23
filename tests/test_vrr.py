"""Owned VRR policies must round-trip through the independent recovery guard."""

import asyncio
import json
from dataclasses import replace

import pytest
from test_guard import guard_setup as guard_setup
from test_transactions import setup_transaction as setup_transaction

from monarch.domain.layout import Layout, rule
from monarch.domain.monitors import parse_monitors
from monarch.errors import MonarchError
from monarch.services.baseline import known_baseline
from monarch.services.state import session_token
from monarch.storage.files import digest, read_private, write_json
from monarch.storage.managed import parse_content, render
from monarch.storage.profiles import ProfileStore


def legacy_data(layout):
    value = layout.to_dict()
    value["schema_version"] = 1
    for output in value["outputs"]:
        output.pop("vrr")
    return value


def capable(state):
    raw = json.loads(state.read_text())
    raw["monitors"][0]["hardwareDetails"]["vrrCapable"] = True
    state.write_text(json.dumps(raw))


def on_layout(layout):
    return Layout((replace(layout.outputs[0], vrr=1), *layout.outputs[1:]))


@pytest.mark.parametrize("value", [True, False, None, "1", -1, 2, 3, 1.0])
def test_policy_is_strict_and_conditional_modes_are_not_accepted(monitors, value):
    monitors[0]["scale"] = 1
    data = Layout.capture(parse_monitors(monitors)).to_dict()
    data["outputs"][0]["vrr"] = value
    with pytest.raises(MonarchError, match="VRR"):
        Layout.parse(data)


def test_legacy_module_roundtrips_exactly_and_new_rules_override_global_vrr(monitors):
    monitors[0]["scale"] = 1
    layout = Layout.capture(parse_monitors(monitors))
    old = render(layout, legacy=True)
    assert b"vrr=" not in old
    assert parse_content(old) == layout
    assert Layout.parse(legacy_data(layout)) == layout
    assert layout.to_dict()["schema_version"] == 2
    assert all("vrr=0" in rule(output) for output in layout.outputs)
    assert parse_content(render(on_layout(layout))).outputs[0].vrr == 1
    with pytest.raises(MonarchError, match="cannot represent"):
        render(on_layout(layout), legacy=True)
    bad = legacy_data(layout)
    bad["outputs"][0]["vrr"] = 1
    with pytest.raises(MonarchError, match="Legacy"):
        Layout.parse(bad)


def test_capture_does_not_invent_an_external_policy_from_active_state(monitors):
    monitors[0].update(scale=1, vrr=True)
    live = parse_monitors(monitors)
    with pytest.raises(MonarchError, match="Cannot infer VRR policy"):
        Layout.capture(live)
    captured = Layout.capture(live, vrr_policies={live[0].name: 1})
    assert captured.outputs[0].vrr == 1


@pytest.mark.parametrize("persist", [False, True])
def test_guard_vrr_keep_baseline_capture_and_client_loss_recovery(guard_setup, persist):
    coordinator, store, baseline, desired, state = guard_setup
    capable(state)
    on = on_layout(desired)

    async def run():
        preview = await coordinator.preview(store, on, seconds=15)
        assert on.matches(parse_monitors(json.loads(state.read_text())["monitors"]))
        assert (await preview.decide(keep=True, persist=persist))["state"] == "kept"
        assert store.read()[0].outputs[0].vrr == int(persist)
        live = parse_monitors(json.loads(state.read_text())["monitors"])
        known, _ = known_baseline(
            store, coordinator.paths, session_token(coordinator.session), live
        )
        assert known == on
        captured = Layout.capture(live, vrr_policies={o.name: o.vrr for o in known.outputs})
        assert captured == on
        off = Layout(tuple(replace(o, vrr=0) for o in on.outputs))
        preview = await coordinator.preview(store, off, seconds=10)
        assert (await preview.disconnect())["state"] == "reverted"
        assert on.matches(parse_monitors(json.loads(state.read_text())["monitors"]))
        assert store.read()[0].outputs[0].vrr == int(persist)

    asyncio.run(run())


def test_timeout_restores_vrr_and_byte_exact_legacy_disk(guard_setup):
    coordinator, store, baseline, desired, state = guard_setup
    capable(state)
    legacy = render(baseline, legacy=True)
    store.monitors.write_bytes(legacy)

    async def run():
        preview = await coordinator.preview(store, on_layout(desired), seconds=3)
        assert (await preview.wait())["state"] == "reverted"
        assert baseline.matches(parse_monitors(json.loads(state.read_text())["monitors"]))
        assert read_private(store.monitors) == legacy

    asyncio.run(run())


def test_failed_persistence_reload_restores_policy_and_old_module(guard_setup):
    coordinator, store, baseline, desired, state = guard_setup
    capable(state)
    original = read_private(store.monitors)

    async def run():
        preview = await coordinator.preview(store, on_layout(desired), seconds=15)
        raw = json.loads(state.read_text())
        raw["fail_at"] = raw["mutations"] + 1
        state.write_text(json.dumps(raw))
        result = await preview.decide(keep=True, persist=True)
        assert result["state"] == "reverted"
        assert baseline.matches(parse_monitors(json.loads(state.read_text())["monitors"]))
        assert read_private(store.monitors) == original

    asyncio.run(run())


def test_incapable_output_rejected_before_any_guard_mutation(guard_setup):
    coordinator, store, baseline, desired, state = guard_setup

    async def run():
        with pytest.raises(MonarchError, match="Preview did not start"):
            await coordinator.preview(store, on_layout(desired), seconds=5)

    asyncio.run(run())
    assert json.loads(state.read_text()).get("mutations", 0) == 0


def test_legacy_profile_catalog_gets_backup_before_layout_migration(tmp_path, monitors):
    monitors[0]["scale"] = 1
    layout = Layout.capture(parse_monitors(monitors))
    store = ProfileStore(tmp_path / "catalog")
    saved = store.save("Legacy", layout)
    value = {"schema_version": 2, "profiles": [dict(saved.to_dict(), layout=legacy_data(layout))]}
    write_json(store.path, value)
    original = read_private(store.path)
    assert store.list()[0].layout == layout
    store.save("Legacy", on_layout(layout), identifier=saved.id)
    backup = store.directory / f"layout-schema-1-backup-{digest(original)}.json"
    assert read_private(backup) == original
    assert store.list()[0].layout.outputs[0].vrr == 1


def test_old_pending_journal_can_still_restore_legacy_bytes(setup_transaction):
    from monarch.services.transaction import Transaction

    tx, backend, store, baseline, desired = setup_transaction
    original = render(baseline, legacy=True)
    store.monitors.write_bytes(original)

    async def run():
        await tx.prepare(store, desired, store.root, 10)
        await tx.apply()
        record = tx.paths.status()
        record["baseline"] = legacy_data(baseline)
        record["desired"] = legacy_data(desired)
        record["candidate_digest"] = digest(render(desired, legacy=True))
        write_json(tx.paths.journal, record)
        await Transaction(backend, tx.paths, lambda: "same-session").recover()
        assert tx.paths.status()["status"] == "reverted"
        assert baseline.matches(backend.live)
        assert read_private(store.monitors) == original

    asyncio.run(run())


def test_acknowledged_but_ineffective_vrr_change_is_rejected_and_rolled_back(guard_setup):
    coordinator, store, baseline, desired, state = guard_setup
    capable(state)
    raw = json.loads(state.read_text())
    raw["ignore_vrr"] = True
    state.write_text(json.dumps(raw))

    async def run():
        with pytest.raises(MonarchError, match="Preview did not start"):
            await coordinator.preview(store, on_layout(desired), seconds=10)
        assert coordinator.paths.status()["status"] == "reverted"
        assert "VRR requested On, observed Off" in coordinator.paths.status()["failure"]
        assert baseline.matches(parse_monitors(json.loads(state.read_text())["monitors"]))

    asyncio.run(run())


def test_partial_apply_failure_after_vrr_enable_restores_off_policy(guard_setup):
    coordinator, store, baseline, desired, state = guard_setup
    capable(state)
    raw = json.loads(state.read_text())
    # Reload + baseline refresh/final/disabled + desired refresh/final; fail next write.
    raw["fail_at"] = 7
    raw["vrr_rule_cache"] = True
    state.write_text(json.dumps(raw))

    async def run():
        with pytest.raises(MonarchError, match="Preview did not start"):
            await coordinator.preview(store, on_layout(desired), seconds=10)
        assert coordinator.paths.status()["status"] == "reverted"
        assert baseline.matches(parse_monitors(json.loads(state.read_text())["monitors"]))

    asyncio.run(run())


def test_topology_rebase_retains_confirmed_runtime_only_vrr_by_identity(setup_transaction):
    from monarch.services.transaction import Transaction

    tx, backend, store, baseline, desired = setup_transaction
    backend.live = tuple(
        replace(m, advanced=replace(m.advanced, vrr_capable=True)) for m in backend.live
    )
    on = on_layout(baseline)

    async def run():
        await tx.prepare(store, on, store.root, 15)
        await tx.apply()
        await tx.keep(False)
        extra = replace(
            backend.live[0],
            name="EXTRA",
            serial="new-device",
            x=4000,
            advanced=replace(backend.live[0].advanced, vrr_active=False, vrr_capable=False),
        )
        backend.live += (extra,)
        desired = Layout.capture(backend.live, vrr_policies={on.outputs[0].name: 1})
        second = Transaction(backend, tx.paths, lambda: "same-session")
        await second.prepare(store, desired, store.root, 15, allow_topology_rebase=True)
        assert second.record["baseline"]["outputs"][0]["vrr"] == 1
        await second.apply()
        await second.rollback("test_rebase")
        assert second.paths.status()["status"] == "reverted"
        assert backend.live[0].advanced.vrr_active is True
        assert store.read()[0] == baseline

    asyncio.run(run())


@pytest.mark.parametrize("persist", [False, True])
def test_native_vrr_only_cache_quirk_keep_revert_and_persistence(guard_setup, persist):
    coordinator, store, baseline, desired, state = guard_setup
    capable(state)
    raw = json.loads(state.read_text())
    raw["vrr_rule_cache"] = True
    state.write_text(json.dumps(raw))
    on = on_layout(baseline)  # VRR is the ONLY requested change.

    async def run():
        preview = await coordinator.preview(store, on, seconds=15)
        assert on.matches(parse_monitors(json.loads(state.read_text())["monitors"]))
        assert (await preview.decide(keep=True, persist=persist))["state"] == "kept"
        off = baseline
        preview = await coordinator.preview(store, off, seconds=15)
        assert off.matches(parse_monitors(json.loads(state.read_text())["monitors"]))
        assert (await preview.decide(keep=False))["state"] == "reverted"
        assert on.matches(parse_monitors(json.loads(state.read_text())["monitors"]))
        assert store.read()[0] == (on if persist else baseline)

    asyncio.run(run())


def test_external_edit_between_vrr_refresh_stages_prevents_final_write(setup_transaction):
    tx, backend, store, baseline, desired = setup_transaction
    backend.vrr_refresh_required = True
    backend.live = tuple(
        replace(m, advanced=replace(m.advanced, vrr_capable=True)) for m in backend.live
    )
    original = read_private(store.monitors)
    modified = original + b"-- external change\n"
    original_set = backend.set_output
    calls_at_edit = []

    async def change_after_refresh(output):
        await original_set(output)
        if output.name == baseline.outputs[0].name and output.x == baseline.outputs[0].x + 1:
            store.monitors.write_bytes(modified)
            calls_at_edit.append(len(backend.calls))

    backend.set_output = change_after_refresh

    async def run():
        await tx.prepare(store, baseline, store.root, 10)
        with pytest.raises(MonarchError):
            await tx.apply()
        assert calls_at_edit and len(backend.calls) == calls_at_edit[0]
        await tx.rollback("external_edit")
        assert tx.paths.status()["status"] == "recovery_required"
        assert read_private(store.monitors) == modified
        assert len(backend.calls) == calls_at_edit[0]

    asyncio.run(run())
