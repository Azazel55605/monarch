"""Read-only advanced state and a redacted, explicitly exported support snapshot."""

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from monarch.domain.advanced import AdvancedState, features


class AdvancedDialog(QDialog):
    hdr_requested = Signal()

    def __init__(
        self, state: AdvancedState, parent: QWidget | None = None, *, hdr_ready: bool = False
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Advanced display settings")
        self.resize(960, 460)
        self.setModal(True)
        layout = QVBoxLayout(self)
        note = QLabel(
            "VRR is available in the display editor. The HDR preview returns to SDR "
            "when the timer expires or you choose Revert."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        rows = features(state)
        self.table = QTableWidget(len(rows), 4)
        self.table.setHorizontalHeaderLabels(["Setting", "Observed", "Control", "Why unavailable"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for row, feature in enumerate(rows):
            for column, text in enumerate(
                (
                    feature.label,
                    feature.observation,
                    "Timed preview"
                    if feature.key == "hdr" and hdr_ready
                    else "Editor: Off/On"
                    if feature.writable
                    else "Unavailable",
                    "Verify HDR using the monitor’s on-screen display."
                    if feature.key == "hdr" and hdr_ready
                    else feature.reason,
                )
            ):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(3, 420)
        self.table.resizeRowsToContents()
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        hdr = buttons.addButton("Preview HDR…", QDialogButtonBox.ButtonRole.ActionRole)
        hdr.setEnabled(hdr_ready)
        hdr.setToolTip(
            "Requires a clean managed SDR layout, an HDR-capable display, "
            "and another active independent display."
        )
        hdr.clicked.connect(self.hdr_requested.emit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class DiagnosticsDialog(QDialog):
    save_requested = Signal(object, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Redacted diagnostics")
        self.resize(800, 600)
        self.setModal(True)
        layout = QVBoxLayout(self)
        note = QLabel(
            "This report omits output identities, config paths/content, profile names, "
            "session IDs and raw logs. Review the snapshot before sharing it."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.text = QPlainTextEdit("Collecting read-only diagnostics…")
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.copy = QPushButton("Copy report")
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(self.text.toPlainText()))
        self.save = QPushButton("Save report…")
        self.save.clicked.connect(self.choose_file)
        self.copy.setEnabled(False)
        self.save.setEnabled(False)
        buttons.addButton(self.copy, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(self.save, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.data: dict[str, Any] | None = None

    def receive(self, data: dict[str, Any]) -> None:
        self.data = data
        self.text.setPlainText(json.dumps(data, indent=2, ensure_ascii=True, allow_nan=False))
        self.copy.setEnabled(True)
        self.save.setEnabled(True)

    def choose_file(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save to a new private file", "monarch-diagnostics.json", "JSON (*.json)"
        )
        if filename and self.data:
            self.save_requested.emit(Path(filename).expanduser().absolute(), self.data)
