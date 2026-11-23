"""Qt entry point with no compositor I/O on the application thread."""

import os
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from monarch.resources import APP_ID, icon_path
from monarch.ui.theme import ThemeController, discover_system_plugins
from monarch.ui.window import MainWindow
from monarch.ui.worker import BackendThread


def configure_app(app: QApplication) -> None:
    app.setApplicationName("Monarch")
    app.setOrganizationName("Monarch")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon.fromTheme(APP_ID, QIcon(icon_path())))
    # Native fonts, palette and widget rendering belong to the selected Qt theme.


def launch(
    directory: Path | None = None,
    *,
    profile: str = "",
    persist: bool = False,
    tray: bool = True,
    background: bool = False,
    profile_directory: Path | None = None,
) -> int:
    if os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
    discover_system_plugins()
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv[:1])
    configure_app(app)
    app.setQuitOnLastWindowClosed(not (tray and QSystemTrayIcon.isSystemTrayAvailable()))
    worker = BackendThread(managed=directory.expanduser().absolute() if directory else None)
    if profile_directory is not None:
        from monarch.storage.profiles import ProfileStore

        worker.profile_store = ProfileStore(profile_directory.expanduser().absolute())
    theme = ThemeController(app)
    window = MainWindow(
        worker,
        quit_on_close=True,
        theme=theme,
        startup_profile=profile,
        persist_profile=persist,
        tray_enabled=tray,
    )
    if theme.warning:
        window.notice = theme.warning
    window.showMinimized() if background else window.show()
    worker.start()
    result = app.exec()
    worker.shutdown()
    worker.wait()
    return result
