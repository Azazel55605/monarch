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


def test_profile_draft_load_switch_and_saving_do_not_apply_implicitly(window, qtbot):
    from monarch.domain.layout import Layout
    from monarch.domain.profiles import Profile

    layout = Layout(tuple(replace(o, x=o.x - 100) for o in window.model.draft.outputs))
    profiles = tuple(
        Profile(str(i) * 32, name, layout)
        for i, name in [(1, "Desk"), (2, "Presentation"), (3, "Portrait")]
    )
    window.receive_profiles(profiles)
    assert window.profile_bar.selector.count() == 3
    previews = []
    window.preview_requested.connect(previews.append)
    window.profile_loaded(layout, False)
    assert window.model.dirty and not window.model.busy
    assert not previews
    window.profile_loaded(layout, True)
    assert window.model.busy and previews == [layout]
    assert not window.profile_bar.isEnabled()
    window.model.busy = False


def test_explicit_mapping_dialog_requires_complete_one_to_one_choices(qtbot, inspection):
    from monarch.domain.layout import Layout
    from monarch.domain.profiles import Profile
    from monarch.ui.profiles import MappingDialog

    live = tuple(replace(m, make="Same", model="Twins", serial="") for m in inspection.monitors)
    layout = Layout(
        tuple(
            replace(o, make="Same", model="Twins", serial="")
            for o in editor_layout(inspection).outputs
        )
    )
    dialog = MappingDialog(Profile("a" * 32, "Twins", layout), live, "Ambiguous", None)
    qtbot.addWidget(dialog)
    dialog.show()
    assert not dialog.ok.isEnabled()
    choices = list(dialog.choices.values())
    choices[0].setCurrentIndex(1)
    choices[1].setCurrentIndex(1)
    assert not dialog.ok.isEnabled()
    choices[1].setCurrentIndex(2)
    assert dialog.ok.isEnabled()
    mapped = []
    dialog.mapped.connect(mapped.append)
    qtbot.mouseClick(dialog.ok, Qt.MouseButton.LeftButton)
    assert len(set(mapped[0].values())) == 2


def editor_layout(inspection):
    model = EditorModel()
    model.receive(inspection)
    return model.draft


def test_installed_styles_and_missing_saved_theme_fallback(qapp, qtbot, tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMenu

    from monarch.ui.theme import ThemeController

    settings = QSettings(str(tmp_path / "appearance.ini"), QSettings.Format.IniFormat)
    settings.setValue("appearance/style", "not-installed")
    original = qapp.style().objectName()
    controller = ThemeController(qapp, settings)
    assert controller.warning and controller.selected == ""
    menu = QMenu()
    controller.menu(menu)
    fusion = next(a for a in menu.actions() if a.text().lower() == "fusion")
    fusion.trigger()
    assert qapp.style().objectName().lower() == "fusion"
    assert settings.value("appearance/style").lower() == "fusion"
    menu.actions()[0].trigger()
    assert qapp.style().objectName() == original
    assert settings.value("appearance/style") == ""


def test_profile_worker_switch_keep_revert_and_shared_cli_lock(qtbot, guard_setup, tmp_path):
    import asyncio

    from monarch.errors import MonarchError
    from monarch.storage.profiles import ProfileStore
    from monarch.ui.worker import BackendThread

    coordinator, store, baseline, desired, state = guard_setup
    worker = BackendThread(
        session=coordinator.session,
        managed=store.directory,
        env=dict(coordinator.env, XDG_STATE_HOME=str(coordinator.state_home)),
        executable=coordinator.executable,
    )
    worker.profile_store = ProfileStore(tmp_path / "profiles")
    profiles = [
        worker.profile_store.save(name, layout)
        for name, layout in [("Desk", baseline), ("Presentation", desired), ("Portrait", baseline)]
    ]
    widget = MainWindow(worker)
    qtbot.addWidget(widget)
    completed = []
    worker.completed.connect(completed.append)
    widget.show()
    worker.start()
    try:
        qtbot.waitUntil(lambda: widget.ready and widget.profile_bar.selector.count() == 3)
        widget.load_profile(profiles[1].id, True)
        qtbot.waitUntil(lambda: widget.confirmation is not None, timeout=10000)

        async def competing_cli():
            with pytest.raises(MonarchError, match="did not start"):
                await coordinator.preview(store, desired, seconds=5)

        asyncio.run(competing_cli())
        widget.confirmation.choose(True)
        qtbot.waitUntil(
            lambda: bool(completed) and not widget.model.busy and not widget.model.dirty,
            timeout=10000,
        )
        assert completed[-1]["state"] == "kept"
        widget.load_profile(profiles[0].id, True)
        qtbot.waitUntil(lambda: widget.confirmation is not None, timeout=10000)
        widget.confirmation.choose(False)
        qtbot.waitUntil(lambda: len(completed) == 2 and not widget.model.busy, timeout=10000)
        assert completed[-1]["state"] == "reverted"
        # Closing a third switch must recover through the independent guard.
        widget.discard_edits()
        qtbot.waitUntil(lambda: not widget.model.dirty)
        widget.load_profile(profiles[2].id, True)
        qtbot.waitUntil(lambda: widget.confirmation is not None, timeout=10000)
    finally:
        widget._closing = True
        widget.close()
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=10000)
    assert coordinator.paths.status()["status"] == "reverted"


def test_profile_menu_captures_observed_and_draft_separately(
    qtbot, guard_setup, tmp_path, monkeypatch
):
    from PySide6.QtWidgets import QInputDialog

    from monarch.storage.profiles import ProfileStore
    from monarch.ui.worker import BackendThread

    coordinator, store, baseline, desired, state = guard_setup
    worker = BackendThread(
        session=coordinator.session,
        managed=store.directory,
        env=dict(coordinator.env, XDG_STATE_HOME=str(coordinator.state_home)),
        executable=coordinator.executable,
    )
    worker.profile_store = ProfileStore(tmp_path / "profiles")
    widget = MainWindow(worker)
    qtbot.addWidget(widget)
    widget.show()
    worker.start()
    try:
        qtbot.waitUntil(lambda: widget.ready and widget.model.inspection is not None)
        widget.model.draft = desired
        widget.render_state()
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("Observed", True))
        widget.profile_bar.menu.actions()[0].trigger()
        qtbot.waitUntil(
            lambda: (
                widget.profile_bar.selector.count() == 1
                and widget.profile_bar.selector.currentText() == "Observed"
            )
        )
        assert worker.profile_store.get("Observed").layout == baseline
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("Edited", True))
        widget.profile_bar.menu.actions()[1].trigger()
        qtbot.waitUntil(lambda: widget.profile_bar.selector.count() == 2)
        assert worker.profile_store.get("Edited").layout == desired
        assert not coordinator.paths.status()  # Captures never launch the guard.
    finally:
        widget._closing = True
        widget.close()
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=10000)


def test_automation_rule_dialog_and_opt_in_default(qtbot, inspection):
    from monarch.domain.policy import Policy
    from monarch.domain.profiles import Profile
    from monarch.ui.automation import AutomationDialog

    profile = Profile("a" * 32, "Desk", editor_layout(inspection))
    dialog = AutomationDialog(Policy(), (profile,), False)
    qtbot.addWidget(dialog)
    assert not dialog.enabled.isChecked() and not dialog.autostart.isChecked()
    captured = []
    dialog.saved.connect(lambda policy, startup: captured.append((policy, startup)))
    identifier, enabled, mode, priority, ports = dialog.rows[0]
    enabled.setChecked(True)
    mode.setCurrentText("subset")
    priority.setValue(10)
    dialog.enabled.setChecked(True)
    dialog.submit()
    assert captured[0][0].enabled
    assert captured[0][0].rules[0].mode == "subset"
    assert captured[0][0].rules[0].priority == 10
    assert not captured[0][1]


def test_automatic_offer_never_persists_and_dirty_edit_is_preserved(window):
    from monarch.domain.layout import Layout

    layout = Layout(tuple(replace(o, x=o.x - 100) for o in window.model.draft.outputs))
    window.persist.setChecked(True)
    window.automatic_offer(layout)
    assert window.model.busy
    assert not window._persist and not window.persist.isChecked()
    window.model.busy = False
    window.model.update(window.model.selected, x=-500)
    draft = window.model.draft
    window.automatic_offer(layout)
    assert window.model.draft == draft and not window.model.busy


def test_automation_worker_shows_confirmation_then_decline_does_not_loop(
    qtbot, guard_setup, tmp_path
):
    from monarch.domain.policy import Policy, Rule
    from monarch.storage.automation import PolicyStore
    from monarch.storage.profiles import ProfileStore
    from monarch.ui.worker import BackendThread

    coordinator, store, baseline, desired, state = guard_setup
    profiles = ProfileStore(tmp_path / "profiles")
    profile = profiles.save("Desk", desired)
    PolicyStore(profiles.directory).write(Policy(True, (Rule(profile.id),)))
    worker = BackendThread(
        session=coordinator.session,
        managed=store.directory,
        env=dict(coordinator.env, XDG_STATE_HOME=str(coordinator.state_home)),
        executable=coordinator.executable,
    )
    worker.profile_store = profiles
    widget = MainWindow(worker)
    qtbot.addWidget(widget)
    completed = []
    worker.completed.connect(completed.append)
    widget.show()
    worker.start()
    try:
        qtbot.waitUntil(lambda: widget.confirmation is not None, timeout=12000)
        assert not widget._persist
        widget.confirmation.choose(False)
        qtbot.waitUntil(
            lambda: bool(completed) and not widget.model.busy and not widget.model.dirty,
            timeout=12000,
        )
        assert completed[-1]["automatic"] and completed[-1]["state"] == "reverted"
        qtbot.wait(2500)
        assert widget.confirmation is None and len(completed) == 1
        assert worker.automation.attempt["outcome"] == "declined"
    finally:
        widget._closing = True
        widget.close()
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=10000)


def test_unchanged_automatic_polling_preserves_canvas_items(
    qtbot, guard_setup, tmp_path, monkeypatch
):
    import asyncio

    import monarch.ui.worker as worker_module
    from monarch.domain.policy import Policy, Rule
    from monarch.storage.automation import PolicyStore
    from monarch.storage.profiles import ProfileStore

    class QuietWatcher:
        def __init__(self, session):
            pass

        async def invalidations(self):
            await asyncio.Event().wait()
            yield "never"

    monkeypatch.setattr(worker_module, "EventWatcher", QuietWatcher)
    coordinator, store, baseline, desired, state = guard_setup
    profiles = ProfileStore(tmp_path / "profiles")
    profile = profiles.save("Already current", baseline)
    PolicyStore(profiles.directory).write(Policy(True, (Rule(profile.id),)))
    worker = worker_module.BackendThread(
        session=coordinator.session,
        managed=store.directory,
        env=dict(coordinator.env, XDG_STATE_HOME=str(coordinator.state_home)),
        executable=coordinator.executable,
    )
    worker.profile_store = profiles
    widget = MainWindow(worker)
    qtbot.addWidget(widget)
    widget.show()
    worker.start()
    try:
        qtbot.waitUntil(lambda: widget.ready and worker.inspector is not None)
        calls = []
        original = worker.inspector.inspect

        async def observed():
            calls.append(True)
            return await original()

        monkeypatch.setattr(worker.inspector, "inspect", observed)
        item = widget.canvas.items_by_name[baseline.outputs[0].name]
        qtbot.waitUntil(lambda: len(calls) >= 2, timeout=8000)
        qtbot.wait(100)
        assert widget.canvas.items_by_name[baseline.outputs[0].name] is item
        assert widget.confirmation is None
    finally:
        widget._closing = True
        widget.close()
        qtbot.waitUntil(lambda: not worker.isRunning(), timeout=10000)
