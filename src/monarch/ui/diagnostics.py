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
    def __init__(self, state: AdvancedState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Advanced display settings")
        self.resize(960, 460)
        self.setModal(True)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Observation snapshot. VRR Off/On is available in the display editor. "
            "Hardware flags, current state and validated write support are different evidence."
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
                    "Editor: Off/On" if feature.writable else "Unavailable",
                    feature.reason,
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
