import time
from dataclasses import replace

import pytest
from test_guard import guard_setup as guard_setup

pytest.importorskip("PySide6")
from PySide6.QtCore import QPoint, Qt

from monarch.backends.hyprland.inspector import Capabilities, Inspection
from monarch.backends.hyprland.session import ConfigLocation
from monarch.domain.monitors import parse_monitors
from monarch.ui.dialogs import ConfirmationDialog, IntegrationDialog
from monarch.ui.model import EditorModel, snap
from monarch.ui.window import MainWindow


@pytest.fixture
def inspection(monitors):
    monitors[0]["scale"] = 1
    return Inspection(
        Capabilities("0.57.2", "lua", "wayland", True, True),
        ConfigLocation(None, "test fixture"),
        parse_monitors(monitors),
        (),
    )


@pytest.fixture
def window(qtbot, inspection):
    widget = MainWindow()
    qtbot.addWidget(widget)
    widget.receive(inspection)
    widget.receive_ownership({"ready": True, "reason": "Synthetic monitor management is ready."})
    widget.show()
    qtbot.waitExposed(widget)
    yield widget
    if widget.confirmation:
        widget.confirmation.finish()
    if widget.integration:
        widget.integration.accept()
    widget.close()


def test_numeric_edit_updates_geometry_dirty_and_validation(window, qtbot):
    assert not window.apply.isEnabled()
    window.scale.setValue(2)
    assert window.model.dirty
    assert window.model.draft.outputs[0].scale == 2
    assert window.apply.isEnabled()
    window.position_x.setValue(-1280)
    assert window.model.draft.outputs[0].x == -1280
    window.scale.setValue(1.5)
    assert "integer logical" in window.validation.text()
    assert not window.apply.isEnabled()
    window.discard_edits()
    assert not window.model.dirty


def test_display_controls_keep_parity_and_forbid_all_disabled(window, qtbot):
    window.rotation.setCurrentIndex(1)
    assert window.model.draft.outputs[0].transform == 1
    window.refresh_rate.setCurrentIndex(1)
    assert window.model.draft.outputs[0].mode.endswith("@59.95")
    window.enabled.setChecked(False)
    assert "usable" in window.validation.text()
    assert not window.apply.isEnabled()
    window.discard_edits()
    window.select_display("HDMI-EXAMPLE")
    window.enabled.setChecked(True)
    window.mirror.setCurrentIndex(window.mirror.findData("DP-EXAMPLE"))
    assert window.model.output("HDMI-EXAMPLE").mirror == "DP-EXAMPLE"
    assert not window.position_x.isEnabled()


def test_keyboard_canvas_and_numeric_positions_share_model(window, qtbot):
    window.canvas.setFocus()
    window.canvas.select("DP-EXAMPLE")
    old = window.model.output("DP-EXAMPLE").x
    qtbot.keyClick(window.canvas.viewport(), Qt.Key.Key_Right)
    qtbot.waitUntil(lambda: window.model.output("DP-EXAMPLE").x == old + 1)
    assert window.position_x.value() == old + 1


def test_drag_changes_position_without_applying(window, qtbot):
    item = window.canvas.items_by_name["DP-EXAMPLE"]
    point = window.canvas.mapFromScene(item.sceneBoundingRect().center())
    old = window.model.output("DP-EXAMPLE").x
    qtbot.mousePress(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    qtbot.mouseMove(window.canvas.viewport(), point + QPoint(40, 25), delay=30)
    qtbot.mouseRelease(
        window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=point + QPoint(40, 25)
    )
    qtbot.waitUntil(lambda: window.model.output("DP-EXAMPLE").x != old)
    assert window.model.dirty
    assert not window.model.busy


def test_hotplug_preserves_draft_and_revalidation_blocks_missing_outputs(window, inspection):
    window.position_x.setValue(-900)
    changed = replace(inspection, monitors=inspection.monitors[:1])
    window.receive(changed)
    assert window.model.stale
    assert window.model.output("DP-EXAMPLE").x == -900
    assert "missing" in window.displays.item(1).text()
    assert not window.apply.isEnabled()
    window.revalidate()
    assert not window.apply.isEnabled()
    window.discard_edits()
    assert len(window.model.draft.outputs) == 1
    assert not window.model.stale


def test_pending_preview_locks_fields_and_uses_guard_deadline(window, qtbot):
    window.scale.setValue(2)
    with qtbot.waitSignal(window.preview_requested):
        window.start_preview()
    assert window.model.busy and not window.properties.isEnabled()
    window.preview_pending(time.monotonic() + 0.2)
    dialog = window.confirmation
    qtbot.waitUntil(lambda: not dialog.keep.isEnabled(), timeout=1500)
    assert "guard is restoring" in dialog.countdown.text()
    assert not window.apply.isEnabled()
    window.preview_complete({"state": "reverted", "reason": "deadline_elapsed"})
    assert not window.model.busy
    assert window.confirmation is None


def test_dialog_keep_is_explicit_and_binds_persistence(qtbot):
    dialog = ConfirmationDialog(time.monotonic() + 10, True)
    qtbot.addWidget(dialog)
    dialog.show()
    with qtbot.waitSignal(dialog.decision) as signal:
        qtbot.mouseClick(dialog.keep, Qt.MouseButton.LeftButton)
    assert signal.args == [True, True]
    assert not dialog.keep.isEnabled()
    dialog.finish()


def test_integration_requires_review_and_invalidates_after_file_selection(qtbot, tmp_path):
    dialog = IntegrationDialog(tmp_path / "hyprland.lua")
    qtbot.addWidget(dialog)
    dialog.show()
    from monarch.storage.integration import IntegrationPlan

    with qtbot.waitSignal(dialog.prepare):
        dialog.request_preview()
    assert not dialog.install_button.isEnabled()
    dialog.show_plan(IntegrationPlan(tmp_path / "hyprland.lua", b"-- sample\n", ()))
    assert not dialog.install_button.isEnabled()
    dialog.approval.setChecked(True)
    assert dialog.install_button.isEnabled()
    dialog.root.setText(str(tmp_path / "other.lua"))
    assert not dialog.install_button.isEnabled()
    dialog.accept()


def test_non_mutating_initial_inspection_and_no_session_error(qtbot, inspection):
    widget = MainWindow()
    qtbot.addWidget(widget)
    widget.receive(inspection)
    assert not widget.apply.isEnabled()
    widget.show_error("No Hyprland session. Start from Hyprland.")
    assert "No Hyprland session" in widget.banner.text()
    assert not widget.apply.isEnabled()


def test_snap_and_draft_model_revalidation(inspection):
    model = EditorModel()
    model.receive(inspection)
    model.update("HDMI-EXAMPLE", enabled=True, transform=0)
    x, y = snap(model.draft, "HDMI-EXAMPLE", 850, 3)
    assert x == 853 and y == 0
    model.update("DP-EXAMPLE", x=-1000)
    model.receive(
        replace(inspection, monitors=tuple(replace(m, x=m.x + 1) for m in inspection.monitors))
    )
    assert model.stale
    model.revalidate()
    assert not model.stale and model.dirty


# Reuse the synthetic transport/process fixture. No live compositor is involved.


def test_real_worker_routes_gui_keep_and_close_through_guard(qtbot, guard_setup):
    from monarch.ui.worker import BackendThread

    coordinator, store, baseline, desired, state = guard_setup
    env = dict(coordinator.env, XDG_STATE_HOME=str(coordinator.state_home))
    worker = BackendThread(
        session=coordinator.session,
        env=env,
        managed=store.directory,
        executable=coordinator.executable,
    )
    widget = MainWindow(worker)
    qtbot.addWidget(widget)
    widget.show()
    worker.start()
    try:
        qtbot.waitUntil(lambda: widget.ready and widget.model.inspection is not None, timeout=10000)
        widget.scale.setValue(2)
        widget.persist.setChecked(True)
        widget.start_preview()
        qtbot.waitUntil(lambda: widget.confirmation is not None, timeout=10000)
        assert not widget.model.stale
        widget.confirmation.choose(True)
        qtbot.waitUntil(lambda: not widget.model.busy and not widget.model.dirty, timeout=10000)
        assert store.read()[0].outputs[0].scale == 2
        widget.position_x.setValue(-1280)
        widget.start_preview()
        qtbot.waitUntil(lambda: widget.confirmation is not None, timeout=10000)
        widget.close()
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=15000)
        assert coordinator.paths.status()["status"] == "reverted"
    finally:
        widget._closing = True
        if widget.confirmation:
            widget.confirmation.finish()
        worker.shutdown()
        worker.wait(15000)
        widget.close()


def test_saving_an_unchanged_confirmed_layout_is_available(window):
    assert not window.model.dirty
    window.persist.setChecked(True)
    assert window.apply.isEnabled()
    assert window.apply.text() == "Save current layout"


def test_disabled_outputs_have_their_own_canvas_lane(window):
    active = window.canvas.items_by_name["DP-EXAMPLE"].sceneBoundingRect()
    disabled = window.canvas.items_by_name["HDMI-EXAMPLE"].sceneBoundingRect()
    assert not active.intersects(disabled)


def test_dark_palette_remains_readable(window, qtbot, tmp_path):
    from PySide6.QtGui import QColor, QPalette

    palette = window.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#202124"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#161719"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#eeeeee"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
    window.setPalette(palette)
    window.canvas.viewport().update()
    qtbot.wait(20)
    assert window.canvas.viewport().palette().text().color().lightness() > 200
    assert window.grab().save(str(tmp_path / "dark-editor.png"))


def test_immediate_window_close_during_worker_startup_finishes(qtbot, guard_setup):
    from monarch.ui.worker import BackendThread

    coordinator, store, baseline, desired, state = guard_setup
    worker = BackendThread(
        session=coordinator.session,
        managed=store.directory,
        env=dict(coordinator.env, XDG_STATE_HOME=str(coordinator.state_home)),
        executable=coordinator.executable,
    )
    widget = MainWindow(worker)
    qtbot.addWidget(widget)
    widget.show()
    worker.start()
    widget.close()
    qtbot.waitUntil(lambda: not worker.isRunning(), timeout=10000)
    widget._closing = True
    widget.close()


def test_position_edits_preserve_nonterminating_scale_precision(window, inspection):
    fractional = replace(
        inspection, monitors=(replace(inspection.monitors[0], scale=4 / 3), inspection.monitors[1])
    )
    window.model.draft = None
    window.model.observed = None
    window.receive(fractional)
    window.position_x.setValue(-1920)
    assert window.model.draft.outputs[0].scale == 4 / 3
    assert not window.model.error()


def test_unknown_current_mode_is_not_silently_replaced(window, inspection):
    from decimal import Decimal

    unknown = replace(
        inspection,
        monitors=(
            replace(inspection.monitors[0], refresh_hz=Decimal("57.0")),
            inspection.monitors[1],
        ),
    )
    window.model.draft = None
    window.model.observed = None
    window.receive(unknown)
    assert window.model.draft.outputs[0].mode.endswith("@57.0")
    assert window.refresh_rate.currentIndex() == -1
    window.position_x.setValue(-1920)
    assert window.model.draft.outputs[0].mode.endswith("@57.0")
    assert not window.apply.isEnabled()
