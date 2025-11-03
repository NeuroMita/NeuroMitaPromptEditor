# ui/node_graph/graph_scene.py
from __future__ import annotations
from typing import Optional
import logging

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QFrame

from ui.node_graph.graph_primitives import EdgeItem, NodeItem, PortItem

log = logging.getLogger("node_graph.scene")
log.setLevel(logging.DEBUG)
log.propagate = True

class GraphScene(QGraphicsScene):
    node_selected = Signal(object)                 # ast_node
    connection_finished = Signal(object, object)   # (source_port:PortItem, target_port:PortItem)
    request_create_menu = Signal(object, object)   # (source_port_or_None, scene_pos:QPointF)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_edge: Optional[EdgeItem] = None
        self._drag_source: Optional[PortItem] = None
        self._is_clearing: bool = False
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

    # ------- interaction for connections -------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            port = self._port_under_pos(event.scenePos())
            if port and not port.is_input:
                self._drag_source = port
                self._drag_edge = EdgeItem(port, None, is_branch=("branch" in port.key or port.key == "else"))
                self.addItem(self._drag_edge)
                self._drag_edge.set_temp_end(event.scenePos())
                event.accept()
                return

        if event.button() == Qt.RightButton:
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
                self.connection_finished.emit(self._drag_source, target)
            else:
                self.request_create_menu.emit(self._drag_source, event.scenePos())

            try:
                if self._drag_edge:
                    self._drag_edge.destroy()
            except Exception:
                pass
            self._drag_edge = None
            self._drag_source = None
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