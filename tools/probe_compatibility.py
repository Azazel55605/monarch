#!/usr/bin/env python3
"""Read-only advanced UI/diagnostics and basic guard regression in a nested compositor."""

import asyncio
import json
import os
import time
from dataclasses import replace
from pathlib import Path

from probe_recovery import nested_session, prepare_baseline

from monarch.domain.layout import Layout
from monarch.services.coordinator import Coordinator


def run() -> None:
    with nested_session() as (session, env, store, root):
        writer, baseline = asyncio.run(prepare_baseline(session, env, store))
        desired = Layout(
            tuple(replace(o, scale=1.25) if o.name == "MONARCH-A" else o for o in baseline.outputs)
        )

        async def regression():
            preview = await Coordinator(session, env=env).preview(store, desired, seconds=10)
            assert (await preview.decide(keep=False))["state"] == "reverted"
            assert baseline.matches(await writer.observe())

        asyncio.run(regression())
        mirrored = Layout(
            tuple(
                replace(o, mirror="MONARCH-A") if o.name == "MONARCH-B" else o
                for o in baseline.outputs
            )
        )

        async def mirror_regression():
            preview = await Coordinator(session, env=env).preview(store, mirrored, seconds=10)
            assert mirrored.matches(await writer.observe())
            assert (await preview.decide(keep=False))["state"] == "reverted"

        asyncio.run(mirror_regression())
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
        worker = BackendThread(session=session, managed=store.directory, env=env)
        theme = ThemeController(app, QSettings(str(root / "theme.ini"), QSettings.Format.IniFormat))
        window = MainWindow(worker, theme=theme, quit_on_close=True)
        window.setScreen(next(s for s in app.screens() if s.name() == "MONARCH-A"))
        window.show()
        worker.start()
        stage = 0
        deadline = time.monotonic() + 40
        errors = []
        results = {
            "basic_guard_apply_and_revert": True,
            "native_mirror_id_resolution_and_revert": True,
        }
        artifact = Path(os.environ.get("MONARCH_PROBE_ARTIFACT_DIR", "/tmp/monarch-phase6"))
        artifact.mkdir(exist_ok=True)

        def finish():
            window._closing = True
            window.close()

        def tick():
            nonlocal stage
            try:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"Read-only native probe timed out at {stage}")
                if stage == 0 and window.ready:
                    from monarch.resources import APP_ID
                    from monarch.ui.help import HelpDialog

                    assert app.desktopFileName() == APP_ID
                    assert not app.windowIcon().pixmap(48, 48).isNull()
                    for notices in (False, True):
                        help_dialog = HelpDialog(notices=notices, parent=window)
                        help_dialog.show()
                        assert len(help_dialog.document.toPlainText()) > 500
                        help_dialog.close()
                    results["native_desktop_identity_icon_and_offline_help"] = True
                    window.select_display("MONARCH-A")
                    window.show_advanced()
                    stage = 1
                elif stage == 1 and window.advanced_dialog.isVisible():
                    dialog = window.advanced_dialog
                    assert all(
                        dialog.table.item(row, 2).text() == "Unavailable" for row in range(5)
                    )
                    assert dialog.grab().save(str(artifact / "advanced.png"))
                    dialog.accept()
                    results["native_advanced_controls_gated"] = True
                    window.show_diagnostics()
                    stage = 2
                elif stage == 2 and window.diagnostics_dialog.data:
                    data = window.diagnostics_dialog.data
                    encoded = json.dumps(data)
                    assert str(root) not in encoded and session.signature not in encoded
                    assert all(m.name not in encoded for m in window.model.inspection.monitors)
                    assert data["redacted"] and data["integration"]["code"] == "verified"
                    window.diagnostics_dialog.save_requested.emit(root / "support.json", data)
                    assert window.diagnostics_dialog.grab().save(str(artifact / "diagnostics.png"))
                    stage = 3
                elif stage == 3 and (root / "support.json").exists():
                    assert (root / "support.json").stat().st_mode & 0o777 == 0o600
                    results["native_redacted_report_and_private_export"] = True
                    window.diagnostics_dialog.accept()
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
        worker.shutdown()
        worker.wait()
        if errors:
            raise RuntimeError(errors[0])
        assert baseline.matches(asyncio.run(writer.observe()))
        results["parent_monitor_mutations"] = 0
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    run()
