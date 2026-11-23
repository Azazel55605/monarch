"""Explicit integration preview and guard-owned confirmation surfaces."""

import math
import time
from pathlib import Path

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from monarch.storage.integration import IntegrationPlan


class ConfirmationDialog(QDialog):
    decision = Signal(bool, bool)

    def __init__(self, deadline: float, persist: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keep this display layout?")
        self.setObjectName("confirmationDialog")
        self.setModal(True)
        self.deadline = deadline
        self.persist = persist
        self.sent = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Are all displays working as expected?"))
        self.countdown = QLabel()
        self.countdown.setAccessibleName("Seconds before automatic revert")
        layout.addWidget(self.countdown)
        layout.addWidget(
            QLabel(
                "Keeping also saves this layout on login."
                if persist
                else "Keeping changes this session only."
            )
        )
        buttons = QDialogButtonBox()
        self.revert = buttons.addButton("Revert", QDialogButtonBox.ButtonRole.RejectRole)
        self.keep = buttons.addButton("Keep changes", QDialogButtonBox.ButtonRole.AcceptRole)
        self.keep.setObjectName("keepChanges")
        self.revert.setObjectName("revertChanges")
        self.revert.setDefault(True)
        self.keep.setAutoDefault(False)
        self.keep.clicked.connect(lambda: self.choose(True))
        self.revert.clicked.connect(lambda: self.choose(False))
        layout.addWidget(buttons)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self.tick()

    def tick(self) -> None:
        remaining = max(0, math.ceil(self.deadline - time.monotonic()))
        self.countdown.setText(f"Automatically reverting in {remaining} seconds.")
        if remaining <= 0:
            self.keep.setEnabled(False)
            self.countdown.setText("The guard is restoring the previous layout…")

    def choose(self, keep: bool) -> None:
        if self.sent:
            return
        self.sent = True
        self.keep.setEnabled(False)
        self.revert.setEnabled(False)
        self.countdown.setText("Confirming…" if keep else "Restoring the previous layout…")
        self.decision.emit(keep, self.persist if keep else False)

    def reject(self) -> None:
        self.choose(False)

    def finish(self) -> None:
        self.timer.stop()
        super().accept()


class IntegrationDialog(QDialog):
    prepare = Signal(object, object)
    install = Signal()

    def __init__(self, root: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._has_plan = False
        self.setWindowTitle("Set up monitor management")
        self.setModal(True)
        self.resize(780, 660)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Monarch adds one managed include at the end of your Lua config. "
            "Your existing settings stay in place and a private backup is kept. "
            "Review the change before installing it."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.root = QLineEdit(str(root) if root else "")
        self.root.setAccessibleName("Hyprland Lua root")
        row = QHBoxLayout()
        row.addWidget(self.root)
        choose = QPushButton("Choose root…")
        row.addWidget(choose)
        layout.addLayout(row)
        choose.clicked.connect(self.choose_root)
        label = QLabel(
            "Add every other configuration file loaded by this root. Changes to these files "
            "will pause monitor management until reviewed."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        self.dependencies = QListWidget()
        self.dependencies.setMaximumHeight(90)
        self.dependencies.setAccessibleName("Declared configuration dependencies")
        layout.addWidget(self.dependencies)
        row = QHBoxLayout()
        add = QPushButton("Add files…")
        remove = QPushButton("Remove selected")
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)
        add.clicked.connect(self.add_dependencies)
        remove.clicked.connect(lambda: self.dependencies.takeItem(self.dependencies.currentRow()))
        self.approval = QCheckBox(
            "I delegate this config's basic monitor settings to Monarch and approve reloads."
        )
        layout.addWidget(self.approval)
        info = QLabel(
            "Default-path sessions require a full Lua context reset during guarded reloads. "
            "Advanced HDR, VRR and color rules are outside this integration contract. "
            "Keep other display managers disabled. Dynamic monitor rules or undeclared "
            "configuration files are outside this integration contract."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName("Exact integration diff")
        layout.addWidget(self.preview, 1)
        row = QHBoxLayout()
        prepare = QPushButton("Preview integration")
        self.install_button = QPushButton("Install reviewed include")
        self.install_button.setEnabled(False)
        self.install_button.setObjectName("installIntegration")
        close = QPushButton("Close")
        row.addWidget(prepare)
        row.addStretch()
        row.addWidget(close)
        row.addWidget(self.install_button)
        layout.addLayout(row)
        close.clicked.connect(self.reject)
        prepare.clicked.connect(self.request_preview)
        self.install_button.clicked.connect(self.request_install)
        self.approval.toggled.connect(self.approval_changed)
        self.root.textChanged.connect(self.invalidate)
        self.dependencies.model().rowsInserted.connect(self.invalidate)
        self.dependencies.model().rowsRemoved.connect(self.invalidate)

    def choose_root(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Hyprland Lua root", self.root.text(), "Lua config (*.lua)"
        )
        if path:
            self.root.setText(path)

    def add_dependencies(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose loaded configuration files", "", "All files (*)"
        )
        existing = {self.dependencies.item(i).text() for i in range(self.dependencies.count())}
        for path in paths:
            if path not in existing:
                self.dependencies.addItem(path)
                existing.add(path)

    def invalidate(self, *args: object) -> None:
        self._has_plan = False
        self.install_button.setEnabled(False)

    def approval_changed(self, approved: bool) -> None:
        self.install_button.setEnabled(self._has_plan and approved)

    def request_preview(self) -> None:
        self.prepare.emit(
            Path(self.root.text()).expanduser().absolute(),
            tuple(Path(self.dependencies.item(i).text()) for i in range(self.dependencies.count())),
        )

    def show_plan(self, plan: IntegrationPlan) -> None:
        self._has_plan = True
        self.preview.setPlainText(
            (
                plan.diff()
                or "The include stays unchanged. This review registers the current root "
                "and declared file revisions.\n"
            )
            + "\nManaged settings: "
            + str(plan.root.parent / "monarch" / "monarch_monitors.lua")
            + "\nA private backup of the original root will be kept alongside the registration."
        )
        if plan.baseline_preview:
            self.preview.appendPlainText("\nCurrent layout saved by this integration:")
            for output in plan.baseline_preview.outputs:
                state = (
                    output.mode + f" · scale {output.scale:g} · {output.x}, {output.y}"
                    if output.enabled
                    else "disabled"
                )
                self.preview.appendPlainText(output.name + ": " + state)
        self.install_button.setEnabled(self.approval.isChecked())

    def request_install(self) -> None:
        self.install_button.setEnabled(False)
        self.install.emit()
