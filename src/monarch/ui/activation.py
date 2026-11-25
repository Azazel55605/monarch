"""Open the editor or a quick panel in the current Hyprland session."""

import hashlib
import os

from PySide6.QtCore import QObject, Slot
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage

from monarch.resources import APP_ID
from monarch.ui.window import MainWindow

OBJECT_PATH = "/org/monarch/Monarch"


def service_name() -> str:
    session = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") or os.environ.get("WAYLAND_DISPLAY", "")
    return f"{APP_ID}.Session_{hashlib.sha256(session.encode()).hexdigest()[:24]}"


def forward_panel(bus: QDBusConnection, panel: str) -> bool:
    if not bus.isConnected():
        return False
    method = "OpenEditor" if panel == "editor" else "OpenPanel"
    message = QDBusMessage.createMethodCall(service_name(), OBJECT_PATH, APP_ID, method)
    if method == "OpenPanel":
        message.setArguments([panel])
    reply = bus.call(message, QDBus.CallMode.Block, 2000)
    return reply.type() == QDBusMessage.MessageType.ReplyMessage


class PanelActivation(QObject):
    def __init__(self, window: MainWindow, panel: str = "") -> None:
        super().__init__(window)
        self.window = window
        self.pending = panel
        self.loaded = False

    def register(self, bus: QDBusConnection) -> bool:
        if not bus.registerObject(
            OBJECT_PATH, APP_ID, self, QDBusConnection.RegisterOption.ExportAllSlots
        ):
            return False
        if bus.registerService(service_name()):
            return True
        bus.unregisterObject(OBJECT_PATH)
        return False

    def initialized(self) -> None:
        self.loaded = True
        if self.pending:
            panel, self.pending = self.pending, ""
            self.OpenPanel(panel)

    @Slot()
    def OpenEditor(self) -> None:
        self.window.show_editor()

    @Slot(str)
    def OpenPanel(self, panel: str) -> None:
        if panel not in {"controls", "external"}:
            return
        if not self.loaded:
            self.pending = panel
        elif panel == "controls":
            self.window.show_quick_panel()
        else:
            self.window.show_external_panel()
