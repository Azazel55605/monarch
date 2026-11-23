#!/usr/bin/env python3
"""Opt-in automation acceptance using virtual hotplug in a disposable compositor."""

import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from threading import Thread

from probe_recovery import nested_session, prepare_baseline

from monarch.domain.layout import Layout
from monarch.domain.policy import Policy, Rule
from monarch.storage.automation import PolicyStore
from monarch.storage.files import read_private
from monarch.storage.profiles import ProfileStore


def run() -> None:
    with nested_session() as (session, env, store, root):
        writer, baseline = asyncio.run(prepare_baseline(session, env, store))
        # Virtual outputs expose empty hardware identities. Explicit saved-port
        # binding is configured for this fixture; physical identity ambiguity
        # remains covered separately by the policy tests.
        target = Layout(
            tuple(
                replace(o, scale=1.25) if o.name == "MONARCH-A" else o
                for o in baseline.outputs
                if o.name != "MONARCH-B"
            )
        )
        profiles = ProfileStore(root / "profiles")
        profile = profiles.save("Mobile", target)
        policy = PolicyStore(profiles.directory)
        policy.write(Policy(True, (Rule(profile.id, connectors=True),)))
        startup_bytes = read_private(store.monitors)
        lock = (session.directory / "hyprland.lock").read_text().splitlines()
        os.environ.update(env)
        os.environ["WAYLAND_DISPLAY"] = lock[1]
        os.environ["QT_QPA_PLATFORM"] = "wayland"
        from monarch.ui.theme import ThemeController, discover_system_plugins

        discover_system_plugins()
        from PySide6.QtCore import QSettings, QTimer
        from PySide6.QtWidgets import QApplication

        from monarch.ui.app import configure_app
        from monarch.ui.window import MainWindow
        from monarch.ui.worker import BackendThread

        app = QApplication([])
        configure_app(app)
        backend = BackendThread(session=session, managed=store.directory, env=env)
        backend.profile_store = profiles
        window = MainWindow(
            backend,
            quit_on_close=True,
            tray_enabled=True,
            theme=ThemeController(
                app, QSettings(str(root / "theme.ini"), QSettings.Format.IniFormat)
            ),
        )
        window.setScreen(next(s for s in app.screens() if s.name() == "MONARCH-A"))
        completed = []
        backend.completed.connect(completed.append)
        window.show()
        backend.start()
        stage = 0
        previous = -1
        pause_started = 0.0
        deadline = time.monotonic() + 120
        errors = []
        results = {}

        def output(*arguments):
            def change():
                subprocess.run(
                    ["hyprctl", "-i", session.signature, "output", *arguments],
                    env=env,
                    capture_output=True,
                    timeout=10,
                    check=True,
                )

            Thread(target=change, daemon=True).start()

        def finish():
            window._closing = True
            window.close()

        def tick():
            nonlocal stage, previous, pause_started
            try:
                if previous != stage:
                    print(
                        f"native auto stage {stage}: {window.automatic_status.text()}",
                        file=sys.stderr,
                        flush=True,
                    )
                    previous = stage
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        f"Native automation timed out at {stage}: {window.banner.text()} / "
                        f"{window.automatic_status.text()}"
                    )
                if stage == 0 and window.ready and "No eligible" in window.automatic_status.text():
                    assert not completed and window.confirmation is None
                    results["no_match_preserves_layout"] = True
                    output("remove", "MONARCH-B")
                    stage = 1
                elif stage == 1 and window.confirmation:
                    assert not window._persist
                    window.confirmation.choose(True)
                    stage = 2
                elif stage == 2 and completed and not window.model.busy and not window.model.dirty:
                    assert completed[-1]["state"] == "kept" and completed[-1]["automatic"]
                    assert read_private(store.monitors) == startup_bytes
                    results["virtual_undock_automatic_preview_and_keep"] = True
                    results["topology_snapshot_preserves_startup_file"] = True
                    window.select_display("MONARCH-A")
                    window.scale.setValue(1)
                    window.start_preview()
                    stage = 3
                elif stage == 3 and window.confirmation:
                    window.confirmation.choose(True)
                    stage = 4
                elif (
                    stage == 4
                    and len(completed) == 2
                    and not window.model.busy
                    and not window.model.dirty
                ):
                    pause_started = time.monotonic()
                    stage = 5
                elif stage == 5 and time.monotonic() - pause_started > 3:
                    assert window.confirmation is None and len(completed) == 2
                    assert window.resume_automatic.isVisible()
                    results["manual_switch_pins_automatic_policy"] = True
                    backend.submit("automation-resume")
                    stage = 6
                elif stage == 6 and window.confirmation:
                    window.confirmation.choose(False)
                    stage = 7
                elif (
                    stage == 7
                    and len(completed) == 3
                    and not window.model.busy
                    and not window.model.dirty
                ):
                    assert completed[-1]["state"] == "reverted"
                    pause_started = time.monotonic()
                    stage = 8
                elif stage == 8 and time.monotonic() - pause_started > 3:
                    assert window.confirmation is None and len(completed) == 3
                    results["resume_revert_and_no_repeat"] = True
                    output("create", "headless", "MONARCH-B")
                    stage = 9
                elif (
                    stage == 9
                    and len(window.model.inspection.monitors) == 3
                    and "No eligible" in window.automatic_status.text()
                ):
                    results["virtual_dock_no_match_preserved"] = True
                    output("remove", "MONARCH-B")
                    stage = 10
                elif stage == 10 and window.confirmation:
                    window.confirmation.choose(True)
                    stage = 11
                elif (
                    stage == 11
                    and len(completed) == 4
                    and not window.model.busy
                    and not window.model.dirty
                ):
                    results["repeated_undock_reselects_once"] = True
                    artifact = Path("/tmp/monarch-phase5")
                    artifact.mkdir(exist_ok=True)
                    assert window.grab().save(str(artifact / "editor.png"))
                    timer.stop()
                    finish()
            except BaseException as exc:
                errors.append(repr(exc))
                timer.stop()
                finish()

        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(100)
        app.exec()
        backend.shutdown()
        backend.wait()
        if errors:
            raise RuntimeError(errors[0])
        assert target.matches(asyncio.run(writer.observe()))
        results["parent_monitor_mutations"] = 0
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    run()
