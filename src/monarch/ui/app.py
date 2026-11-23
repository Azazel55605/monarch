"""Qt entry point with no compositor I/O on the application thread."""

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from monarch.ui.window import MainWindow
from monarch.ui.worker import BackendThread


def configure_app(app: QApplication) -> None:
    app.setApplicationName("Monarch")
    app.setOrganizationName("Monarch")
    font = app.font()
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(
        "QPushButton {padding: 6px 10px;} "
        "QComboBox,QSpinBox,QDoubleSpinBox {min-height: 28px;} "
        "QPushButton#previewChanges {font-weight: bold;}"
    )


def launch(directory: Path | None = None) -> int:
    if os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv[:1])
    configure_app(app)
    worker = BackendThread(managed=directory.expanduser().absolute() if directory else None)
    window = MainWindow(worker, quit_on_close=True)
    window.show()
    worker.start()
    result = app.exec()
    worker.shutdown()
    worker.wait()
    return result
