"""Proportional, keyboard-accessible display layout canvas."""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QKeyEvent, QPainter, QPen
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


class DisplayItem(QGraphicsObject):
    selected = Signal(str)
    moved = Signal(str, int, int)
    editing = Signal()

    def __init__(self, output: Output, number: int, layout: Layout, editable: bool) -> None:
        super().__init__()
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
        self.setToolTip(f"{output.name}: {output.mode} · scale {output.scale:g}")
        self.setZValue(2 if not output.mirror else 3)

    def boundingRect(self) -> QRectF:
        return self.rectangle.adjusted(-4, -4, 4, 4)

    def paint(
        self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = widget.palette() if widget else self.scene().views()[0].palette()
        fill = palette.base().color()
        if not self.output.enabled:
            fill = palette.alternateBase().color()
        border = palette.highlight().color() if self.isSelected() else palette.mid().color()
        painter.setPen(QPen(border, 3 if self.isSelected() else 1.5))
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
        if self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
            self.editing.emit()
        self.selected.emit(self.output.name)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
            x, y = snap(
                self.layout,
                self.output.name,
                round(self.pos().x() / FACTOR),
                round(self.pos().y() / FACTOR),
            )
            self.setPos(x * FACTOR, y * FACTOR)
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
    editing = Signal()

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
            item.editing.connect(self.editing.emit)
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
