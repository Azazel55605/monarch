"""Profile actions produce requests; all filesystem/discovery work stays in the worker."""

from functools import partial

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from monarch.domain.monitors import Monitor
from monarch.domain.profiles import Profile, candidates_for


class ProfileBar(QWidget):
    request = Signal(str, object)
    load = Signal(str, bool)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.selector = QComboBox()
        self.selector.setAccessibleName("Saved profiles")
        self.selector.setMinimumContentsLength(18)
        row.addWidget(self.selector, 1)
        self.edit = QPushButton("Load to editor")
        self.edit.clicked.connect(lambda: self.load.emit(self.key(), False))
        row.addWidget(self.edit)
        self.switch = QPushButton("Switch profile…")
        self.switch.clicked.connect(lambda: self.load.emit(self.key(), True))
        row.addWidget(self.switch)
        self.actions_button = QToolButton()
        self.actions_button.setText("Profiles")
        self.actions_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu = QMenu(self)
        for label, operation in [
            ("Save observed layout as…", "capture"),
            ("Save edited layout as…", "save"),
            ("Update selected from edited layout…", "update"),
            ("Rename selected…", "rename"),
            ("Delete selected…", "delete"),
            ("Import profiles…", "import"),
            ("Export selected…", "export"),
            ("Refresh profiles", "list"),
        ]:
            self.menu.addAction(label, partial(self.action, operation))
        self.actions_button.setMenu(self.menu)
        row.addWidget(self.actions_button)
        self.profiles: tuple[Profile, ...] = ()
        self.populate(())

    def key(self) -> str:
        return str(self.selector.currentData() or "")

    def populate(self, profiles: tuple[Profile, ...]) -> None:
        key = self.key()
        self.profiles = profiles
        self.selector.clear()
        for profile in sorted(profiles, key=lambda p: p.name.casefold()):
            self.selector.addItem(profile.name, profile.id)
        if not profiles:
            self.selector.addItem("No saved profiles", "")
        selected = self.selector.findData(key)
        if selected >= 0:
            self.selector.setCurrentIndex(selected)
        self.edit.setEnabled(bool(profiles))
        self.switch.setEnabled(bool(profiles))

    def action(self, operation: str) -> None:
        key = self.key()
        if operation in {"update", "rename", "delete", "export"} and not key:
            return
        if operation in {"capture", "save", "rename"}:
            name, ok = QInputDialog.getText(
                self,
                "Profile name",
                "Name:",
                text=self.selector.currentText() if operation == "rename" else "",
            )
            if ok:
                self.request.emit(operation, {"name": name, "key": key})
        elif operation in {"update", "delete"}:
            if (
                QMessageBox.question(
                    self,
                    "Change saved profile?",
                    f"{operation.title()} {self.selector.currentText()}?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                == QMessageBox.StandardButton.Yes
            ):
                self.request.emit(operation, {"key": key})
        elif operation in {"import", "export"}:
            chooser = (
                QFileDialog.getOpenFileName
                if operation == "import"
                else QFileDialog.getSaveFileName
            )
            filename, _ = chooser(
                self, "Profile JSON (contains monitor identities)", "", "JSON (*.json)"
            )
            if filename:
                self.request.emit(operation, {"key": key, "path": filename})
        else:
            self.request.emit(operation, {})


class MappingDialog(QDialog):
    """Bindings are explicit for this load only and checked again against live topology."""

    mapped = Signal(object)

    def __init__(
        self, profile: Profile, monitors: tuple[Monitor, ...], reason: str, parent: QWidget
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Map profile displays")
        self.setModal(True)
        layout = QVBoxLayout(self)
        label = QLabel(
            reason + "\nChoose each physical display explicitly. No settings change here."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        form = QFormLayout()
        self.choices: dict[str, QComboBox] = {}
        for output in profile.layout.outputs:
            choice = QComboBox()
            choice.addItem("Choose a connected display…", "")
            for monitor in candidates_for(output, monitors):
                choice.addItem(f"{monitor.name} — {monitor.make} {monitor.model}", monitor.name)
            form.addRow(output.name, choice)
            self.choices[output.name] = choice
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setEnabled(False)
        for choice in self.choices.values():
            choice.currentIndexChanged.connect(self.validate)
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def validate(self) -> None:
        values = [str(choice.currentData() or "") for choice in self.choices.values()]
        self.ok.setEnabled(all(values) and len(set(values)) == len(values))

    def submit(self) -> None:
        self.mapped.emit({key: str(choice.currentData()) for key, choice in self.choices.items()})
        self.accept()
