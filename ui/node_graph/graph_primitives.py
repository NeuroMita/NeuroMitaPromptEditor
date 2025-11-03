# File: ui/node_graph/graph_primitives.py
from __future__ import annotations
from typing import List, Optional, Callable, Dict

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
)

NODE_BG = QColor("#2F3542")
NODE_BORDER = QColor("#57606f")
NODE_SELECTED = QColor("#70a1ff")
TEXT_FG = QColor("#ecf0f1")
EXEC_EDGE = QColor("#a4b0be")
BRANCH_EDGE = QColor("#ff7f50")

PORT_IN_COLOR = QColor("#4cd137")
PORT_OUT_COLOR = QColor("#487eb0")
PORT_HOVER = QColor("#e1b12c")
PORT_LABEL = QColor("#dfe6e9")


class PortItem(QGraphicsEllipseItem):
    R = 6

    def __init__(self, owner: "NodeItem", key: str, is_input: bool):
        super().__init__(-PortItem.R, -PortItem.R, 2 * PortItem.R, 2 * PortItem.R, owner)
        self.owner = owner
        self.key = key
        self.is_input = is_input
        self.edges: List["EdgeItem"] = []
        self.setBrush(QBrush(PORT_IN_COLOR if is_input else PORT_OUT_COLOR))
        self.setPen(QPen(Qt.black, 1.0))
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

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(PORT_HOVER))
        return super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(PORT_IN_COLOR if self.is_input else PORT_OUT_COLOR))
        return super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for e in list(self.edges):
                e.update_path()
        return super().itemChange(change, value)


class EdgeItem(QGraphicsPathItem):
    def __init__(self, source: PortItem, target: Optional[PortItem], is_branch: bool = False):
        super().__init__()
        self.source = source
        self.target = target
        self.temp_end: Optional[QPointF] = None
        self.is_branch = is_branch
        pen = QPen(BRANCH_EDGE if is_branch else EXEC_EDGE, 2.0)
        self.setPen(pen)
        self.setZValue(-1)
        source.add_edge(self)
        if target:
            target.add_edge(self)
        self.update_path()

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

    def update_path(self):
        # защита от удаленного source/target
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
        self.payload = payload  # AST node
        self._in_ports: List[PortItem] = []
        self._out_ports: List[PortItem] = []
        self._in_labels: Dict[str, QGraphicsSimpleTextItem] = {}
        self._out_labels: Dict[str, QGraphicsSimpleTextItem] = {}
        self._on_moved: Optional[Callable[["NodeItem"], None]] = None

        self.setBrush(QBrush(bg))
        self.setPen(QPen(NODE_BORDER, 1.5))
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )

    # ---------- ports ----------
    def add_in_port(self, key: str, label: str) -> PortItem:
        p = PortItem(self, key, True)
        p.setToolTip(f"in: {label}")
        self._in_ports.append(p)
        lab = QGraphicsSimpleTextItem(label, self)
        lab.setBrush(QBrush(PORT_LABEL))
        f = lab.font(); f.setPointSize(max(f.pointSize() - 1, 8)); lab.setFont(f)
        self._in_labels[key] = lab
        self._layout_ports()
        return p

    def add_out_port(self, key: str, label: str) -> PortItem:
        p = PortItem(self, key, False)
        p.setToolTip(f"out: {label}")
        self._out_ports.append(p)
        lab = QGraphicsSimpleTextItem(label, self)
        lab.setBrush(QBrush(PORT_LABEL))
        f = lab.font(); f.setPointSize(max(f.pointSize() - 1, 8)); lab.setFont(f)
        self._out_labels[key] = lab
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

    # ---------- painting ----------
    def paint(self, painter, option, widget=None):
        pen = QPen(NODE_SELECTED if self.isSelected() else NODE_BORDER, 2.0)
        painter.setPen(pen)
        painter.setBrush(self.brush())
        painter.drawRoundedRect(self.rect(), 6, 6)

        painter.setPen(QPen(TEXT_FG))
        f = QFont()
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(
            self.rect().adjusted(self.PADDING, self.PADDING, -self.PADDING, -self.PADDING),
            Qt.AlignTop | Qt.AlignLeft,
            self.title,
        )

        f2 = QFont()
        f2.setPointSize(max(f.pointSize() - 1, 8))
        painter.setFont(f2)
        painter.drawText(
            self.rect().adjusted(self.PADDING, 28, -self.PADDING, -self.PADDING),
            Qt.AlignTop | Qt.AlignLeft,
            self.subtitle,
        )

    def _layout_ports(self):
        r = self.rect()

        # -------- inputs (exec in) --------
        if self._in_ports:
            # единственный exec-in — слева по центру
            if len(self._in_ports) == 1 or all(p.key == "exec" for p in self._in_ports):
                p = self._in_ports[0]
                y = r.center().y()
                p.setPos(r.left(), y)
                lab = self._in_labels.get(p.key)
                if lab:
                    br = lab.boundingRect()
                    lab.setPos(r.left() - br.width() - 8, y - br.height() / 2)
            else:
                step = r.height() / (len(self._in_ports) + 1)
                for i, p in enumerate(self._in_ports, start=1):
                    y = r.top() + i * step
                    p.setPos(r.left(), y)
                    lab = self._in_labels.get(p.key)
                    if lab:
                        br = lab.boundingRect()
                        lab.setPos(r.left() - br.width() - 8, y - br.height() / 2)

        # -------- outputs --------
        exec_port = None
        branch_ports: List[PortItem] = []
        for p in self._out_ports:
            if p.key == "exec":
                exec_port = p
            elif p.key.startswith("branch_") or p.key == "else":
                branch_ports.append(p)

        # exec-out — СВЕРХУ справа с небольшим отступом
        if exec_port is not None:
            y = r.top() + 16
            exec_port.setPos(r.right(), y)
            lab = self._out_labels.get(exec_port.key)
            if lab:
                br = lab.boundingRect()
                lab.setPos(r.right() + 8, y - br.height() / 2)

        # ветви IF — ниже exec-out, каждая на своей строке
        if branch_ports:
            top_zone = (r.top() + 40)   # чтобы не прилипало к exec-out/заголовку
            bottom = r.bottom() - 12
            n = len(branch_ports)
            if n == 1:
                y = (top_zone + bottom) * 0.5
                branch_ports[0].setPos(r.right(), y)
                lab = self._out_labels.get(branch_ports[0].key)
                if lab:
                    br = lab.boundingRect()
                    lab.setPos(r.right() + 8, y - br.height() / 2)
            else:
                total_h = max(1.0, bottom - top_zone)
                step = total_h / (n + 1)
                for i, p in enumerate(branch_ports, 1):
                    y = top_zone + i * step
                    branch_ports[i - 1].setPos(r.right(), y)
                    lab = self._out_labels.get(p.key)
                    if lab:
                        br = lab.boundingRect()
                        lab.setPos(r.right() + 8, y - br.height() / 2)

        # обновить рёбра
        for p in self._in_ports + self._out_ports:
            for e in list(p.edges):
                e.update_path()

    # ---------- edges follow the node ----------
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