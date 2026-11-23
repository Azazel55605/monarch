#!/usr/bin/env python3
"""Native profiles/theme acceptance inside a disposable nested compositor only."""

import asyncio
import json
import os
import pty
import select
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

from probe_recovery import nested_session, prepare_baseline

from monarch.domain.layout import Layout
from monarch.storage.profiles import ProfileStore


def run(*, cycle_disabled_output: bool = False) -> None:
    with nested_session() as (session, env, store, root):
        writer, baseline = asyncio.run(prepare_baseline(session, env, store))
        presentation = Layout(
            tuple(
                replace(o, scale=1.25)
                if o.name == "MONARCH-A"
                else replace(o, enabled=False)
                if o.name == "MONARCH-B" and cycle_disabled_output
                else o
                for o in baseline.outputs
            )
        )
        portrait = Layout(
            tuple(replace(o, transform=1) if o.name == "MONARCH-B" else o for o in baseline.outputs)
        )
        profiles = ProfileStore(root / "profiles")
        desk = profiles.save("Desk", baseline)
        talk = profiles.save("Presentation", presentation)
        rotate = profiles.save("Portrait", portrait)
        export = root / "export.json"
        profiles.export_file(export)
        imported = ProfileStore(root / "imported").import_file(export)
        assert len(imported) == 3
        lock = (session.directory / "hyprland.lock").read_text().splitlines()
        os.environ.update(env)
        os.environ["WAYLAND_DISPLAY"] = lock[1]
        os.environ["QT_QPA_PLATFORM"] = "wayland"
        from monarch.ui.theme import ThemeController, discover_system_plugins

        plugins = discover_system_plugins()
        from PySide6.QtCore import QSettings, QTimer
        from PySide6.QtWidgets import QApplication, QStyleFactory, QSystemTrayIcon

        from monarch.ui.app import configure_app
        from monarch.ui.window import MainWindow
        from monarch.ui.worker import BackendThread

        app = QApplication([])
        configure_app(app)
        theme = ThemeController(app, QSettings(str(root / "theme.ini"), QSettings.Format.IniFormat))
        backend = BackendThread(session=session, managed=store.directory, env=env)
        backend.profile_store = profiles
        window = MainWindow(backend, quit_on_close=True, theme=theme, tray_enabled=True)
        window.setScreen(next(s for s in app.screens() if s.name() == "MONARCH-A"))
        results = {
            "styles": QStyleFactory.keys(),
            "active_style": app.style().objectName(),
            "system_plugin_roots": plugins,
            "tray_host_available": QSystemTrayIcon.isSystemTrayAvailable(),
            "three_profile_import_export": True,
        }
        window.show()
        backend.start()
        stage = 0
        previous = -1
        deadline = time.monotonic() + 100
        completed = []
        errors = []
        backend.completed.connect(completed.append)

        def finish():
            window._closing = True
            window.close()

        def map_if_needed():
            dialog = getattr(window, "mapping_dialog", None)
            if dialog is not None and dialog.isVisible():
                for name, choice in dialog.choices.items():
                    choice.setCurrentIndex(choice.findData(name))
                assert dialog.ok.isEnabled()
                dialog.submit()
                results["explicit_virtual_identity_mapping"] = True

        def tick():
            nonlocal stage, previous
            try:
                if stage != previous:
                    print(
                        f"native profiles stage {stage}: {window.banner.text()}",
                        file=sys.stderr,
                        flush=True,
                    )
                    previous = stage
                if time.monotonic() > deadline:
                    raise RuntimeError(f"Timed out at stage {stage}: {window.banner.text()}")
                if stage in {1, 3, 6, 8} and "Preview did not start" in window.banner.text():
                    raise RuntimeError(window.banner.text())
                map_if_needed()
                if stage == 0 and window.ready and window.profile_bar.selector.count() == 3:
                    window.load_profile(talk.id, True)
                    stage = 1
                elif stage == 1 and window.confirmation:
                    window.confirmation.choose(True)
                    stage = 2
                elif stage == 2 and completed and not window.model.busy and not window.model.dirty:
                    assert completed[-1]["state"] == "kept"
                    results["presentation_kept"] = True
                    window.load_profile(rotate.id, True)
                    stage = 3
                elif stage == 3 and window.confirmation:
                    window.confirmation.choose(False)
                    stage = 4
                elif stage == 4 and len(completed) == 2 and not window.model.busy:
                    assert completed[-1]["state"] == "reverted"
                    results["portrait_reverted"] = True
                    window.discard_edits()
                    stage = 5
                elif stage == 5 and not window.model.dirty:
                    window.persist.setChecked(True)
                    window.load_profile(rotate.id, True)
                    stage = 6
                elif stage == 6 and window.confirmation:
                    window.confirmation.choose(True)
                    stage = 7
                elif (
                    stage == 7
                    and len(completed) == 3
                    and not window.model.busy
                    and not window.model.dirty
                ):
                    assert completed[-1]["state"] == "kept"
                    assert store.read()[0] == portrait
                    results["portrait_kept_and_persisted"] = True
                    artifact = Path("/tmp/monarch-phase4")
                    artifact.mkdir(exist_ok=True)
                    assert window.grab().save(str(artifact / "editor.png"))
                    # Trigger the actual menu action; it surfaces the GUI, maps
                    # identities and requires confirmation just like the selector.
                    next(a for a in window.tray_menu.actions() if a.text() == desk.name).trigger()
                    stage = 8
                elif stage == 8 and window.confirmation:
                    assert not window.persist.isChecked()
                    results["tray_requires_visible_confirmation"] = True
                    timer.stop()
                    finish()  # EOF must restore the kept portrait baseline.
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
        assert portrait.matches(asyncio.run(writer.observe()))
        results["third_profile_close_restores_previous"] = True
        bindings = [arg for o in baseline.outputs for arg in ("--map", f"{o.name}={o.name}")]
        command = [
            sys.executable,
            "-m",
            "monarch",
            "profile",
            "--store",
            str(profiles.directory),
            "switch",
            desk.id,
            "--terminal",
            "--directory",
            str(store.directory),
            *bindings,
        ]
        master, slave = pty.openpty()
        process = subprocess.Popen(
            command, env=env, stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        os.close(slave)
        try:
            assert select.select([process.stdout], [], [], 20)[0], "CLI did not reach confirmation"
            assert "Preview active" in process.stdout.readline()
            os.write(master, b"keep\n")
            output, error = process.communicate(timeout=20)
            assert process.returncode == 0, error
            assert json.loads(output.splitlines()[-1])["state"] == "kept"
        finally:
            os.close(master)
            if process.poll() is None:
                process.kill()
                process.wait()
        assert baseline.matches(asyncio.run(writer.observe()))
        results["native_terminal_profile_keep"] = True
        results["parent_monitor_mutations"] = 0
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle-disabled-output", action="store_true")
    run(cycle_disabled_output=parser.parse_args().cycle_disabled_output)
