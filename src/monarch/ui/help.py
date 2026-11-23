"""Offline user help and dependency notices installed with every application wheel."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout, QWidget

from monarch import __version__
from monarch.resources import text


class HelpDialog(QDialog):
    def __init__(self, *, notices: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About Monarch" if notices else "Monarch quick start and recovery")
        self.resize(780, 640)
        layout = QVBoxLayout(self)
        self.document = QTextBrowser()
        self.document.setOpenLinks(False)
        heading = f"# Monarch {__version__}\n\n" if notices else ""
        self.document.setMarkdown(heading + text("notices.md" if notices else "guide.md"))
        layout.addWidget(self.document)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
