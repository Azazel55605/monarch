"""Use native Qt themes and compatible installed styles without a forced palette."""

import sysconfig
from pathlib import Path
from typing import cast

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QPluginLoader, QSettings
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QApplication, QMenu, QStyleFactory


def discover_system_plugins() -> tuple[str, ...]:
    # Wheels search their bundled tree only. Let Qt see installed theme/style
    # plugins when their metadata matches this runtime's major/minor ABI.
    version = QLibraryInfo.version()
    abi = (version.majorVersion(), version.minorVersion())
    multiarch = sysconfig.get_config_var("MULTIARCH")
    roots = [Path("/usr/lib/qt6/plugins"), Path("/usr/lib64/qt6/plugins")]
    if multiarch:
        roots.append(Path("/usr/lib") / multiarch / "qt6/plugins")
    accepted = []
    for root in roots:
        plugins = [*root.glob("styles/*.so"), *root.glob("platformthemes/*.so")]
        if any(
            (
                (v := cast(int, QPluginLoader(str(p)).metaData().get("version", 0))) >> 16,
                (v >> 8) & 255,
            )
            == abi
            for p in plugins
        ):
            accepted.append(str(root))
    paths = QCoreApplication.libraryPaths()
    QCoreApplication.setLibraryPaths(list(dict.fromkeys(paths + accepted)))
    return tuple(accepted)


class ThemeController:
    def __init__(self, app: QApplication, settings: QSettings | None = None) -> None:
        self.app = app
        self.settings = settings if settings is not None else QSettings()
        self.system_style = app.style().objectName()
        self.system_palette = app.palette()
        self.selected = str(self.settings.value("appearance/style", ""))
        self.warning = ""
        if self.selected and not self.apply(self.selected, save=False):
            self.warning = "Saved Qt style is unavailable; using the system theme."
            self.selected = ""

    def apply(self, name: str, *, save: bool = True) -> bool:
        style = QStyleFactory.create(name or self.system_style)
        if style is None:
            return False
        self.app.setStyle(style)
        self.app.setPalette(self.system_palette if not name else style.standardPalette())
        self.selected = name
        if save:
            self.settings.setValue("appearance/style", name)
            self.settings.sync()
        return True

    def menu(self, parent: QMenu) -> None:
        group = QActionGroup(parent)
        group.setExclusive(True)
        for name in ["", *QStyleFactory.keys()]:
            action = parent.addAction(name or "System theme")
            action.setCheckable(True)
            action.setChecked(name.casefold() == self.selected.casefold())
            group.addAction(action)
            action.triggered.connect(lambda checked=False, value=name: self.apply(value))
        parent.addSeparator()
        info = parent.addAction("System theme uses Qt platform settings (such as qt6ct)")
        info.setEnabled(False)
