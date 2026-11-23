#!/usr/bin/env python3
"""Run the real Qt editor inside a private nested Wayland compositor."""

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
from monarch.storage.files import atomic_write, digest, read_private
from monarch.storage.managed import Managed, render


def run() -> None:
    with nested_session(default_config=True) as (session, env, store, root):
        writer, baseline = asyncio.run(prepare_baseline(session, env, store))
        mixed = Layout(
            tuple(
                replace(o, scale=1.25)
                if o.name == "MONARCH-A"
                else replace(o, transform=1, x=1536)
                if o.name == "MONARCH-B"
                else o
                for o in baseline.outputs
            )
        )
        atomic_write(store.monitors, render(mixed), expected=digest(read_private(store.monitors)))

        async def settle():
            await asyncio.sleep(0.5)
            await writer.reload()
            for _ in range(30):
                if mixed.matches(await writer.observe()):
                    return
                await asyncio.sleep(0.1)
            raise RuntimeError("Mixed-scale virtual baseline did not settle.")

        asyncio.run(settle())
        lock = (session.directory / "hyprland.lock").read_text().splitlines()
        os.environ.update(env)
        os.environ["WAYLAND_DISPLAY"] = lock[1]
        os.environ["QT_QPA_PLATFORM"] = "wayland"
        os.environ["XDG_STATE_HOME"] = str(root / "state")
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        from monarch.ui.app import configure_app
        from monarch.ui.window import MainWindow
        from monarch.ui.worker import BackendThread

        app = QApplication([])
        configure_app(app)
        backend = BackendThread(session=session, env=env)
        window = MainWindow(backend, quit_on_close=True)
        screen = next(screen for screen in app.screens() if screen.name() == "MONARCH-A")
        window.setScreen(screen)
        window.show()
        backend.start()
        stage = 0
        last_stage = -1
        identify_started = 0.0
        deadline = time.monotonic() + 100
        errors = []
        results = {}
        completed = []
        backend.completed.connect(completed.append)

        def finish():
            window.identification.close()
            window._closing = True
            window.close()

        def tick():
            nonlocal stage, last_stage, identify_started
            if stage != last_stage:
                print(
                    f"native GUI stage {stage}: {window.banner.text()}", file=sys.stderr, flush=True
                )
                last_stage = stage
            try:
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        f"Native GUI probe timed out at stage {stage}: {window.banner.text()}"
                    )
                if stage == 0 and window.model.inspection is not None and window.ready:
                    window.setup_integration()
                    window.integration.dependencies.addItem(str(store.monitors))
                    window.integration.approval.setChecked(True)
                    window.integration.request_preview()
                    stage = 1
                elif (
                    stage == 1
                    and window.integration
                    and window.integration.install_button.isEnabled()
                ):
                    window.integration.request_install()
                    stage = 2
                elif (
                    stage == 2
                    and window.integration is None
                    and backend.directory == store.directory / "monarch"
                    and window.ready
                ):
                    results["reviewed_desktop_integration"] = True
                    window.select_display("MONARCH-B")
                    window.scale.setValue(1.5)
                    assert window.apply.isEnabled(), window.validation.text()
                    window.persist.setChecked(True)
                    window.start_preview()
                    stage = 3
                elif stage == 3 and window.confirmation:
                    window.confirmation.choose(True)
                    stage = 4
                elif (
                    stage == 4
                    and completed
                    and completed[-1]["state"] == "kept"
                    and not window.model.busy
                    and not window.model.dirty
                ):
                    saved = Managed(backend.directory).read()[0]
                    assert next(o for o in saved.outputs if o.name == "MONARCH-B").scale == 1.5
                    results["gui_keep_and_persistence"] = True
                    window.rotation.setCurrentIndex(3)
                    window.start_preview()
                    stage = 5
                elif stage == 5 and window.confirmation:
                    window.confirmation.choose(False)
                    stage = 6
                elif stage == 6 and completed[-1]["state"] == "reverted" and not window.model.busy:
                    results["gui_revert"] = True
                    window.discard_edits()
                    stage = 7
                elif stage == 7 and not window.model.dirty and window.ready:
                    screens = {screen.name(): screen.devicePixelRatio() for screen in app.screens()}
                    assert len(screens) == 2, screens
                    results["native_mixed_dpi_screens"] = screens
                    window.identify()
                    assert len(window.identification.windows) == 2
                    results["per_output_identification"] = True
                    results["window_fractional_scale"] = window.windowHandle().devicePixelRatio()
                    results["configured_monitor_scales"] = {
                        o.name: o.scale for o in window.model.observed.outputs if o.enabled
                    }
                    assert len(set(results["configured_monitor_scales"].values())) >= 2
                    identify_started = time.monotonic()
                    stage = 9
                elif stage == 9 and time.monotonic() - identify_started > 0.4:
                    actual_screens = {
                        w.windowHandle().screen().name() for w in window.identification.windows
                    }
                    assert actual_screens == {"MONARCH-A", "MONARCH-B"}, actual_screens
                    window.identification.close()
                    window.select_display("MONARCH-A")
                    Path("/tmp/monarch-phase3").mkdir(exist_ok=True)
                    assert window.grab().save("/tmp/monarch-phase3/editor.png")
                    window.position_x.setValue(-100)

                    def unplug():
                        subprocess.run(
                            ["hyprctl", "-i", session.signature, "output", "remove", "MONARCH-B"],
                            env=env,
                            capture_output=True,
                            timeout=5,
                            check=True,
                        )

                    Thread(target=unplug, daemon=True).start()
                    stage = 8
                elif stage == 8 and window.model.stale:
                    assert window.model.dirty
                    assert not window.apply.isEnabled()
                    assert "MONARCH-B" in {o.name for o in window.model.draft.outputs}
                    assert "MONARCH-B" not in {m.name for m in window.model.inspection.monitors}
                    results["hotplug_preserves_stale_edits"] = True
                    results["parent_monitor_mutations"] = 0
                    timer.stop()
                    finish()
            except BaseException as error:
                print(f"native GUI failed: {error}", file=sys.stderr, flush=True)
                errors.append(str(error))
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
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    run()
