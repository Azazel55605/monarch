"""Explicit policy and login-startup controls; never confirms monitor previews."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from monarch.domain.policy import Policy, Rule
from monarch.domain.profiles import Profile


class AutomationDialog(QDialog):
    saved = Signal(object, bool)

    def __init__(
        self,
        policy: Policy,
        profiles: tuple[Profile, ...],
        autostart: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Automatic profile switching")
        self.setModal(True)
        self.resize(720, 480)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "Opt in to exclusive basic monitor control. Topology changes may capture the "
            "current basic layout for recovery. Every automatic preview still needs Keep; "
            "timeout restores it. Unknown extra displays keep their current settings."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        form = QFormLayout()
        self.enabled = QCheckBox("Enable automatic profile previews")
        self.enabled.setChecked(policy.enabled)
        self.autostart = QCheckBox("Start Monarch in the tray at login")
        self.autostart.setChecked(autostart)
        form.addRow(self.enabled)
        form.addRow(self.autostart)
        layout.addLayout(form)
        self.table = QTableWidget(len(profiles), 5)
        self.table.setHorizontalHeaderLabels(
            ["Eligible", "Profile", "Match", "Priority", "Binding"]
        )
        self.rows = []
        rules = {r.profile: r for r in policy.rules}
        for row, profile in enumerate(profiles):
            rule = rules.get(profile.id)
            eligible = QCheckBox()
            eligible.setChecked(rule is not None)
            label = QLabel(profile.name)
            mode = QComboBox()
            mode.addItems(["exact", "subset"])
            mode.setCurrentText(rule.mode if rule else "exact")
            priority = QSpinBox()
            priority.setRange(-1000, 1000)
            priority.setValue(rule.priority if rule else 0)
            ports = QCheckBox("Saved ports")
            ports.setChecked(rule.connectors if rule else False)
            ports.setToolTip(
                "Explicitly bind identities to saved connector names. Keep the same cabling; "
                "identical displays cannot be distinguished physically."
            )
            for column, widget in enumerate((eligible, label, mode, priority, ports)):
                self.table.setCellWidget(row, column, widget)
            self.rows.append((profile.id, eligible, mode, priority, ports))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)
        hint = QLabel(
            "Higher priority wins, then exact matching, then more required outputs. "
            "Ties, absent/ambiguous identities and no match make no changes. "
            "Saved ports explicitly uses fixed cabling for otherwise ambiguous identities. "
            "Manual changes pin the session until Resume automatic switching."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def submit(self) -> None:
        rules = tuple(
            Rule(identifier, mode.currentText(), priority.value(), ports.isChecked())
            for identifier, enabled, mode, priority, ports in self.rows
            if enabled.isChecked()
        )
        self.saved.emit(Policy(self.enabled.isChecked(), rules), self.autostart.isChecked())
