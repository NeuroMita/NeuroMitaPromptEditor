# ui/node_graph/controller.py
from __future__ import annotations
from typing import Dict, List, Optional
import logging

from PySide6.QtCore import QPointF

from logic.dsl_ast import Script, AstNode, Set, Log, AddSystemInfo, Return, If
from ui.node_graph.graph_primitives import NodeItem, PortItem
from ui.node_graph.graph_scene import GraphScene

log = logging.getLogger("node_graph.controller")
log.setLevel(logging.DEBUG)
log.propagate = True


class NodeGraphController:
    """
    Управляет отображением AST на графе и синхронизацией.
    rebuild() — автолэйаут только при генерации из текста.
    При ручных изменениях: create_item_for_node() + refresh_edges().
    """
    def __init__(self, scene: GraphScene):
        self.scene = scene
        self.script: Script = Script()
        self.parent_map: Dict[str, List[AstNode]] = {}      # node.id -> parent body list
        self.node2item: Dict[str, NodeItem] = {}
        self.item2node: Dict[NodeItem, AstNode] = {}
        self.node_positions: Dict[str, QPointF] = {}
        log.debug("Controller.__init__")

    # ---------- build ----------
    def set_ast(self, script: Script):
        self.script = script
        log.debug("Controller.set_ast: nodes=%d", len(self.script.body))


    def rebuild(self, keep_positions: bool = True):
        """
        Smart autolayout v3:
        - Последовательность: узлы идут слева-направо по одной "магистральной" строке.
        - IF: сам IF остаётся на магистральной строке; ветви раскладываются СПУСКОМ ниже (branch-start-row = center+offset),
        чтобы линии магистрали не перекрывались нодами ветвей.
        - Высота/ширина в ячейках учитывают вложенность ветвей, чтобы следующий узел последовательности не попадал "внутрь" веток.
        """
        # сохранить текущие позиции
        for nid, item in list(self.node2item.items()):
            try:
                self.node_positions[nid] = item.pos()
            except Exception:
                pass

        self.scene.clear()
        self.parent_map.clear()
        self.node2item.clear()
        self.item2node.clear()

        NODE_W = 360
        NODE_H = 96
        COL_GAP = 140
        ROW_GAP = 40
        H_STEP = NODE_W + COL_GAP
        V_STEP = NODE_H + ROW_GAP

        from logic.dsl_ast import If as IfNode

        def measure_block(body: List[AstNode]) -> tuple[int, int]:
            if not body:
                return (1, 1)
            max_h = 1
            total_w = 0
            for n in body:
                nh, nw = measure_node(n)
                max_h = max(max_h, nh)
                total_w += max(1, nw)
            return (max_h, max(1, total_w))

        def measure_node(n: AstNode) -> tuple[int, int]:
            if isinstance(n, IfNode):
                # суммарная высота ветвей (в строках)
                total_h = 0
                max_w = 1
                for br in n.branches:
                    bh, bw = measure_block(br.body)
                    total_h += max(1, bh)
                    max_w = max(max_w, bw)
                if n.else_body is not None:
                    eh, ew = measure_block(n.else_body)
                    total_h += max(1, eh)
                    max_w = max(max_w, ew)
                # ширина узла IF + ширина самой широкой ветки
                return (max(1, total_h), 1 + max(1, max_w))
            return (1, 1)

        pos_map: Dict[str, QPointF] = {}

        def place_block(body: List[AstNode], col: int, row: int):
            # магистральная высота блока
            blk_h, _blk_w = measure_block(body)
            c = col
            for n in body:
                nh, nw = measure_node(n)
                # центр узла по магистрали
                row_center = row + max(0, (blk_h - nh) // 2)
                pos_map[n.id] = QPointF(c * H_STEP, row_center * V_STEP)
                self.parent_map[n.id] = body

                if isinstance(n, IfNode):
                    # разместить ветви СПУСКОМ ниже центра IF
                    branch_row = row_center + 1  # смещаем ветки относительно exec-магистрали
                    for br in n.branches:
                        bh, _bw = measure_block(br.body)
                        place_block(br.body, c + 1, branch_row)
                        branch_row += max(1, bh)
                    if n.else_body is not None:
                        eh, _ew = measure_block(n.else_body)
                        place_block(n.else_body, c + 1, branch_row)
                        branch_row += max(1, eh)

                c += max(1, nw)

        place_block(self.script.body, col=0, row=0)

        # создание нод
        def create_nodes(body: List[AstNode]):
            for n in body:
                item = self._node_item_for(n)
                self.node2item[n.id] = item
                self.item2node[item] = n
                # позиция
                p = self.node_positions.get(n.id) if keep_positions and (n.id in self.node_positions) else pos_map.get(n.id, QPointF(0, 0))
                self.scene.add_node_item(item, p)
                if isinstance(n, IfNode):
                    for br in n.branches:
                        create_nodes(br.body)
                    if n.else_body:
                        create_nodes(n.else_body)

        create_nodes(self.script.body)
        self.refresh_edges()
        
    def create_item_for_node(self, node: AstNode, pos: QPointF) -> NodeItem:
        if node.id in self.node2item:
            it = self.node2item[node.id]
            it.setPos(pos)
            self.node_positions[node.id] = QPointF(pos)
            log.debug("Controller.create_item_for_node: reuse node=%s pos=%s", node.id, pos)
            return it
        item = self._node_item_for(node)
        self.node2item[node.id] = item
        self.item2node[item] = node
        self.scene.add_node_item(item, pos)
        self.node_positions[node.id] = QPointF(pos)
        log.debug("Controller.create_item_for_node: new node=%s pos=%s", node.id, pos)
        return item

    def refresh_edges(self):
        self.scene.clear_edges()

        def body_edges(body: List[AstNode]):
            for i in range(len(body) - 1):
                a = body[i]
                if isinstance(a, Return):
                    break
                b = body[i + 1]
                ia, ib = self.node2item.get(a.id), self.node2item.get(b.id)
                if ia and ib:
                    self.scene.add_edge_between_ports(ia.out_port("exec"), ib.in_port("exec"))
            for n in body:
                if isinstance(n, If):
                    iif = self.node2item.get(n.id)
                    if iif:
                        for idx, br in enumerate(n.branches):
                            if len(br.body) > 0:
                                first = br.body[0]
                                it_first = self.node2item.get(first.id)
                                if it_first:
                                    self.scene.add_edge_between_ports(iif.out_port(f"branch_{idx}"), it_first.in_port("exec"))
                        if n.else_body and len(n.else_body) > 0:
                            first = n.else_body[0]
                            it_first = self.node2item.get(first.id)
                            if it_first:
                                self.scene.add_edge_between_ports(iif.out_port("else"), it_first.in_port("exec"), is_branch=True)
                    for br in n.branches:
                        body_edges(br.body)
                    if n.else_body:
                        body_edges(n.else_body)

        body_edges(self.script.body)
        log.debug("Controller.refresh_edges: edges refreshed")

    # ---------- internal ----------
    def _node_item_for(self, node: AstNode) -> NodeItem:
        from logic.dsl_ast import If
        if isinstance(node, Set):
            item = NodeItem("SET", f"{'LOCAL ' if node.local else ''}{node.var} = {node.expr}", node)
            item.setRect(0, 0, 320, 96)
        elif isinstance(node, Log):
            item = NodeItem("LOG", node.expr, node)
            item.setRect(0, 0, 320, 96)
        elif isinstance(node, AddSystemInfo):
            item = NodeItem("ADD_SYSTEM_INFO", node.expr, node)
            item.setRect(0, 0, 340, 96)
        elif isinstance(node, Return):
            item = NodeItem("RETURN", node.expr, node)
            item.setRect(0, 0, 340, 96)
        elif isinstance(node, If):
            item = NodeItem("IF", "", node)
            # Высота IF динамична: шапка + строки условий
            branches_count = len(node.branches) + (1 if node.else_body is not None else 0)
            base_h = 64   # шапка + место для exec-out
            per_row = 26  # строка под одну ветку
            h = base_h + max(1, branches_count) * per_row + 12
            w = 360
            item.setRect(0, 0, w, h)
        else:
            item = NodeItem(type(node).__name__, "", node)
            item.setRect(0, 0, 320, 96)

        # вход exec — всегда
        item.add_in_port("exec", "exec in")

        # RETURN — терминальный, без exec out
        from logic.dsl_ast import If as IfNode
        if not isinstance(node, Return):
            item.add_out_port("exec", "exec out")

        # IF — подписываем ветви условиями, else — отдельным портом
        if isinstance(node, IfNode):
            for i, br in enumerate(node.branches):
                label = f"IF {br.cond}" if i == 0 else f"ELSEIF {br.cond}"
                item.add_out_port(f"branch_{i}", label)
            if node.else_body is not None:
                item.add_out_port("else", "ELSE")

        return item

    # ---------- editing ----------
    def insert_after(self, target: Optional[AstNode], new_node: AstNode):
        if target is None:
            self.script.body.append(new_node)
            self.parent_map[new_node.id] = self.script.body
            log.debug("Controller.insert_after: root append node=%s", new_node.id)
        else:
            parent = self.parent_map.get(target.id, self.script.body)
            try:
                idx = parent.index(target)
            except ValueError:
                idx = len(parent) - 1
            parent.insert(idx + 1, new_node)
            self.parent_map[new_node.id] = parent
            log.debug("Controller.insert_after: after=%s inserted=%s", target.id, new_node.id)

    def delete_node(self, node: AstNode):
        parent = self.parent_map.get(node.id)
        if parent and node in parent:
            parent.remove(node)
            log.debug("Controller.delete_node: node=%s removed", node.id)

    def connect_ports(self, src: PortItem, dst: PortItem):
        src_node = self.item2node.get(src.owner)
        dst_node = self.item2node.get(dst.owner)
        if not src_node or not dst_node:
            log.debug("Controller.connect_ports: src/dst node missing")
            return

        if isinstance(src_node, If) and (src.key.startswith("branch_") or src.key == "else"):
            if src.key == "else":
                if src_node.else_body is None:
                    src_node.else_body = []
                body = src_node.else_body
            else:
                idx = int(src.key.split("_")[1])
                body = src_node.branches[idx].body
            self._move_node_to_body_start(dst_node, body)
            self.parent_map[dst_node.id] = body
            log.debug("Controller.connect_ports: IF-branch %s -> dst=%s", src.key, dst_node.id)
            return

        src_parent = self.parent_map.get(src_node.id, self.script.body)
        self._remove_from_parent(dst_node)
        try:
            sidx = src_parent.index(src_node)
        except ValueError:
            sidx = len(src_parent) - 1
        src_parent.insert(sidx + 1, dst_node)
        self.parent_map[dst_node.id] = src_parent
        log.debug("Controller.connect_ports: seq %s -> %s", getattr(src_node, "id", None), getattr(dst_node, "id", None))

    def _remove_from_parent(self, node: AstNode):
        for body in self._all_bodies():
            if node in body:
                body.remove(node)
                log.debug("Controller._remove_from_parent: node=%s removed from body", node.id)
                return

    def _all_bodies(self) -> List[List[AstNode]]:
        res: List[List[AstNode]] = [self.script.body]

        def walk(body: List[AstNode]):
            for n in body:
                if isinstance(n, If):
                    for br in n.branches:
                        res.append(br.body)
                        walk(br.body)
                    if n.else_body is not None:
                        res.append(n.else_body)
                        walk(n.else_body)
        walk(self.script.body)
        return res

    def _move_node_to_body_start(self, node: AstNode, body: List[AstNode]):
        self._remove_from_parent(node)
        body.insert(0, node)
        log.debug("Controller._move_node_to_body_start: node=%s -> beginning of body", node.id)