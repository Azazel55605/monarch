"""Native Qt manual monitor editor; mutations go through BackendThread's coordinator."""

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from monarch.backends.hyprland.inspector import Inspection
from monarch.backends.hyprland.support import blockers
from monarch.domain.advanced import AdvancedState
from monarch.domain.layout import Layout
from monarch.domain.monitors import Mode, Monitor
from monarch.domain.policy import Policy
from monarch.domain.profiles import Profile
from monarch.domain.quick_layout import arrange_external, connection_key, external, identity
from monarch.errors import MonarchError
from monarch.resources import APP_ID, icon_path
from monarch.ui.automation import AutomationDialog
from monarch.ui.canvas import LayoutCanvas
from monarch.ui.diagnostics import AdvancedDialog, DiagnosticsDialog
from monarch.ui.dialogs import ConfirmationDialog, IntegrationDialog
from monarch.ui.help import HelpDialog
from monarch.ui.identify import Identification
from monarch.ui.model import EditorModel, draft_layout
from monarch.ui.profiles import MappingDialog, ProfileBar
from monarch.ui.quick import ExternalDialog, icon_button, quick_dialog
from monarch.ui.theme import ThemeController
from monarch.ui.worker import BackendThread


class MainWindow(QMainWindow):
    preview_requested = Signal(object)
    quick_panel_closed = Signal()

    def __init__(
        self,
        backend: BackendThread | None = None,
        *,
        quit_on_close: bool = False,
        theme: ThemeController | None = None,
        startup_profile: str = "",
        persist_profile: bool = False,
        tray_enabled: bool = False,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Monarch · Displays")
        self.resize(1180, 780)
        self.setMinimumSize(940, 650)
        self.model = EditorModel()
        self.backend = backend
        self.quit_on_close = quit_on_close
        self.advanced_dialog: AdvancedDialog | None = None
        self.diagnostics_dialog: DiagnosticsDialog | None = None
        self.automation_dialog: AutomationDialog | None = None
        self.startup_profile = startup_profile
        self._profile_loading = False
        self._requested_profile = ""
        self.ready = False
        self.ownership_reason = "Connecting to Hyprland…"
        self.loading = False
        self._discard_next = False
        self._reverted_draft: Layout | None = None
        self._closing = False
        self._quit_requested = False
        self.quick_panel: QDialog | None = None
        self.confirmation: ConfirmationDialog | None = None
        self.integration: IntegrationDialog | None = None
        self.identification = Identification()
        self._persist = False
        self.notice = ""
        if theme is not None:
            appearance = self.menuBar().addMenu("Appearance")
            theme.menu(appearance)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("Quick start and recovery…", lambda: self.show_help())
        help_menu.addAction("About and license notices…", lambda: self.show_help(notices=True))
        self.diagnostics_action = help_menu.addAction(
            "Redacted diagnostics…", self.show_diagnostics
        )
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)
        row = QHBoxLayout()
        title = QLabel("Displays")
        font = title.font()
        font.setPointSize(24)
        font.setBold(True)
        title.setFont(font)
        row.addWidget(title)
        row.addStretch()
        self.session_label = QLabel("Connecting…")
        row.addWidget(self.session_label)
        self.identify_button = QPushButton("Identify")
        self.identify_button.clicked.connect(self.identify)
        row.addWidget(self.identify_button)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        outer.addLayout(row)
        self.profile_bar = ProfileBar(self)
        self.profile_bar.request.connect(self.profile_request)
        self.profile_bar.load.connect(self.load_profile)
        outer.addWidget(self.profile_bar)
        automatic_row = QHBoxLayout()
        self.automatic_status = QLabel("Automatic switching is disabled.")
        self.automatic_status.setWordWrap(True)
        self.automatic_status.setAccessibleName("Automatic profile switching status")
        automatic_row.addWidget(self.automatic_status, 1)
        self.automatic_button = QPushButton("Automation…")
        self.automatic_button.clicked.connect(
            lambda: self.backend.submit("automation-settings") if self.backend else None
        )
        automatic_row.addWidget(self.automatic_button)
        self.resume_automatic = QPushButton("Resume automatic switching")
        self.resume_automatic.clicked.connect(
            lambda: self.backend.submit("automation-resume") if self.backend else None
        )
        self.resume_automatic.setVisible(False)
        automatic_row.addWidget(self.resume_automatic)
        outer.addLayout(automatic_row)
        self.tray: QSystemTrayIcon | None = None
        self.tray_menu: QMenu | None = None
        if tray_enabled:
            self.tray = QSystemTrayIcon(self)
            icon = QIcon.fromTheme(APP_ID, QIcon(icon_path()))
            if icon.isNull():
                icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            self.tray.setIcon(icon)
            self.tray.setToolTip("Monarch — guarded monitor profiles")
            self.tray_menu = QMenu(self)
            self.tray.setContextMenu(self.tray_menu)
            self.tray.activated.connect(self.tray_activated)
            self.update_tray(())
            self.tray.show()
        self.banner = QLabel("Connecting to the compositor…")
        self.banner.setWordWrap(True)
        self.banner.setAccessibleName("Monitor management status")
        outer.addWidget(self.banner)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = LayoutCanvas()
        center_layout.addWidget(self.canvas, 1)
        hint = QLabel(
            "Drag displays to arrange them. Edges snap together. "
            "Arrow keys move 1 px; Shift moves 10 px."
        )
        hint.setWordWrap(True)
        center_layout.addWidget(hint)
        self.displays = QListWidget()
        self.displays.setMaximumHeight(122)
        self.displays.setAccessibleName("Connected and disabled displays")
        center_layout.addWidget(self.displays)
        row = QHBoxLayout()
        fit = QPushButton("Fit layout")
        fit.clicked.connect(self.canvas.fit)
        self.revalidate_button = QPushButton("Revalidate edits")
        self.revalidate_button.clicked.connect(self.revalidate)
        row.addWidget(fit)
        row.addStretch()
        row.addWidget(self.revalidate_button)
        center_layout.addLayout(row)
        self.splitter.addWidget(center)
        properties = QWidget()
        form = QFormLayout(properties)
        form.setContentsMargins(20, 0, 0, 0)
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.selected_title = QLabel("Select a display")
        f = self.selected_title.font()
        f.setBold(True)
        f.setPointSize(14)
        self.selected_title.setFont(f)
        form.addRow(self.selected_title)
        self.enabled = QCheckBox("Use this display")
        self.enabled.setObjectName("displayEnabled")
        form.addRow(self.enabled)
        self.resolution = QComboBox()
        self.resolution.setAccessibleName("Resolution")
        self.resolution.setObjectName("resolution")
        self.refresh_rate = QComboBox()
        self.refresh_rate.setAccessibleName("Refresh rate")
        self.refresh_rate.setObjectName("refreshRate")
        form.addRow("Resolution", self.resolution)
        form.addRow("Refresh rate", self.refresh_rate)
        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.25, 8)
        self.scale.setDecimals(4)
        self.scale.setSingleStep(0.25)
        self.scale.setAccessibleName("Display scale")
        self.scale.setObjectName("scale")
        form.addRow("Scale", self.scale)
        self.rotation = QComboBox()
        self.rotation.setAccessibleName("Rotation and flip")
        self.rotation.addItems(
            [
                "Normal",
                "90°",
                "180°",
                "270°",
                "Flipped",
                "Flipped 90°",
                "Flipped 180°",
                "Flipped 270°",
            ]
        )
        self.rotation.setObjectName("rotation")
        form.addRow("Transform", self.rotation)
        self.vrr = QComboBox()
        self.vrr.setAccessibleName("Variable refresh rate policy")
        self.vrr.addItem("Off", 0)
        self.vrr.addItem("On", 1)
        self.vrr.setToolTip(
            "Per-display VRR policy. Off/On uses Keep/Revert and Save on login. "
            "Fullscreen-only policies are not supported yet."
        )
        form.addRow("VRR", self.vrr)
        self.position_x = QSpinBox()
        self.position_y = QSpinBox()
        for name, spin in [
            ("Horizontal position", self.position_x),
            ("Vertical position", self.position_y),
        ]:
            spin.setRange(-(2**31) + 1, 2**31 - 1)
            spin.setAccessibleName(name)
        self.position_x.setObjectName("positionX")
        self.position_y.setObjectName("positionY")
        form.addRow("X position", self.position_x)
        form.addRow("Y position", self.position_y)
        self.mirror = QComboBox()
        self.mirror.setAccessibleName("Mirror target")
        self.mirror.setObjectName("mirrorTarget")
        form.addRow("Mirror", self.mirror)
        self.display_info = QLabel("")
        self.display_info.setWordWrap(True)
        form.addRow(self.display_info)
        self.advanced_button = QPushButton("Advanced settings…")
        self.advanced_button.clicked.connect(self.show_advanced)
        form.addRow(self.advanced_button)
        self.properties = properties
        for combo in (self.resolution, self.refresh_rate, self.rotation, self.vrr, self.mirror):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        inspector = QScrollArea()
        inspector.setWidgetResizable(True)
        inspector.setFrameShape(QFrame.Shape.NoFrame)
        inspector.setWidget(properties)
        self.splitter.addWidget(inspector)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setSizes([760, 330])
        outer.addWidget(self.splitter, 1)
        self.validation = QLabel("")
        self.validation.setWordWrap(True)
        self.validation.setAccessibleName("Layout validation")
        outer.addWidget(self.validation)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        outer.addWidget(line)
        row = QHBoxLayout()
        self.setup_button = QPushButton("Set up monitor management…")
        self.setup_button.clicked.connect(self.setup_integration)
        row.addWidget(self.setup_button)
        self.recover_button = QPushButton("Recover unfinished preview")
        self.recover_button.clicked.connect(self.recover)
        row.addWidget(self.recover_button)
        row.addStretch()
        self.persist = QCheckBox("Save on login")
        self.persist.setToolTip("Only saved after you choose Keep changes.")
        self.persist.setObjectName("saveOnLogin")
        self.persist.setChecked(persist_profile)
        self.persist.toggled.connect(self.update_status)
        row.addWidget(self.persist)
        self.discard = QPushButton("Discard edits")
        self.discard.clicked.connect(self.discard_edits)
        row.addWidget(self.discard)
        self.apply = QPushButton("Preview changes")
        self.apply.setObjectName("previewChanges")
        self.apply.clicked.connect(lambda: self.start_preview())
        row.addWidget(self.apply)
        outer.addLayout(row)
        self.canvas.editing.connect(
            lambda: self.backend.submit("automation-edit-pin") if self.backend else None
        )
        self.canvas.selected.connect(self.select_display)
        self.canvas.moved.connect(self.position_changed, Qt.ConnectionType.QueuedConnection)
        self.displays.currentRowChanged.connect(self.row_selected)
        self.resolution.currentIndexChanged.connect(self.resolution_changed)
        self.vrr.currentIndexChanged.connect(self.fields_changed)
        self.refresh_rate.currentIndexChanged.connect(self.fields_changed)
        self.enabled.toggled.connect(self.fields_changed)
        self.scale.valueChanged.connect(self.fields_changed)
        self.rotation.currentIndexChanged.connect(self.fields_changed)
        self.position_x.valueChanged.connect(self.fields_changed)
        self.position_y.valueChanged.connect(self.fields_changed)
        self.mirror.currentIndexChanged.connect(self.fields_changed)
        QShortcut(QKeySequence("Escape"), self, self.identification.close)
        QShortcut(QKeySequence("Ctrl+R"), self, self.refresh)
        if backend:
            backend.diagnostics_ready.connect(self.diagnostics_received)
            backend.diagnostics_failed.connect(self.diagnostics_error)
            backend.diagnostics_saved.connect(self.diagnostics_exported)
            backend.automation_state.connect(self.automation_status)
            backend.automation_settings.connect(self.automation_settings)
            backend.automation_offer.connect(self.automatic_offer)
            backend.automation_saved.connect(self.automation_saved)
            backend.automation_failed.connect(self.automation_error)
            backend.profiles.connect(self.receive_profiles)
            backend.profile_loaded.connect(self.profile_loaded)
            backend.profile_mapping.connect(self.profile_mapping)
            backend.profile_notice.connect(self.profile_message)
            backend.profile_failed.connect(self.profile_error)
            backend.observed.connect(self.receive)
            backend.ownership.connect(self.receive_ownership)
            backend.failed.connect(self.show_error)
            backend.pending.connect(self.preview_pending)
            backend.completed.connect(self.preview_complete)
            backend.integration_ready.connect(self.integration_plan)
            backend.installed.connect(self.integration_installed)
            backend.finished.connect(self.backend_finished)
        self.render_state()

    def receive(self, inspection: Inspection) -> None:
        if self._reverted_draft is not None:
            if self.model.draft != self._reverted_draft:
                self._reverted_draft = None
            elif connection_key(inspection.monitors) != connection_key(
                self._reverted_draft.outputs
            ):
                self._discard_next = True
                self._reverted_draft = None
        self.model.receive(inspection, discard=self._discard_next)
        self._discard_next = False
        caps = inspection.capabilities
        self.session_label.setText(f"Hyprland {caps.version or 'unknown'} · {caps.provider}")
        self.render_state()
        if self.startup_profile and self.ready:
            key, self.startup_profile = self.startup_profile, ""
            QTimer.singleShot(0, lambda: self.load_profile(key, True))

    def receive_ownership(self, state: dict[str, Any]) -> None:
        self.ready = state["ready"]
        self.ownership_reason = state["reason"]
        self.render_state()

    def render_state(self) -> None:
        self.loading = True
        draft = self.model.draft
        if draft:
            selected = self.model.selected
            self.displays.clear()
            connected = (
                {m.name: m for m in self.model.inspection.monitors} if self.model.inspection else {}
            )
            for index, output in enumerate(draft.outputs, 1):
                state = (
                    "missing"
                    if output.name not in connected
                    else "replaced · discard draft to use"
                    if identity(output) != identity(connected[output.name])
                    else "enabled"
                    if output.enabled
                    else "disabled"
                )
                self.displays.addItem(f"{index}   {output.name}    ·    {state}")
                if output.name == selected:
                    self.displays.setCurrentRow(index - 1)
            self.canvas.display(draft, selected, not self.model.busy and not self._profile_loading)
        self.loading = False
        self.load_properties()
        self.update_status()
        if self.backend:
            self.backend.submit(
                "ui-state",
                not self.model.busy and not self.model.dirty and not self._profile_loading,
                self.model.dirty and not self.model.busy and not self._discard_next,
            )

    def load_properties(self) -> None:
        self.loading = True
        output = self.model.output(self.model.selected)
        self.properties.setEnabled(
            output is not None and not self.model.busy and not self._profile_loading
        )
        if output and self.model.inspection:
            self.selected_title.setText(output.name)
            monitor = next(
                (m for m in self.model.inspection.monitors if m.name == output.name), None
            )
            self.enabled.setChecked(output.enabled)
            self.vrr.setCurrentIndex(output.vrr)
            self.resolution.clear()
            resolutions = []
            if monitor:
                for mode in monitor.modes:
                    pair = (mode.width, mode.height)
                    if pair not in resolutions:
                        resolutions.append(pair)
            for width, height in resolutions:
                self.resolution.addItem(f"{width} × {height}", (width, height))
            if output.mode != "preferred":
                mode = Mode.parse(output.mode + "Hz")
                self.resolution.setCurrentIndex(
                    resolutions.index((mode.width, mode.height))
                    if (mode.width, mode.height) in resolutions
                    else -1
                )
            else:
                self.resolution.setCurrentIndex(-1)
            self.populate_refresh(output.mode)
            self.scale.setValue(output.scale)
            self.rotation.setCurrentIndex(output.transform)
            self.position_x.setValue(output.x)
            self.position_y.setValue(output.y)
            self.mirror.clear()
            self.mirror.addItem("Independent display", "")
            if self.model.draft:
                for other in self.model.draft.outputs:
                    if other.name != output.name and other.enabled and not other.mirror:
                        self.mirror.addItem(other.name, other.name)
            index = self.mirror.findData(output.mirror)
            if index < 0:
                self.mirror.addItem(f"Unavailable: {output.mirror}", output.mirror)
                index = self.mirror.count() - 1
            self.mirror.setCurrentIndex(index)
            self.position_x.setEnabled(not output.mirror)
            self.position_y.setEnabled(not output.mirror)
            self.display_info.setText(
                (monitor.description or monitor.model)
                if monitor
                else "This display is no longer connected."
            )
        self.loading = False

    def populate_refresh(self, selected: str = "") -> None:
        self.refresh_rate.clear()
        if not self.model.inspection:
            return
        monitor = next(
            (m for m in self.model.inspection.monitors if m.name == self.model.selected), None
        )
        pair = self.resolution.currentData()
        if monitor:
            for mode in monitor.modes:
                if (mode.width, mode.height) == pair:
                    name = f"{mode.width}x{mode.height}@{mode.refresh_hz}"
                    self.refresh_rate.addItem(f"{mode.refresh_hz} Hz", name)
        index = self.refresh_rate.findData(selected)
        self.refresh_rate.setCurrentIndex(index if index >= 0 else (-1 if selected else 0))

    def resolution_changed(self, *args: object) -> None:
        if self.loading:
            return
        self.loading = True
        self.populate_refresh()
        self.loading = False
        self.fields_changed()

    def fields_changed(self, *args: object) -> None:
        if self.loading or not self.model.selected:
            return
        current = self.model.output(self.model.selected)
        if current is None:
            return
        mode = self.refresh_rate.currentData() or current.mode
        scale = self.scale.value()
        if scale == round(current.scale, self.scale.decimals()):
            scale = current.scale
        self.model.update(
            self.model.selected,
            mode=mode,
            enabled=self.enabled.isChecked(),
            scale=scale,
            transform=self.rotation.currentIndex(),
            x=self.position_x.value(),
            y=self.position_y.value(),
            mirror=self.mirror.currentData() or "",
            vrr=self.vrr.currentData(),
        )
        self.render_state()

    def update_status(self) -> None:
        error = self.model.error()
        if not error and self.model.inspection:
            error = next(
                (
                    message
                    for code, message in blockers(self.model.inspection)
                    if code != "unverified_config"
                ),
                "",
            )
        self.validation.setText(
            error
            or (
                "Unsaved layout changes."
                if self.model.dirty
                else "Layout matches the current session."
            )
        )
        self.banner.setText(
            "Previewing display settings. Keep or Revert before the timer expires."
            if self.model.busy
            else (self.notice + "\n" if self.notice else "") + self.ownership_reason
        )
        self.apply.setEnabled(
            bool(
                self.ready
                and (self.model.dirty or self.persist.isChecked())
                and not error
                and not self.model.busy
                and not self._profile_loading
            )
        )
        self.apply.setText(
            "Save current layout"
            if self.persist.isChecked() and not self.model.dirty
            else "Preview changes"
        )
        self.profile_bar.setEnabled(not self.model.busy and not self._profile_loading)
        self.discard.setEnabled(
            self.model.dirty and not self.model.busy and not self._profile_loading
        )
        self.revalidate_button.setEnabled(
            self.model.stale and not self.model.busy and not self._profile_loading
        )
        for button in (
            self.automatic_button,
            self.setup_button,
            self.refresh_button,
            self.identify_button,
            self.recover_button,
        ):
            button.setEnabled(not self.model.busy and not self._profile_loading)
        self.persist.setEnabled(not self.model.busy and self.ready)
        self.diagnostics_action.setEnabled(not self.model.busy)
        issues = blockers(self.model.inspection) if self.model.inspection else ()
        self.setup_button.setEnabled(
            not self.model.busy and not self._profile_loading and not issues
        )
        self.setup_button.setToolTip("\n".join(message for _, message in issues))
        self.recover_button.setVisible(
            "recovery" in self.ownership_reason.lower()
            or "unfinished" in self.ownership_reason.lower()
        )

    def show_help(self, *, notices: bool = False) -> None:
        self.help_dialog = HelpDialog(notices=notices, parent=self)
        self.help_dialog.show()

    def show_advanced(self) -> None:
        state = AdvancedState()
        if self.model.inspection:
            monitor = next(
                (m for m in self.model.inspection.monitors if m.name == self.model.selected), None
            )
            if monitor:
                state = monitor.advanced
        self.advanced_dialog = AdvancedDialog(state, self)
        self.advanced_dialog.show()

    def show_diagnostics(self) -> None:
        self.diagnostics_dialog = DiagnosticsDialog(self)
        if self.backend:
            self.diagnostics_dialog.save_requested.connect(
                lambda path, data: self.backend.submit("diagnostics-save", path, data)
            )
            self.backend.submit("diagnostics")
        self.diagnostics_dialog.show()

    def diagnostics_received(self, data: dict[str, Any]) -> None:
        if self.diagnostics_dialog:
            self.diagnostics_dialog.receive(data)

    def diagnostics_error(self, message: str) -> None:
        if self.diagnostics_dialog:
            self.diagnostics_dialog.status.setText(message)

    def diagnostics_exported(self) -> None:
        if self.diagnostics_dialog:
            self.diagnostics_dialog.status.setText(
                "Saved a new private report. Existing files are never replaced."
            )

    def automation_status(self, state: dict[str, Any]) -> None:
        self.automatic_status.setText(state["reason"])
        self.automatic_status.setToolTip("\n".join(state.get("rejected", [])))
        self.resume_automatic.setVisible(bool(state.get("pinned")))

    def automation_settings(self, policy: Policy, autostart: bool) -> None:
        dialog = AutomationDialog(policy, self.profile_bar.profiles, autostart, self)
        if self.backend:
            dialog.saved.connect(
                lambda policy, login: self.backend.submit("automation-save", policy, login)
            )
        self.automation_dialog = dialog
        dialog.show()

    def automation_error(self, message: str) -> None:
        if self.automation_dialog:
            self.automation_dialog.error.setText(message)
        self.profile_message(message)

    def automation_saved(self) -> None:
        if self.automation_dialog:
            self.automation_dialog.accept()
            self.automation_dialog = None
        self.profile_message(
            "Automatic switching settings saved. Every preview still requires Keep."
        )

    def automatic_offer(self, layout: Layout, authorization: dict[str, str] | None = None) -> None:
        if (
            self.model.busy
            or self.model.dirty
            or self._profile_loading
            or not self.ready
            or QApplication.activeModalWidget() is not None
            or QApplication.mouseButtons() != Qt.MouseButton.NoButton
        ):
            if self.backend:
                self.backend.submit("automatic-defer", authorization)
            return
        self.show_editor()
        self.persist.setChecked(False)
        self.model.draft = layout
        self.model.stale = False
        self.model.busy = True
        self._persist = False
        self.render_state()
        if self.backend:
            self.backend.submit("automatic-preview", layout, authorization)

    def profile_message(self, message: str) -> None:
        self.notice = message
        self.update_status()

    def profile_error(self, message: str) -> None:
        self._profile_loading = False
        self.profile_message(message)
        self.render_state()

    def receive_profiles(self, profiles: tuple[Profile, ...]) -> None:
        self.profile_bar.populate(profiles)
        index = self.profile_bar.selector.findData(self._requested_profile)
        if index >= 0:
            self.profile_bar.selector.setCurrentIndex(index)
        self.update_tray(profiles)

    def update_tray(self, profiles: tuple[Profile, ...]) -> None:
        if self.tray_menu is None:
            return
        self.tray_menu.clear()
        self.tray_menu.addAction("Quick controls…", self.show_quick_panel)
        self.tray_menu.addAction("External display layout…", self.show_external_panel)
        self.tray_menu.addAction("Open Monarch", self.show_editor)
        for profile in profiles:
            self.tray_menu.addAction(profile.name, partial(self.tray_switch, profile.id))
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(
            "Pause automatic switching for this session",
            lambda: self.backend.submit("automation-pin") if self.backend else None,
        )
        self.tray_menu.addAction(
            "Resume automatic switching",
            lambda: self.backend.submit("automation-resume") if self.backend else None,
        )
        self.tray_menu.addAction("Quit Monarch", self.quit_requested)

    def tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_quick_panel()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if self.quick_panel:
                self.quick_panel.close()
            self.show_editor()

    def present_quick_panel(self, dialog: QDialog) -> None:
        if self.quick_panel:
            self.quick_panel.close()
        self.quick_panel = dialog
        # Equal min/max size tells Hyprland this is a compact floating dialog.
        layout = dialog.layout()
        assert layout is not None
        layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        dialog.adjustSize()
        dialog.finished.connect(self.quick_panel_finished)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def quick_panel_finished(self) -> None:
        self.quick_panel = None
        self.quick_panel_closed.emit()

    def show_quick_panel(self) -> None:
        if self.model.busy:
            self.show_editor()
            return
        panel = quick_dialog("Monarch quick controls", self)
        form = QFormLayout(panel)
        picker = QComboBox()
        for profile in self.profile_bar.profiles:
            picker.addItem(profile.name, profile.id)
        switch = QPushButton("Preview profile")
        switch.setEnabled(bool(picker.count()) and self.ready and not self._profile_loading)
        form.addRow("Profile", picker)
        form.addRow(switch)

        def preview_profile() -> None:
            panel.accept()
            self.tray_switch(str(picker.currentData()))

        switch.clicked.connect(preview_profile)
        row = QHBoxLayout()
        sp = QStyle.StandardPixmap

        def open_panel(callback: Callable[[], None]) -> None:
            panel.accept()
            callback()

        for label, name, fallback, callback in (
            ("External displays", "video-display", sp.SP_ComputerIcon, self.show_external_panel),
            ("Open editor", "document-edit", sp.SP_FileDialogDetailedView, self.show_editor),
        ):
            button = icon_button(panel, label, name, fallback)
            button.clicked.connect(partial(open_panel, callback))
            row.addWidget(button)
        form.addRow(row)
        self.present_quick_panel(panel)

    def show_external_panel(self) -> None:
        inspection = self.model.inspection
        if not self.ready or self.model.busy or self._profile_loading or inspection is None:
            self.show_editor()
            self.profile_message("Monitor management must be ready to preview an external layout.")
            return
        layout = draft_layout(inspection.monitors)
        anchors = [o.name for o in layout.outputs if o.enabled and not o.mirror]
        targets = [
            o.name for o in layout.outputs if external(o.name) and any(a != o.name for a in anchors)
        ]
        if not targets:
            self.show_editor()
            self.profile_message(
                "Connect an external display and a separate independent reference."
            )
            return
        preferred = next((name for name in anchors if not external(name)), "")
        panel = ExternalDialog(targets, anchors, preferred, self)
        for action, button in panel.layout_buttons.items():
            button.clicked.connect(partial(self.preview_external, panel, action))
        self.present_quick_panel(panel)

    def preview_external(self, panel: ExternalDialog, action: str) -> None:
        target, anchor = panel.target.currentText(), panel.anchor.currentText()
        panel.accept()
        self.show_editor()
        inspection = self.model.inspection
        if not inspection or self.model.busy or not self.ready:
            return
        current = draft_layout(inspection.monitors)
        try:
            layout = arrange_external(current, inspection.monitors, target, anchor, action)
        except MonarchError as exc:
            self.profile_message(str(exc))
            return
        if (
            self.model.dirty
            and QMessageBox.question(
                self,
                "Replace edited layout?",
                "Discard your draft and preview this layout?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            != QMessageBox.StandardButton.Discard
        ):
            return
        self.persist.setChecked(False)
        self.model.observed = current
        self.model.draft = layout
        self.model.stale = False
        self.render_state()
        self.start_preview(topology_snapshot=current)

    def quit_requested(self) -> None:
        self._quit_requested = True
        self.close()
        self._quit_requested = False

    def show_editor(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_switch(self, key: str) -> None:
        # Always surface the editor and the real Keep/Revert dialog. Tray actions
        # never imply confirmation or persistence.
        self.show_editor()
        self.persist.setChecked(False)
        self.load_profile(key, True)

    def profile_request(self, operation: str, payload: dict[str, Any]) -> None:
        if self.model.busy or self._profile_loading:
            return
        if operation in {"save", "update"}:
            if not self.model.draft:
                self.profile_message("No edited layout is available.")
                return
            try:
                Layout.parse(self.model.draft.to_dict())
            except MonarchError as exc:
                self.profile_message(str(exc))
                return
            payload = dict(payload, layout=self.model.draft)
        if self.backend:
            self.backend.submit("profile", operation, payload)

    def load_profile(self, key: str, switch: bool = False) -> None:
        if not key or self.model.busy or self._profile_loading:
            return
        if switch and not self.ready:
            self.profile_message("Set up monitor management before switching profiles.")
            return
        if (
            self.model.dirty
            and QMessageBox.question(
                self,
                "Replace edited layout?",
                "Discard the current edits and load this profile?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            != QMessageBox.StandardButton.Discard
        ):
            return
        self._requested_profile = key
        index = self.profile_bar.selector.findData(key)
        if index >= 0:
            self.profile_bar.selector.setCurrentIndex(index)
        self._profile_loading = True
        self.render_state()
        if self.backend:
            self.backend.submit("profile", "switch" if switch else "load", {"key": key})

    def profile_mapping(
        self, profile: Profile, monitors: tuple[Monitor, ...], switch: bool, reason: str
    ) -> None:
        self._profile_loading = False
        self.update_status()
        dialog = MappingDialog(profile, monitors, reason, self)

        def mapped(bindings: dict[str, str]) -> None:
            if self.backend and not self.model.busy:
                self._profile_loading = True
                self.update_status()
                self.backend.submit(
                    "profile",
                    "switch" if switch else "load",
                    {"key": profile.id, "bindings": bindings},
                )

        dialog.mapped.connect(mapped)
        self.mapping_dialog = dialog
        dialog.show()

    def profile_loaded(self, layout: Layout, switch: bool) -> None:
        self._profile_loading = False
        if self.model.inspection is None or self.model.busy:
            return
        try:
            layout.validate(self.model.inspection.monitors)
        except MonarchError as exc:
            self.profile_message(str(exc))
            return
        self.model.draft = layout
        self.model.stale = False
        self.render_state()
        if switch:
            self.start_preview(topology_snapshot=draft_layout(self.model.inspection.monitors))

    def select_display(self, name: str) -> None:
        self.model.selected = name
        self.loading = True
        if self.model.draft:
            for index, o in enumerate(self.model.draft.outputs):
                if o.name == name:
                    self.displays.setCurrentRow(index)
        self.loading = False
        self.canvas.select(name)
        self.load_properties()

    def row_selected(self, index: int) -> None:
        if self.loading or self.model.draft is None or index < 0:
            return
        self.select_display(self.model.draft.outputs[index].name)

    def position_changed(self, name: str, x: int, y: int) -> None:
        self.model.update(name, x=x, y=y)
        self.model.selected = name
        self.render_state()

    def refresh(self) -> None:
        if self.backend:
            self.backend.submit("refresh")

    def discard_edits(self) -> None:
        if self.model.inspection:
            self.model.receive(self.model.inspection, discard=True)
            self.render_state()
        self.refresh()

    def revalidate(self) -> None:
        try:
            self.model.revalidate()
            self.render_state()
        except MonarchError as exc:
            self.show_error(str(exc))

    def identify(self) -> None:
        if self.model.draft:
            self.identification.show(tuple(o.name for o in self.model.draft.outputs))

    def start_preview(self, *, topology_snapshot: Layout | None = None) -> None:
        if self.model.error() or not self.ready or not self.model.draft:
            return
        self.model.busy = True
        self._persist = self.persist.isChecked()
        self.render_state()
        self.preview_requested.emit(self.model.draft)
        if self.backend:
            self.backend.submit("preview", self.model.draft, topology_snapshot)

    def preview_pending(self, deadline: float) -> None:
        self.confirmation = ConfirmationDialog(deadline, self._persist, self)
        if self.backend:
            self.confirmation.decision.connect(
                lambda keep, persist: self.backend.submit("decide", keep, persist)
            )
        self.confirmation.show()

    def preview_complete(self, result: dict[str, Any]) -> None:
        if self.confirmation:
            self.confirmation.finish()
            self.confirmation = None
        self.model.busy = False
        if result.get("automatic"):
            self._discard_next = True
        self._reverted_draft = (
            self.model.draft
            if result["state"] == "reverted" and not result.get("automatic")
            else None
        )
        if result["state"] == "kept":
            self._discard_next = True
            self.ownership_reason = (
                "Layout kept and saved on login."
                if result.get("reason") == "persisted"
                else "Layout kept for this session."
            )
        else:
            self.ownership_reason = (
                "Previous layout restored."
                if result["state"] == "reverted"
                else "Recovery needs attention: " + result["state"]
            )
            self.model.stale = result["state"] != "reverted"
        self.notice = self.ownership_reason
        self.render_state()

    def show_error(self, message: str) -> None:
        self.notice = message
        self.model.busy = False
        if self.confirmation:
            self.confirmation.finish()
            self.confirmation = None
        self.ownership_reason = message
        if self.integration:
            self.integration.preview.setPlainText(message)
            self.integration.install_button.setEnabled(False)
        self.ready = False
        self.render_state()

    def setup_integration(self) -> None:
        root = self.model.inspection.config.path if self.model.inspection else None
        self.integration = IntegrationDialog(root, self)
        if self.backend:
            self.integration.prepare.connect(
                lambda root, deps: self.backend.submit("prepare", root, deps)
            )
            self.integration.install.connect(lambda: self.backend.submit("install"))
        self.integration.show()

    def integration_plan(self, plan) -> None:  # type: ignore[no-untyped-def]
        if self.integration:
            self.integration.show_plan(plan)

    def integration_installed(self, directory: Path) -> None:
        if self.integration:
            self.integration.accept()
            self.integration = None
        self.ownership_reason = "Monitor management installed. Preview edits and Keep to save them."
        self.render_state()

    def recover(self) -> None:
        self.model.busy = True
        self.render_state()
        if self.backend:
            self.backend.submit("recover")

    def closeEvent(self, event: QCloseEvent) -> None:
        if (
            self.tray
            and QSystemTrayIcon.isSystemTrayAvailable()
            and not self._closing
            and not self._quit_requested
        ):
            event.ignore()
            if self.model.busy:
                # Keep a live confirmation reachable; hiding must never imply Keep.
                self.show_editor()
                if self.confirmation:
                    self.confirmation.raise_()
                    self.confirmation.activateWindow()
                return
            self.identification.close()
            self.hide()
            return
        if self.backend and self.model.dirty and not self.model.busy and not self._closing:
            answer = QMessageBox.question(
                self,
                "Discard unsaved layout edits?",
                "The edited layout has not been kept. Discard these edits and close Monarch?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Discard:
                event.ignore()
                return
        self.identification.close()
        if self.tray:
            self.tray.hide()
        if self.backend and self.backend.isRunning():
            event.ignore()
            self.hide()
            self._closing = True
            self.backend.shutdown()
        else:
            event.accept()
            if self.quit_on_close:
                application = QApplication.instance()
                if application is not None:
                    application.quit()

    def backend_finished(self) -> None:
        if self._closing:
            self.close()
            if self.quit_on_close:
                application = QApplication.instance()
                if application is not None:
                    application.quit()
