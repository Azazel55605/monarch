import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_guard import guard_setup as guard_setup

from monarch.backends.hyprland.inspector import Capabilities, Inspection
from monarch.backends.hyprland.session import ConfigLocation
from monarch.domain.monitors import parse_monitors
from monarch.domain.policy import Policy, Rule
from monarch.errors import MonarchError
from monarch.services.automation import Automation
from monarch.storage.automation import Autostart, PolicyStore, control, desktop_entry, pin
from monarch.storage.files import atomic_write, read_private
from monarch.storage.profiles import ProfileStore


@pytest.fixture
def automatic(guard_setup, tmp_path):
    coordinator, managed, baseline, desired, state = guard_setup
    store = ProfileStore(tmp_path / "profiles")
    profile = store.save("Desk", desired)
    policy = PolicyStore(store.directory)
    policy.write(Policy(True, (Rule(profile.id),)))
    engine = Automation(coordinator, store)
    monitors = parse_monitors(json.loads(state.read_text())["monitors"])
    inspection = Inspection(
        Capabilities("0.57.2", "lua", "wayland", True, True),
        ConfigLocation(managed.root, "test", True),
        monitors,
        (),
    )
    try:
        yield engine, inspection, profile, managed, desired
    finally:
        engine.close()


def offer(engine, inspection, now=0):
    assert engine.evaluate(inspection, idle=True, ready=True, now=now)[1] is None
    return engine.evaluate(inspection, idle=True, ready=True, now=now + 2)[1]


def test_stability_storms_feedback_decline_and_restart_suppression(automatic):
    engine, inspection, profile, _, _ = automatic
    for now in [0, 0.1, 0.4, 0.8, 1.4]:
        assert engine.evaluate(inspection, idle=True, ready=True, now=now)[1] is None
    assert engine.evaluate(inspection, idle=True, ready=True, now=2)[1].profile == profile
    # Self events never offer again while confirmation is pending.
    assert engine.evaluate(inspection, idle=True, ready=True, now=10)[1] is None
    engine.finish({"state": "reverted", "reason": "user_revert"}, now=10)
    assert engine.evaluate(inspection, idle=True, ready=True, now=1000)[1] is None
    engine.close()
    restarted = Automation(engine.coordinator, engine.profiles)
    try:
        assert offer(restarted, inspection, now=2000) is None
        pin(restarted.paths, False)
        assert offer(restarted, inspection, now=2010) is not None
    finally:
        restarted.close()


def test_backoff_is_bounded_and_three_failures_block_same_revision(automatic):
    engine, inspection, _, _, _ = automatic
    assert offer(engine, inspection) is not None
    for failures, now in [(1, 2), (2, 32), (3, 92)]:
        engine.finish({"state": "failed"}, now=now)
        assert engine.attempt["failures"] == failures
        assert engine.evaluate(inspection, idle=True, ready=True, now=now + 1)[1] is None
        result = engine.evaluate(
            inspection, idle=True, ready=True, now=now + 30 * 2 ** (failures - 1)
        )[1]
        assert (result is not None) == (failures < 3)
    assert engine.evaluate(inspection, idle=True, ready=True, now=10000)[1] is None


def test_manual_pin_single_owner_idle_and_policy_changes(automatic):
    engine, inspection, _, _, _ = automatic
    assert engine.evaluate(inspection, idle=False, ready=True, now=0)[1] is None
    second = Automation(engine.coordinator, engine.profiles)
    try:
        assert "Another" in second.evaluate(inspection, idle=True, ready=True, now=3)[0]["reason"]
        pin(engine.paths)
        assert offer(engine, inspection, now=10) is None
        assert control(engine.paths)["pinned"]
        pin(engine.paths, False)
        assert offer(engine, inspection, now=20) is not None
        PolicyStore(engine.profiles.directory).enabled(False)
        with pytest.raises(MonarchError, match="policy changed"):
            engine.authorize()
    finally:
        second.close()


def test_catalog_change_revokes_authorization(automatic):
    engine, inspection, profile, _, desired = automatic
    assert offer(engine, inspection) is not None
    engine.profiles.save("Changed", desired, identifier=profile.id)
    with pytest.raises(MonarchError, match="catalog changed"):
        engine.authorize()


def test_automatic_guard_keep_then_manual_preemption_restores_before_manual_switch(automatic):
    engine, inspection, _, managed, desired = automatic
    coordinator = engine.coordinator
    assert offer(engine, inspection) is not None

    async def run():
        handle = await coordinator.preview(
            managed, desired, seconds=10, automation=engine.authorize()
        )
        # A manual client revokes the auto guard and waits for its restoration.
        baseline = managed.read()[0]
        manual = await coordinator.preview(managed, baseline, seconds=10)
        assert (await handle.wait())["state"] == "reverted"
        assert (await manual.decide(keep=True))["state"] == "kept"
        assert control(engine.paths)["pinned"]

    asyncio.run(run())


def test_autostart_roundtrip_quoting_and_external_edit_preservation(tmp_path):
    store = PolicyStore(tmp_path / "config" / "monarch")
    store.write(Policy())
    startup = Autostart(store.directory)
    executable = '/tmp/a space/py$`"%thon'
    entry = desktop_entry(executable)
    assert b"%%" in entry and b'"-m" "monarch" "automation" "run"' in entry
    startup.set(True, executable=executable)
    assert startup.active()
    startup.set(True, executable=executable)
    startup.path.write_bytes(entry + b"# external edit\n")
    with pytest.raises(MonarchError, match="preserved"):
        startup.set(False)
    startup.path.write_bytes(entry)
    startup.set(False)
    assert not startup.path.exists() and not startup.active()
    startup.path.write_text("[Desktop Entry]\nName=Other\n")
    with pytest.raises(MonarchError, match="not overwritten"):
        startup.set(True)


def test_policy_future_schema_and_profile_lock_preserve_data(tmp_path):
    store = PolicyStore(tmp_path / "profiles")
    atomic_write(store.path, b'{"schema_version":99,"enabled":true,"rules":[]}')
    original = read_private(store.path)
    with pytest.raises(MonarchError):
        store.enabled(False)
    assert read_private(store.path) == original
    with ProfileStore(store.directory).locked():
        with pytest.raises(MonarchError, match="Another client"):
            store.write(Policy())


def test_topology_rebase_is_automatic_only_and_restores_captured_connected_layout(automatic):
    from monarch.domain.layout import Layout

    engine, inspection, profile, managed, desired = automatic
    state_path = Path(engine.coordinator.env["MONARCH_FAKE_STATE"])
    data = json.loads(state_path.read_text())
    data["monitors"] = data["monitors"][:1]  # Simulated unplug of the disabled second output.
    state_path.write_text(json.dumps(data))
    connected = parse_monitors(data["monitors"])
    desired = Layout((desired.outputs[0],))
    engine.profiles.save(profile.name, desired, identifier=profile.id)
    inspection = replace(inspection, monitors=connected)
    baseline = Layout.capture(connected)
    assert offer(engine, inspection) is not None

    async def run():
        # Existing manual adoption policy is unchanged.
        with pytest.raises(MonarchError):
            await engine.coordinator.preview(managed, desired, seconds=8)
        pin(engine.paths, False)
        assert offer(engine, inspection, now=10) is not None
        preview = await engine.coordinator.preview(
            managed, desired, seconds=8, automation=engine.authorize()
        )
        result = await preview.decide(keep=False)
        assert result["state"] == "reverted"
        current = parse_monitors(
            json.loads(await asyncio.to_thread(state_path.read_text))["monitors"]
        )
        assert baseline.matches(current)
        # Snapshot/revert did not rewrite the startup file for the old topology.
        assert len(managed.read()[0].outputs) == 2

    asyncio.run(run())


def test_same_topology_external_drift_is_not_adopted_and_revocation_allows_recovery(automatic):
    engine, inspection, _, managed, desired = automatic
    state_path = Path(engine.coordinator.env["MONARCH_FAKE_STATE"])
    data = json.loads(state_path.read_text())
    data["monitors"][0]["x"] = -50
    state_path.write_text(json.dumps(data))
    assert offer(engine, inspection) is not None

    async def run():
        with pytest.raises(MonarchError):
            await engine.coordinator.preview(
                managed, desired, seconds=8, automation=engine.authorize()
            )

    asyncio.run(run())


def test_disabling_policy_during_preview_reverts_and_does_not_persist(automatic):
    engine, inspection, _, managed, desired = automatic
    before = read_private(managed.monitors)
    assert offer(engine, inspection) is not None

    async def run():
        preview = await engine.coordinator.preview(
            managed, desired, seconds=8, automation=engine.authorize()
        )
        engine.store.enabled(False)
        result = await preview.wait()
        assert result["state"] == "reverted"
        assert read_private(managed.monitors) == before

    asyncio.run(run())


def test_reconnect_resume_requires_fresh_quiet_period_and_new_generation_cannot_replay(automatic):
    engine, inspection, _, _, _ = automatic
    assert engine.evaluate(inspection, idle=True, ready=True, now=0)[1] is None
    engine.stable_key = ""  # Watcher reconnect or resume gap invalidation.
    assert engine.evaluate(inspection, idle=True, ready=True, now=100)[1] is None
    assert engine.evaluate(inspection, idle=True, ready=True, now=102)[1] is not None
    socket = engine.coordinator.session.directory / ".socket.sock"
    socket.rename(socket.with_name("old.sock"))
    socket.touch()
    with pytest.raises(MonarchError, match="generation changed"):
        engine.evaluate(inspection, idle=True, ready=True, now=200)


def test_hotplug_cycle_resets_decline_but_disabled_owner_releases_session(automatic):
    engine, inspection, _, _, _ = automatic
    assert offer(engine, inspection) is not None
    engine.finish({"state": "reverted", "reason": "user_revert"}, now=3)
    assert engine.evaluate(inspection, idle=True, ready=True, now=10)[1] is None
    changed = replace(inspection, monitors=inspection.monitors[:-1])
    assert engine.evaluate(changed, idle=True, ready=True, now=12)[1] is None
    assert offer(engine, inspection, now=15) is not None
    engine.store.enabled(False)
    assert engine.evaluate(inspection, idle=True, ready=True, now=20)[1] is None
    assert engine.owner is None


def test_cli_policy_opt_in_lifecycle_and_offline_status(tmp_path, monkeypatch, capsys):
    from monarch.cli import main

    # Catalog operations are tested elsewhere; use a minimal real fixture here.
    from monarch.domain.layout import Layout, Output

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    directory = tmp_path / "config" / "monarch"
    profile = ProfileStore(directory).save(
        "Desk", Layout((Output("DP-1", "Example", "Panel", "DEMO", "1920x1080@60", 1, 0, 0, 0),))
    )
    assert main(["automation", "set-rule", "Desk", "--priority", "10"]) == 0
    assert not PolicyStore(directory).read().enabled
    assert main(["automation", "enable"]) == 0
    assert main(["automation", "status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["policy"]["enabled"] and status["runner"] is None
    assert main(["automation", "autostart", "enable"]) == 0
    assert Autostart(directory).active()
    assert main(["automation", "autostart", "disable"]) == 0
    assert not Autostart(directory).active()
    assert main(["automation", "disable"]) == 0
    assert main(["automation", "remove-rule", profile.id]) == 0
    assert PolicyStore(directory).read() == Policy()


def test_generated_desktop_entry_validates_with_spaces_and_percent(tmp_path):
    import shutil
    import subprocess

    validator = shutil.which("desktop-file-validate")
    if not validator:
        pytest.skip("desktop-file-utils is optional outside the native host")
    path = tmp_path / "monarch-automation.desktop"
    path.write_bytes(desktop_entry("/tmp/space and % symbols/python", tmp_path / "profile space"))
    result = subprocess.run([validator, str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
