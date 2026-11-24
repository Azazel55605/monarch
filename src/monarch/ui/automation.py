"""Explicit policy and login-startup controls; never confirms monitor previews."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
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
        self.setWindowTitle("Display automation")
        self.setModal(True)
        self.resize(720, 480)
        layout = QVBoxLayout(self)
        notice = QLabel(
            "Opt in to exclusive basic monitor control. Topology changes may capture the "
            "current basic layout for recovery. Every automatic preview still needs Keep; "
            "timeout restores it. Matching profiles take priority."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        form = QFormLayout()
        self.enabled = QCheckBox("Enable automatic display previews")
        self.enabled.setChecked(policy.enabled)
        self.new_displays = QCheckBox("Use the best advertised mode for new external displays")
        self.new_displays.setChecked(policy.new_displays)
        self.autostart = QCheckBox("Start Monarch in the tray at login")
        self.autostart.setChecked(autostart)
        form.addRow(self.enabled)
        form.addRow(self.new_displays)
        self.scale_1440p = QDoubleSpinBox()
        self.scale_4k = QDoubleSpinBox()
        for caption, field, value in (
            ("New 1440p display scale", self.scale_1440p, policy.scale_1440p),
            ("New 4K UHD display scale", self.scale_4k, policy.scale_4k),
        ):
            field.setRange(0.25, 8)
            field.setDecimals(3)
            field.setSingleStep(0.05)
            field.setSuffix("×")
            field.setValue(value)
            field.setToolTip("Monarch uses the closest scale that gives whole logical pixels.")
            field.setEnabled(policy.new_displays)
            self.new_displays.toggled.connect(field.setEnabled)
            form.addRow(caption, field)
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
            "Automatic previews wait while you have an unsaved draft."
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
        self.saved.emit(
            Policy(
                enabled=self.enabled.isChecked(),
                rules=rules,
                new_displays=self.new_displays.isChecked(),
                scale_1440p=self.scale_1440p.value(),
                scale_4k=self.scale_4k.value(),
            ),
            self.autostart.isChecked(),
        )
