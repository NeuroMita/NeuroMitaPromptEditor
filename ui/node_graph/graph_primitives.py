# File: ui/node_graph/graph_primitives.py
from __future__ import annotations
from typing import List, Optional, Callable, Dict

from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QMenu,
    QColorDialog,
)

# Строгая цветовая схема
NODE_BG = QColor("#202020")
NODE_BORDER = QColor("#999999")
NODE_SELECTED = QColor("#FFA500")
TEXT_FG = QColor("#FFFFFF")
TEXT_SECONDARY = QColor("#999999")
EXEC_EDGE = QColor("#FFFFFF")
BRANCH_EDGE = QColor("#FFA500")

PORT_EXEC_COLOR = QColor("#F0F0F0")
PORT_HOVER = QColor("#FFA500")


class PortItem(QGraphicsEllipseItem):
    R = 5

    def __init__(self, owner: "NodeItem", key: str, is_input: bool):
        super().__init__(-PortItem.R, -PortItem.R, 2 * PortItem.R, 2 * PortItem.R, owner)
        self.owner = owner
        self.key = key
        self.is_input = is_input
        self.edges: List["EdgeItem"] = []
        self.is_highlighted = False
        self.setBrush(QBrush(PORT_EXEC_COLOR))
        self.setPen(QPen(Qt.NoPen))
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

    def add_edge(self, e: "EdgeItem"):
        if e not in self.edges:
            self.edges.append(e)

    def remove_edge(self, e: "EdgeItem"):
        if e in self.edges:
            self.edges.remove(e)

    def center_in_scene(self) -> QPointF:
        return self.mapToScene(self.rect().center())

    def set_highlighted(self, on: bool):
        self.is_highlighted = on
        if on:
            self.setBrush(QBrush(PORT_HOVER))
            self.setPen(QPen(PORT_HOVER, 1.5))
        else:
            self.setBrush(QBrush(PORT_EXEC_COLOR))
            self.setPen(QPen(Qt.NoPen))

    def hoverEnterEvent(self, event):
        if not self.is_highlighted:
            self.setBrush(QBrush(PORT_HOVER))
        return super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.is_highlighted:
            self.setBrush(QBrush(PORT_EXEC_COLOR))
        return super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for e in list(self.edges):
                e.update_path()
        return super().itemChange(change, value)


class EdgeItem(QGraphicsPathItem):
    """
    ВАЖНО: добавлены методы detach_from_ports/destroy,
    чтобы удаление ребра было безопасным (без removeItem для item со сцены=None).
    """
    def __init__(self, source: PortItem, target: Optional[PortItem], is_branch: bool = False):
        super().__init__()
        self.source: Optional[PortItem] = source
        self.target: Optional[PortItem] = target
        self.temp_end: Optional[QPointF] = None
        self.is_branch = is_branch
        self.is_highlighted = False

        self._update_pen()
        self.setZValue(-1)
        if self.source:
            self.source.add_edge(self)
        if self.target:
            self.target.add_edge(self)
        self.update_path()

    def _update_pen(self):
        color = BRANCH_EDGE if self.is_branch else EXEC_EDGE
        width = 2.5 if self.is_highlighted else 2.0
        self.setPen(QPen(color, width))

    def set_highlighted(self, on: bool):
        self.is_highlighted = on
        self._update_pen()

    def set_target(self, t: Optional[PortItem]):
        if self.target is t:
            return
        if self.target:
            self.target.remove_edge(self)
        self.target = t
        if t:
            t.add_edge(self)
        self.update_path()

    def set_temp_end(self, p: Optional[QPointF]):
        self.temp_end = p
        self.update_path()

    def other_end(self, p: PortItem) -> Optional[PortItem]:
        if p is self.source:
            return self.target
        if p is self.target:
            return self.source
        return None

    def detach_from_ports(self):
        if self.source:
            self.source.remove_edge(self)
        if self.target:
            self.target.remove_edge(self)

    def destroy(self):
        """
        Безопасно удалить ребро:
        - убрать из списков портов;
        - убрать из сцены, если оно ещё там.
        """
        try:
            self.detach_from_ports()
        except Exception:
            pass
        sc = self.scene()
        if sc:
            try:
                sc.removeItem(self)
            except Exception:
                pass

    def update_path(self):
        # если source уже отцепили — ничего не делаем
        if self.source is None or self.source.scene() is None:
            return
        p1 = self.source.center_in_scene()
        if self.target and self.target.scene() is not None:
            p2 = self.target.center_in_scene()
        else:
            p2 = self.temp_end or p1

        path = QPainterPath(p1)
        dx = max(30.0, abs(p2.x() - p1.x()) * 0.5)
        c1 = QPointF(p1.x() + dx, p1.y())
        c2 = QPointF(p2.x() - dx, p2.y())
        path.cubicTo(c1, c2, p2)
        self.setPath(path)


class NodeItem(QGraphicsRectItem):
    WIDTH = 280
    HEIGHT = 96
    PADDING = 8

    def __init__(self, title: str, subtitle: str, payload, bg: QColor = NODE_BG):
        super().__init__(0, 0, NodeItem.WIDTH, NodeItem.HEIGHT)
        self.title = title
        self.subtitle = subtitle
        self.description = ""
        self.payload = payload
        self.custom_color: Optional[QColor] = None
        self._default_bg = bg
        self._in_ports: List[PortItem] = []
        self._out_ports: List[PortItem] = []
        self._port_labels_internal: Dict[str, QGraphicsSimpleTextItem] = {}
        self._on_moved: Optional[Callable[["NodeItem"], None]] = None
        self._on_color_changed: Optional[Callable[["NodeItem"], None]] = None

        self.setBrush(QBrush(bg))
        self.setPen(QPen(NODE_BORDER, 1.0))
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

    def set_description(self, desc: str):
        self.description = desc
        tooltip_parts = [self.title]
        if self.subtitle:
            tooltip_parts.append(self.subtitle)
        if desc:
            tooltip_parts.append(f"\n{desc}")
        self.setToolTip("\n".join(tooltip_parts))

    def set_custom_color(self, color: Optional[QColor]):
        self.custom_color = color
        if color:
            self.setBrush(QBrush(color))
        else:
            self.setBrush(QBrush(self._default_bg))
        self.update()
        if self._on_color_changed:
            try:
                self._on_color_changed(self)
            except Exception:
                pass

    def get_custom_color(self) -> Optional[QColor]:
        return self.custom_color

    def set_color_changed_callback(self, cb: Optional[Callable[["NodeItem"], None]]):
        self._on_color_changed = cb

    def contextMenuEvent(self, event):
        menu = QMenu()
        color_menu = menu.addMenu("Цвет ноды")
        colors = [
            ("По умолчанию", None),
            ("Красный", QColor("#4A1A1A")),
            ("Зелёный", QColor("#1A4A1A")),
            ("Синий", QColor("#1A1A4A")),
            ("Жёлтый", QColor("#4A4A1A")),
            ("Фиолетовый", QColor("#3A1A4A")),
            ("Бирюзовый", QColor("#1A4A4A")),
        ]
        for name, color in colors:
            action = color_menu.addAction(name)
            if color:
                pixmap = self._create_color_pixmap(color)
                from PySide6.QtGui import QIcon
                action.setIcon(QIcon(pixmap))
            action.triggered.connect(lambda checked=False, c=color: self.set_custom_color(c))
        color_menu.addSeparator()
        custom_action = color_menu.addAction("Выбрать цвет...")
        custom_action.triggered.connect(self._pick_custom_color)
        menu.exec(event.screenPos())
        event.accept()

    def _create_color_pixmap(self, color: QColor):
        from PySide6.QtGui import QPixmap, QPainter
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor("#666666"), 1))
        painter.drawRect(1, 1, 14, 14)
        painter.end()
        return pixmap

    def _pick_custom_color(self):
        current = self.custom_color if self.custom_color else self._default_bg
        color = QColorDialog.getColor(current, None, "Выбрать цвет ноды")
        if color.isValid():
            self.set_custom_color(color)

    # ---------- ports ----------
    def add_in_port(self, key: str, label: str) -> PortItem:
        p = PortItem(self, key, True)
        p.setToolTip(label)
        self._in_ports.append(p)
        self._layout_ports()
        return p

    def add_out_port(self, key: str, label: str) -> PortItem:
        p = PortItem(self, key, False)
        p.setToolTip(label)
        self._out_ports.append(p)
        if key != "exec":
            lab = QGraphicsSimpleTextItem(label, self)
            lab.setBrush(QBrush(TEXT_SECONDARY))
            f = lab.font()
            f.setPointSize(8)
            lab.setFont(f)
            self._port_labels_internal[key] = lab
            lab.setAcceptHoverEvents(True)
            lab.setData(0, key)
        self._layout_ports()
        return p

    def in_port(self, key: str) -> Optional[PortItem]:
        for p in self._in_ports:
            if p.key == key:
                return p
        return None

    def out_port(self, key: str) -> Optional[PortItem]:
        for p in self._out_ports:
            if p.key == key:
                return p
        return None

    def in_ports(self) -> List[PortItem]:
        return self._in_ports

    def out_ports(self) -> List[PortItem]:
        return self._out_ports

    def set_subtitle(self, txt: str):
        self.subtitle = txt
        self.update()

    def set_move_callback(self, cb: Optional[Callable[["NodeItem"], None]]):
        self._on_moved = cb

    def highlight_branch(self, port_key: str, on: bool):
        port = self.out_port(port_key)
        if port:
            port.set_highlighted(on)
            for edge in port.edges:
                edge.set_highlighted(on)

    # ---------- painting ----------
    def paint(self, painter, option, widget=None):
        pen = QPen(NODE_SELECTED if self.isSelected() else NODE_BORDER, 1.5 if self.isSelected() else 1.0)
        painter.setPen(pen)
        painter.setBrush(self.brush())
        painter.drawRoundedRect(self.rect(), 2, 2)

        painter.setPen(QPen(TEXT_FG))
        f = QFont()
        f.setBold(True)
        f.setPointSize(9)
        painter.setFont(f)
        painter.drawText(
            self.rect().adjusted(self.PADDING, self.PADDING, -self.PADDING, -self.PADDING),
            Qt.AlignTop | Qt.AlignLeft,
            self.title,
        )

        if self.subtitle:
            f2 = QFont()
            f2.setPointSize(8)
            painter.setFont(f2)
            painter.setPen(QPen(TEXT_SECONDARY))
            painter.drawText(
                self.rect().adjusted(self.PADDING, 26, -self.PADDING, -self.PADDING),
                Qt.AlignTop | Qt.AlignLeft,
                self.subtitle,
            )

    def _layout_ports(self):
        r = self.rect()

        # inputs
        if self._in_ports:
            if len(self._in_ports) == 1 or all(p.key == "exec" for p in self._in_ports):
                p = self._in_ports[0]
                y = r.center().y()
                p.setPos(r.left(), y)
            else:
                step = r.height() / (len(self._in_ports) + 1)
                for i, p in enumerate(self._in_ports, start=1):
                    y = r.top() + i * step
                    p.setPos(r.left(), y)

        # outputs
        exec_port = None
        branch_ports: List[PortItem] = []
        for p in self._out_ports:
            if p.key == "exec":
                exec_port = p
            elif p.key.startswith("branch_") or p.key == "else":
                branch_ports.append(p)

        if exec_port is not None:
            y = r.top() + 20
            exec_port.setPos(r.right(), y)

        if branch_ports:
            top_zone = r.top() + 45
            bottom = r.bottom() - 10
            n = len(branch_ports)
            if n == 1:
                y = (top_zone + bottom) * 0.5
                branch_ports[0].setPos(r.right(), y)
                lab = self._port_labels_internal.get(branch_ports[0].key)
                if lab:
                    br = lab.boundingRect()
                    lab.setPos(r.right() - br.width() - 16, y - br.height() / 2)
            else:
                total_h = max(1.0, bottom - top_zone)
                step = total_h / (n + 1)
                for i, p in enumerate(branch_ports, 1):
                    y = top_zone + i * step
                    p.setPos(r.right(), y)
                    lab = self._port_labels_internal.get(p.key)
                    if lab:
                        br = lab.boundingRect()
                        lab.setPos(r.right() - br.width() - 16, y - br.height() / 2)

        for p in self._in_ports + self._out_ports:
            for e in list(p.edges):
                e.update_path()

    def mousePressEvent(self, event):
        for key, lab in self._port_labels_internal.items():
            if lab.contains(lab.mapFromScene(event.scenePos())):
                self.highlight_branch(key, True)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        for key in self._port_labels_internal.keys():
            self.highlight_branch(key, False)
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for p in self._in_ports + self._out_ports:
                for e in list(p.edges):
                    e.update_path()
            if self._on_moved:
                try:
                    self._on_moved(self)
                except Exception:
                    pass
        return super().itemChange(change, value)