# ui/node_graph/graph_scene.py
from __future__ import annotations
from typing import Optional
import logging

from PySide6.QtCore import QPointF, Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QFrame

from ui.node_graph.graph_primitives import EdgeItem, NodeItem, PortItem

log = logging.getLogger("node_graph.scene")
log.setLevel(logging.DEBUG)
log.propagate = True

class GraphScene(QGraphicsScene):
    node_selected = Signal(object)                 # ast_node
    connection_finished = Signal(object, object)   # (source_port:PortItem, target_port:PortItem)
    request_create_menu = Signal(object, object)   # (source_port_or_None, scene_pos:QPointF)
    edge_disconnect_requested = Signal(object)     # src_port: PortItem (whose outgoing connection to sever)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_edge: Optional[EdgeItem] = None
        self._drag_source: Optional[PortItem] = None
        self._is_clearing: bool = False
        self._is_reconnecting: bool = False
        self._reconnect_old_target_port: Optional[PortItem] = None
        self.setSceneRect(-5000, -5000, 10000, 10000)
        self.selectionChanged.connect(self._on_selection_changed)
        log.debug("GraphScene.__init__: scene created, rect=%s", self.sceneRect())

    def clear(self):
        log.debug("GraphScene.clear: begin (items=%d)", len(self.items()))
        self._is_clearing = True
        try:
            super().clear()
        finally:
            self._is_clearing = False
            log.debug("GraphScene.clear: end (items=%d)", len(self.items()))

    def _is_alive_item(self, it) -> bool:
        try:
            alive = (it is not None) and (it.scene() is not None)
        except RuntimeError:
            alive = False
        if not alive:
            log.debug("GraphScene._is_alive_item: item dead %s", repr(it))
        return alive

    def _node_under_pos(self, scene_pos) -> Optional[NodeItem]:
        view = self.views()[0] if self.views() else None
        if not view:
            return None
        it = self.itemAt(scene_pos, view.transform())
        if not self._is_alive_item(it):
            return None
        cur = it
        while cur and not isinstance(cur, NodeItem):
            try:
                cur = cur.parentItem()
            except RuntimeError:
                return None
        if cur and self._is_alive_item(cur):
            return cur
        return None

    def _port_under_pos(self, scene_pos) -> Optional[PortItem]:
        view = self.views()[0] if self.views() else None
        if not view:
            return None
        it = self.itemAt(scene_pos, view.transform())
        if isinstance(it, PortItem) and self._is_alive_item(it):
            return it
        return None

    def _edge_under_pos(self, scene_pos) -> Optional[EdgeItem]:
        view = self.views()[0] if self.views() else None
        if not view:
            return None
        for it in self.items(scene_pos, Qt.IntersectsItemShape, Qt.DescendingOrder, view.transform()):
            if isinstance(it, EdgeItem) and self._is_alive_item(it):
                return it
        return None

    # ------- interaction for connections -------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            port = self._port_under_pos(event.scenePos())
            # Grab the TARGET (input) end of an existing edge → reconnect drag
            if port and port.is_input and port.edges:
                edge = port.edges[-1]
                if self._is_alive_item(edge) and edge.source and self._is_alive_item(edge.source):
                    self._reconnect_old_target_port = port
                    edge.set_target(None)
                    edge.set_temp_end(event.scenePos())
                    self._drag_edge = edge
                    self._drag_source = edge.source
                    self._is_reconnecting = True
                    event.accept()
                    return
            # Drag from output port → new connection
            if port and not port.is_input:
                self._drag_source = port
                self._drag_edge = EdgeItem(port, None, is_branch=("branch" in port.key or port.key == "else"))
                self.addItem(self._drag_edge)
                self._drag_edge.set_temp_end(event.scenePos())
                self._is_reconnecting = False
                self._reconnect_old_target_port = None
                event.accept()
                return

        if event.button() == Qt.RightButton:
            # Right-click on an edge → disconnect context menu
            edge = self._edge_under_pos(event.scenePos())
            if edge and self._is_alive_item(edge) and edge.source and self._is_alive_item(edge.source):
                from PySide6.QtWidgets import QMenu
                menu = QMenu()
                act_disconnect = menu.addAction("Отцепить соединение")
                view = self.views()[0] if self.views() else None
                act = menu.exec(view.mapToGlobal(view.mapFromScene(event.scenePos())) if view else event.screenPos().toPoint())
                if act == act_disconnect:
                    src_port = edge.source
                    try:
                        edge.destroy()
                    except Exception:
                        pass
                    self.edge_disconnect_requested.emit(src_port)
                event.accept()
                return
            node = self._node_under_pos(event.scenePos())
            if node is None:
                self.request_create_menu.emit(None, event.scenePos())
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_edge:
            if (self._drag_source is None) or (not self._is_alive_item(self._drag_source)):
                try:
                    if self._drag_edge:
                        self._drag_edge.destroy()
                except Exception:
                    pass
                self._drag_edge = None
                self._drag_source = None
                self._is_reconnecting = False
                self._reconnect_old_target_port = None
                event.accept()
                return
            self._drag_edge.set_temp_end(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_edge and self._drag_source:
            target: Optional[PortItem] = self._port_under_pos(event.scenePos())
            if target and target.is_input and target.owner is not self._drag_source.owner:
                if self._is_reconnecting and target is self._reconnect_old_target_port:
                    # Released back on the original port → restore (no-op)
                    self._drag_edge.set_target(target)
                else:
                    # Connect (new or reconnect to different port)
                    try:
                        if self._drag_edge:
                            self._drag_edge.destroy()
                    except Exception:
                        pass
                    self.connection_finished.emit(self._drag_source, target)
            else:
                if self._is_reconnecting:
                    # Released on empty while reconnecting → disconnect
                    src_port = self._drag_source
                    try:
                        if self._drag_edge:
                            self._drag_edge.destroy()
                    except Exception:
                        pass
                    self.edge_disconnect_requested.emit(src_port)
                else:
                    try:
                        if self._drag_edge:
                            self._drag_edge.destroy()
                    except Exception:
                        pass
                    self.request_create_menu.emit(self._drag_source, event.scenePos())

            self._drag_edge = None
            self._drag_source = None
            self._is_reconnecting = False
            self._reconnect_old_target_port = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _on_selection_changed(self):
        if self._is_clearing:
            return
        sel = self.selectedItems()
        if not sel:
            return
        it = sel[0]
        if not self._is_alive_item(it):
            return
        while it and not isinstance(it, NodeItem):
            try:
                it = it.parentItem()
            except RuntimeError:
                return
        if it and self._is_alive_item(it):
            self.node_selected.emit(it.payload)

    def add_node_item(self, item: NodeItem, pos: QPointF):
        self.addItem(item)
        item.setPos(pos)

    def add_edge_between_ports(self, src: Optional[PortItem], dst: Optional[PortItem], is_branch: bool = False):
        if src is None or dst is None:
            return
        if not (self._is_alive_item(src) and self._is_alive_item(dst)):
            return
        edge = EdgeItem(src, dst, is_branch=is_branch)
        self.addItem(edge)
        edge.update_path()

    def clear_edges(self):
        for it in list(self.items()):
            if isinstance(it, EdgeItem):
                try:
                    it.destroy()
                except Exception:
                    pass

class GraphView(QGraphicsView):
    def __init__(self, scene: GraphScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(self.renderHints() | QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setFrameShape(QFrame.NoFrame)
        self._panning = False
        self._last_pos = None
        self._hint_forced = False
        log.debug("GraphView.__init__")

    def wheelEvent(self, e):
        factor = 1.10 if e.angleDelta().y() > 0 else 1 / 1.10
        self.scale(factor, factor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._panning = True
            self._last_pos = e.pos()
            self.setCursor(Qt.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._panning and self._last_pos is not None:
            delta = e.pos() - self._last_pos
            self._last_pos = e.pos()
            h = self.horizontalScrollBar()
            v = self.verticalScrollBar()
            h.setValue(h.value() - delta.x())
            v.setValue(v.value() - delta.y())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def toggle_hint(self):
        """Принудительно показать/скрыть подсказку по управлению."""
        self._hint_forced = not self._hint_forced
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect):
        """Показывает подсказку по управлению, когда граф пустой (≤1 ноды) или принудительно."""
        node_count = sum(1 for it in self.scene().items() if isinstance(it, NodeItem))
        if node_count > 1 and not self._hint_forced:
            return
        hint_lines = [
            "ПКМ на холсте  →  добавить ноду",
            "Тяни выход ○ →  соединить ноды",
            "Тяни вход ●  →  перецепить стрелку",
            "ПКМ на стрелке  →  отцепить",
            "Колёсико — зум,  средняя кнопка — перемещение",
            "Del — удалить выделенную ноду",
        ]
        painter.save()
        painter.resetTransform()
        vp = self.viewport().rect()
        f = QFont()
        f.setPointSize(9)
        painter.setFont(f)
        fm = painter.fontMetrics()
        line_h = fm.height() + 4
        block_h = len(hint_lines) * line_h + 16
        block_w = max(fm.horizontalAdvance(ln) for ln in hint_lines) + 24
        x = (vp.width() - block_w) // 2
        y = vp.height() - block_h - 30
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(20, 20, 20, 160))
        painter.drawRoundedRect(x, y, block_w, block_h, 6, 6)
        painter.setPen(QPen(QColor("#888888")))
        for i, line in enumerate(hint_lines):
            painter.drawText(x + 12, y + 8 + (i + 1) * line_h, line)
        painter.restore()

    def fit_all(self):
        """Подогнать вид под все ноды на холсте."""
        items = self.scene().items()
        if not items:
            return
        rect = self.scene().itemsBoundingRect()
        self.fitInView(rect.adjusted(-60, -60, 60, 60), Qt.KeepAspectRatio)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Delete:
            parent = self.parent()
            try:
                if hasattr(parent, "_delete_selected_nodes"):
                    parent._delete_selected_nodes()
                    e.accept()
                    return
            except Exception:
                pass
        if self._panning and self._last_pos is not None:
            super().keyPressEvent(e)
            return
        super().keyPressEvent(e)