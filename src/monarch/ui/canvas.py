"""Proportional, keyboard-accessible display layout canvas."""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QGraphicsView,
    QStyleOptionGraphicsItem,
    QWidget,
)

from monarch.domain.layout import Layout, Output
from monarch.ui.model import size, snap

FACTOR = 0.16
SNAP_PIXELS = 12


def contrast(first: QColor, second: QColor) -> float:
    def luminance(color: QColor) -> float:
        channels = (color.redF(), color.greenF(), color.blueF())
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

    a, b = luminance(first), luminance(second)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def display_colors(palette: QPalette, *, selected: bool, enabled: bool) -> tuple[QColor, QColor]:
    fill = palette.base().color() if enabled else palette.alternateBase().color()
    if fill.alpha() == 0:
        fill = palette.window().color()
    fill.setAlpha(255)
    border = palette.highlight().color() if selected else palette.mid().color()
    if border.alpha() < 255 or contrast(fill, border) < 3:
        border = palette.text().color()
        border.setAlpha(255)
        if contrast(fill, border) < 3:
            border = max((QColor("black"), QColor("white")), key=lambda c: contrast(fill, c))
    return fill, border


class DisplayItem(QGraphicsObject):
    selected = Signal(str)
    moved = Signal(str, int, int)

    def __init__(self, output: Output, number: int, layout: Layout, editable: bool) -> None:
        super().__init__()
        self._dragged = False
        self.output = output
        self.number = number
        self.layout = layout
        width, height = size(output)
        self.rectangle = (
            QRectF(0, 0, width * FACTOR, height * FACTOR)
            if output.enabled
            else QRectF(0, 0, 180, 118)
        )
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setPos(output.x * FACTOR, output.y * FACTOR)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
            editable and output.enabled and not output.mirror,
        )
        self.setToolTip(
            f"{output.name}: {output.mode} · scale {output.scale:g}\n"
            "Drag to snap to nearby displays; hold Alt to move freely."
        )
        self.setZValue(2 if not output.mirror else 3)

    def boundingRect(self) -> QRectF:
        return self.rectangle.adjusted(-4, -4, 4, 4)

    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = widget.palette() if widget else self.scene().views()[0].palette()
        fill, border = display_colors(
            palette, selected=self.isSelected(), enabled=self.output.enabled
        )
        pen = QPen(border, 3 if self.isSelected() else 1.5)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(fill)
        painter.drawRoundedRect(self.rectangle, 10, 10)
        painter.setPen(palette.text().color())
        font = painter.font()
        font.setPointSize(24)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            self.rectangle.adjusted(18, 14, -12, -12), Qt.AlignmentFlag.AlignTop, str(self.number)
        )
        font.setPointSize(11)
        painter.setFont(font)
        text = self.output.name
        if self.output.mirror:
            text += " · mirror"
        label = painter.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, max(1, int(self.rectangle.width() - 30))
        )
        painter.drawText(self.rectangle.adjusted(18, 59, -12, -8), Qt.AlignmentFlag.AlignTop, label)
        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        w, h = size(self.output)
        painter.drawText(
            self.rectangle.adjusted(18, 86, -12, -8),
            Qt.AlignmentFlag.AlignTop,
            (
                f"{round(w)} × {round(h)}\n{self.output.scale:g}× scale"
                if self.output.enabled
                else "Disabled"
            ),
        )

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._dragged = False
        self.selected.emit(self.output.name)
        super().mousePressEvent(event)

    def snap_position(self, *, bypass: bool = False) -> tuple[int, int]:
        x, y = round(self.pos().x() / FACTOR), round(self.pos().y() / FACTOR)
        if not bypass:
            views = self.scene().views()
            zoom = abs(views[0].transform().m11()) if views else 1
            x, y = snap(
                self.layout,
                self.output.name,
                x,
                y,
                threshold=SNAP_PIXELS / max(FACTOR * zoom, 0.001),
            )
        self.setPos(x * FACTOR, y * FACTOR)
        return x, y

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseMoveEvent(event)
        if self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
            self._dragged = True
            self.snap_position(bypass=bool(event.modifiers() & Qt.KeyboardModifier.AltModifier))

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._dragged and self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
            x, y = self.snap_position(
                bypass=bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
            )
            self.moved.emit(self.output.name, x, y)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        directions: dict[int, tuple[int, int]] = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }
        if (
            event.key() in directions
            and self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        ):
            dx, dy = directions[event.key()]
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            x = round(self.pos().x() / FACTOR) + dx * step
            y = round(self.pos().y() / FACTOR) + dy * step
            self.setPos(x * FACTOR, y * FACTOR)
            self.moved.emit(self.output.name, x, y)
            event.accept()
        else:
            super().keyPressEvent(event)


class LayoutCanvas(QGraphicsView):
    selected = Signal(str)
    moved = Signal(str, int, int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("layoutCanvas")
        self.setAccessibleName("Display layout canvas")
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumSize(480, 300)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.items_by_name: dict[str, DisplayItem] = {}

    def display(self, layout: Layout, selected: str, editable: bool) -> None:
        had_focus = self.hasFocus()
        self.scene().clear()
        self.items_by_name = {}
        enabled = [o for o in layout.outputs if o.enabled]
        bottom = max(((o.y + size(o)[1]) * FACTOR for o in enabled), default=0)
        left = min((o.x * FACTOR for o in enabled), default=0)
        disabled = 0
        for index, output in enumerate(layout.outputs, 1):
            item = DisplayItem(output, index, layout, editable)
            self.scene().addItem(item)
            if not output.enabled:
                item.setPos(left + disabled * 200, bottom + 35)
                disabled += 1
            item.selected.connect(self.selected.emit)
            item.moved.connect(self.moved.emit)
            item.setSelected(output.name == selected)
            if had_focus and output.name == selected:
                item.setFocus()
            self.items_by_name[output.name] = item
        rect = self.scene().itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self.scene().setSceneRect(rect)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def select(self, name: str) -> None:
        for key, item in self.items_by_name.items():
            item.setSelected(key == name)
            if key == name:
                item.setFocus()

    def fit(self) -> None:
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self.fit()
