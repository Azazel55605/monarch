"""Temporary native output labels using Qt's per-screen fullscreen request."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class Identification:
    def __init__(self) -> None:
        self.windows: list[QWidget] = []

    def close(self) -> None:
        for window in self.windows:
            window.close()
            window.deleteLater()
        self.windows = []

    def show(self, names: tuple[str, ...]) -> None:
        self.close()
        for screen in QGuiApplication.screens():
            if screen.name() not in names:
                continue
            number = names.index(screen.name()) + 1
            window = QWidget(
                None,
                Qt.WindowType.Tool
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.WindowDoesNotAcceptFocus
                | Qt.WindowType.WindowTransparentForInput,
            )
            window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            window.setWindowTitle("Monarch display identification")
            window.winId()
            handle = window.windowHandle()
            if handle is not None:
                handle.setTransientParent(None)  # type: ignore[arg-type]  # Qt accepts a null transient parent.
                handle.setScreen(screen)
            layout = QVBoxLayout(window)
            label = QLabel(f"{number}\n{screen.name()}")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(
                "background: #162331; color: white; border: 3px solid #63b3ff; "
                "border-radius: 18px; font-size: 36px; padding: 24px;"
            )
            label.setFixedSize(340, 190)
            layout.addWidget(label, 0, Qt.AlignmentFlag.AlignCenter)
            window.showFullScreen()
            self.windows.append(window)
        QTimer.singleShot(3000, self.close)
