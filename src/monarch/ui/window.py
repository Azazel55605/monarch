"""Native Qt manual monitor editor; mutations go through BackendThread's coordinator."""

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from monarch.backends.hyprland.inspector import Inspection
from monarch.domain.monitors import Mode
from monarch.errors import MonarchError
from monarch.ui.canvas import LayoutCanvas
from monarch.ui.dialogs import ConfirmationDialog, IntegrationDialog
from monarch.ui.identify import Identification
from monarch.ui.model import EditorModel
from monarch.ui.worker import BackendThread


class MainWindow(QMainWindow):
    preview_requested = Signal(object)

    def __init__(
        self, backend: BackendThread | None = None, *, quit_on_close: bool = False
    ) -> None:
        super().__init__()
        self.setWindowTitle("Monarch · Displays")
        self.resize(1180, 780)
        self.setMinimumSize(940, 650)
        self.model = EditorModel()
        self.backend = backend
        self.quit_on_close = quit_on_close
        self.ready = False
        self.ownership_reason = "Connecting to Hyprland…"
        self.loading = False
        self._discard_next = False
        self._closing = False
        self.confirmation: ConfirmationDialog | None = None
        self.integration: IntegrationDialog | None = None
        self.identification = Identification()
        self._persist = False
        self.notice = ""
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
        form.setSpacing(14)
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
        self.properties = properties
        self.splitter.addWidget(properties)
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
        self.persist.toggled.connect(self.update_status)
        row.addWidget(self.persist)
        self.discard = QPushButton("Discard edits")
        self.discard.clicked.connect(self.discard_edits)
        row.addWidget(self.discard)
        self.apply = QPushButton("Preview changes")
        self.apply.setObjectName("previewChanges")
        self.apply.clicked.connect(self.start_preview)
        row.addWidget(self.apply)
        outer.addLayout(row)
        self.canvas.selected.connect(self.select_display)
        self.canvas.moved.connect(self.position_changed, Qt.ConnectionType.QueuedConnection)
        self.displays.currentRowChanged.connect(self.row_selected)
        self.resolution.currentIndexChanged.connect(self.resolution_changed)
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
        self.model.receive(inspection, discard=self._discard_next)
        self._discard_next = False
        caps = inspection.capabilities
        self.session_label.setText(f"Hyprland {caps.version or 'unknown'} · {caps.provider}")
        self.render_state()

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
                {m.name for m in self.model.inspection.monitors} if self.model.inspection else set()
            )
            for index, output in enumerate(draft.outputs, 1):
                state = (
                    "missing"
                    if output.name not in connected
                    else "enabled"
                    if output.enabled
                    else "disabled"
                )
                self.displays.addItem(f"{index}   {output.name}    ·    {state}")
                if output.name == selected:
                    self.displays.setCurrentRow(index - 1)
            self.canvas.display(draft, selected, not self.model.busy)
        self.loading = False
        self.load_properties()
        self.update_status()

    def load_properties(self) -> None:
        self.loading = True
        output = self.model.output(self.model.selected)
        self.properties.setEnabled(output is not None and not self.model.busy)
        if output and self.model.inspection:
            self.selected_title.setText(output.name)
            monitor = next(
                (m for m in self.model.inspection.monitors if m.name == output.name), None
            )
            self.enabled.setChecked(output.enabled)
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
        )
        self.render_state()

    def update_status(self) -> None:
        error = self.model.error()
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
            )
        )
        self.apply.setText(
            "Save current layout"
            if self.persist.isChecked() and not self.model.dirty
            else "Preview changes"
        )
        self.discard.setEnabled(self.model.dirty and not self.model.busy)
        self.revalidate_button.setEnabled(self.model.stale and not self.model.busy)
        for button in (
            self.setup_button,
            self.refresh_button,
            self.identify_button,
            self.recover_button,
        ):
            button.setEnabled(not self.model.busy)
        self.persist.setEnabled(not self.model.busy and self.ready)
        self.recover_button.setVisible(
            "recovery" in self.ownership_reason.lower()
            or "unfinished" in self.ownership_reason.lower()
        )

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

    def start_preview(self) -> None:
        if self.model.error() or not self.ready or not self.model.draft:
            return
        self.model.busy = True
        self._persist = self.persist.isChecked()
        self.render_state()
        self.preview_requested.emit(self.model.draft)
        if self.backend:
            self.backend.submit("preview", self.model.draft)

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
        if self.backend and self.backend.isRunning():
            event.ignore()
            self.hide()
            self._closing = True
            self.backend.shutdown()
        else:
            event.accept()

    def backend_finished(self) -> None:
        if self._closing:
            self.close()
            if self.quit_on_close:
                application = QApplication.instance()
                if application is not None:
                    application.quit()
