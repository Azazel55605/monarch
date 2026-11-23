"""Compact tray dialogs for profiles and external display placement."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QStyle,
    QToolButton,
    QWidget,
)


def icon_button(
    parent: QWidget, label: str, name: str, fallback: QStyle.StandardPixmap
) -> QToolButton:
    button = QToolButton(parent)
    button.setText(label)
    button.setIcon(QIcon.fromTheme(name, parent.style().standardIcon(fallback)))
    button.setIconSize(QSize(24, 24))
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    button.setAccessibleName(label.replace("\n", " "))
    return button


def quick_dialog(title: str, parent: QWidget) -> QDialog:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    return dialog


class ExternalDialog(QDialog):
    def __init__(
        self, targets: list[str], anchors: list[str], preferred: str, parent: QWidget
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("External display layout")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.target = QComboBox()
        self.target.addItems(targets)
        self.anchor = QComboBox()
        self.preferred = preferred
        self.anchors = anchors
        self.target.currentTextChanged.connect(self.update_anchors)
        self.update_anchors(self.target.currentText())
        form = QFormLayout(self)
        form.addRow("External display", self.target)
        form.addRow("Reference display", self.anchor)
        row = QHBoxLayout()
        self.layout_buttons = {}
        sp = QStyle.StandardPixmap
        for key, label, theme_icon, fallback in (
            ("left", "Extend left", "go-previous", sp.SP_ArrowLeft),
            ("right", "Extend right", "go-next", sp.SP_ArrowRight),
            ("above", "Extend above", "go-up", sp.SP_ArrowUp),
            ("below", "Extend below", "go-down", sp.SP_ArrowDown),
            ("duplicate", "Duplicate", "edit-copy", sp.SP_FileDialogDetailedView),
        ):
            button = icon_button(self, label.replace(" ", "\n", 1), theme_icon, fallback)
            self.layout_buttons[key] = button
            row.addWidget(button)
        form.addRow(row)

    def update_anchors(self, target: str) -> None:
        current = self.anchor.currentText()
        self.anchor.clear()
        self.anchor.addItems([name for name in self.anchors if name != target])
        if self.anchor.findText(current) >= 0:
            self.anchor.setCurrentText(current)
        elif self.anchor.findText(self.preferred) >= 0:
            self.anchor.setCurrentText(self.preferred)
