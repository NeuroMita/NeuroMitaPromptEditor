# File: ui/node_graph/controller.py
from __future__ import annotations
from typing import Dict, List, Optional, Set as PySet
import logging

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QMessageBox

from logic.dsl_ast import Script, AstNode, Set, Log, AddSystemInfo, Return, If
from ui.node_graph.graph_primitives import NodeItem, PortItem
from ui.node_graph.graph_scene import GraphScene

log = logging.getLogger("node_graph.controller")
log.setLevel(logging.DEBUG)
log.propagate = True


class NodeGraphController:
    """
    Управляет отображением AST на графе и синхронизацией.
    """
    def __init__(self, scene: GraphScene):
        self.scene = scene
        self.script: Script = Script()
        self.parent_map: Dict[str, List[AstNode]] = {}
        self.node2item: Dict[str, NodeItem] = {}
        self.item2node: Dict[NodeItem, AstNode] = {}
        self.node_positions: Dict[str, QPointF] = {}
        self.node_colors: Dict[str, QColor] = {}
        self._on_metadata_changed: Optional[callable] = None

    def set_metadata_changed_callback(self, cb: callable):
        self._on_metadata_changed = cb

    def set_ast(self, script: Script):
        self.script = script

    def load_metadata(self, positions: Dict[str, tuple], colors: Dict[str, str]):
        self.node_positions.clear()
        self.node_colors.clear()
        for nid, (x, y) in positions.items():
            self.node_positions[nid] = QPointF(x, y)
        for nid, color_str in colors.items():
            try:
                self.node_colors[nid] = QColor(color_str)
            except Exception:
                pass

    def export_metadata(self) -> tuple[Dict[str, tuple], Dict[str, str]]:
        positions = {}
        colors = {}
        for nid, item in self.node2item.items():
            try:
                pos = item.pos()
                positions[nid] = (pos.x(), pos.y())
                custom_color = item.get_custom_color()
                if custom_color:
                    colors[nid] = custom_color.name()
            except Exception:
                pass
        return positions, colors

    def rebuild(self, keep_positions: bool = True):
        for nid, item in list(self.node2item.items()):
            try:
                self.node_positions[nid] = item.pos()
                custom_color = item.get_custom_color()
                if custom_color:
                    self.node_colors[nid] = custom_color
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
                return (max(1, total_h), 1 + max(1, max_w))
            return (1, 1)

        pos_map: Dict[str, QPointF] = {}

        def place_block(body: List[AstNode], col: int, row: int):
            blk_h, _blk_w = measure_block(body)
            c = col
            for n in body:
                nh, nw = measure_node(n)
                row_center = row + max(0, (blk_h - nh) // 2)
                pos_map[n.id] = QPointF(c * H_STEP, row_center * V_STEP)
                self.parent_map[n.id] = body

                if isinstance(n, IfNode):
                    branch_row = row_center + 1
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

        def create_nodes(body: List[AstNode]):
            for n in body:
                item = self._node_item_for(n)
                self.node2item[n.id] = item
                self.item2node[item] = n
                p = self.node_positions.get(n.id) if keep_positions and (n.id in self.node_positions) else pos_map.get(n.id, QPointF(0, 0))
                self.scene.add_node_item(item, p)
                if n.id in self.node_colors:
                    item.set_custom_color(self.node_colors[n.id])
                item.set_move_callback(self._on_node_moved)
                item.set_color_changed_callback(self._on_node_color_changed)
                if isinstance(n, IfNode):
                    for br in n.branches:
                        create_nodes(br.body)
                    if n.else_body:
                        create_nodes(n.else_body)

        create_nodes(self.script.body)
        self.refresh_edges()

    def _on_node_moved(self, item: NodeItem):
        for nid, it in self.node2item.items():
            if it is item:
                self.node_positions[nid] = item.pos()
                if self._on_metadata_changed:
                    self._on_metadata_changed()
                break

    def _on_node_color_changed(self, item: NodeItem):
        for nid, it in self.node2item.items():
            if it is item:
                custom_color = item.get_custom_color()
                if custom_color:
                    self.node_colors[nid] = custom_color
                elif nid in self.node_colors:
                    del self.node_colors[nid]
                if self._on_metadata_changed:
                    self._on_metadata_changed()
                break

    def create_item_for_node(self, node: AstNode, pos: QPointF) -> NodeItem:
        if node.id in self.node2item:
            it = self.node2item[node.id]
            it.setPos(pos)
            self.node_positions[node.id] = QPointF(pos)
            return it
        item = self._node_item_for(node)
        self.node2item[node.id] = item
        self.item2node[item] = node
        self.scene.add_node_item(item, pos)
        self.node_positions[node.id] = QPointF(pos)
        item.set_move_callback(self._on_node_moved)
        item.set_color_changed_callback(self._on_node_color_changed)
        if node.id in self.node_colors:
            item.set_custom_color(self.node_colors[node.id])
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

    def _node_item_for(self, node: AstNode) -> NodeItem:
        from logic.dsl_ast import If
        if isinstance(node, Set):
            title = "Установить переменную"
            subtitle = f"{'LOCAL ' if node.local else ''}{node.var} = {node.expr}"
            desc = "Создаёт или изменяет переменную. LOCAL — видна только внутри текущего блока."
            item = NodeItem(title, subtitle, node); item.setRect(0, 0, 320, 80); item.set_description(desc)
        elif isinstance(node, Log):
            title = "Записать в лог"
            subtitle = node.expr[:40] + "..." if len(node.expr) > 40 else node.expr
            desc = "Выводит значение выражения в лог для отладки."
            item = NodeItem(title, subtitle, node); item.setRect(0, 0, 320, 80); item.set_description(desc)
        elif isinstance(node, AddSystemInfo):
            title = "Системная информация"
            subtitle = node.expr[:30] + "..." if len(node.expr) > 30 else node.expr
            desc = "Добавляет системные инструкции, обычно загружает файл в начало промпта."
            item = NodeItem(title, subtitle, node); item.setRect(0, 0, 340, 80); item.set_description(desc)
        elif isinstance(node, Return):
            title = "Вернуть результат"
            subtitle = node.expr[:35] + "..." if len(node.expr) > 35 else node.expr
            desc = "Возвращает итоговый текст промпта. Завершает выполнение скрипта."
            item = NodeItem(title, subtitle, node); item.setRect(0, 0, 340, 80); item.set_description(desc)
        elif isinstance(node, If):
            title = "Условие"; subtitle = ""
            desc = "Условная развилка: выполняет разные ветки кода в зависимости от условий."
            item = NodeItem(title, subtitle, node)
            branches_count = len(node.branches) + (1 if node.else_body is not None else 0)
            base_h = 64; per_row = 28
            h = base_h + max(1, branches_count) * per_row + 10; w = 360
            item.setRect(0, 0, w, h); item.set_description(desc)
        else:
            item = NodeItem(type(node).__name__, "", node); item.setRect(0, 0, 320, 80); item.set_description("")
        item.add_in_port("exec", "Выполнение")
        from logic.dsl_ast import If as IfNode
        if not isinstance(node, Return): item.add_out_port("exec", "Далее")
        if isinstance(node, IfNode):
            for i, br in enumerate(node.branches):
                item.add_out_port(f"branch_{i}", f"{br.cond}")
            if node.else_body is not None:
                item.add_out_port("else", "Иначе")
        return item

    # ---- защита от циклов ----
    def _is_ancestor(self, potential_ancestor: AstNode, node: AstNode) -> bool:
        visited: PySet[str] = set()
        def check_parent(n: AstNode) -> bool:
            if n.id in visited: return False
            visited.add(n.id)
            if n.id == potential_ancestor.id: return True
            parent_body = self.parent_map.get(n.id)
            if not parent_body: return False
            from logic.dsl_ast import If as IfNode
            for item, ast in list(self.item2node.items()):
                if isinstance(ast, IfNode):
                    for br in ast.branches:
                        if br.body is parent_body: return check_parent(ast)
                    if ast.else_body is parent_body: return check_parent(ast)
            try:
                idx = parent_body.index(n)
                if idx > 0:
                    return check_parent(parent_body[idx - 1])
            except Exception:
                pass
            return False
        return check_parent(node)

    def _detach_node(self, node: AstNode):
        # полностью убрать узел из любого тела
        for body in self._all_bodies():
            if node in body:
                body.remove(node)
                break
        if node.id in self.parent_map:
            del self.parent_map[node.id]

    def connect_ports(self, src: PortItem, dst: PortItem):
        """
        Правила:
        - Только одна связь из exec-порта. При переподключении мы НЕ трогаем ветки IF.
        - Если старый сосед после src — это IF, мы его не выбрасываем из AST (оставляем после нового dst).
          Это сохраняет все branch-связи IF и устраняет "обрушение" веток.
        - Для других типов узлов старый сосед отсоединяется полностью (по раннему требованию).
        """
        src_node = self.item2node.get(src.owner)
        dst_node = self.item2node.get(dst.owner)
        if not src_node or not dst_node:
            return

        if src_node is dst_node or self._is_ancestor(dst_node, src_node):
            QMessageBox.warning(None, "Недопустимое соединение",
                                "Рекурсивные или циклические связи запрещены.")
            return

        # Главный выход exec — только одна связь
        if src.key == "exec":
            # удаляем только рёбра exec-порта источника
            for e in list(src.edges):
                try:
                    e.destroy()
                except Exception:
                    pass

            src_parent = self.parent_map.get(src_node.id, self.script.body)
            try:
                sidx = src_parent.index(src_node)
            except ValueError:
                sidx = -1

            old_next = None
            if sidx >= 0 and sidx + 1 < len(src_parent):
                old_next = src_parent[sidx + 1]

            # вставляем новый dst сразу после src
            self._remove_from_parent(dst_node)
            if sidx >= 0:
                src_parent.insert(sidx + 1, dst_node)
                self.parent_map[dst_node.id] = src_parent

            # если старый сосед существовал и это НЕ IF — отсоединяем его полностью;
            # если это IF — оставляем его на месте (он сам сместится на позицию sidx+2),
            # все его ветви остаются нетронутыми.
            if old_next and old_next is not dst_node:
                if not isinstance(old_next, If):
                    self._detach_node(old_next)
            return

        # Ветви IF: по одному ребру на каждую ветку; удаляем только рёбра этой ветки
        if isinstance(src_node, If) and (src.key.startswith("branch_") or src.key == "else"):
            for e in list(src.edges):
                try:
                    e.destroy()
                except Exception:
                    pass

            if src.key == "else":
                if src_node.else_body is None:
                    src_node.else_body = []
                body = src_node.else_body
            else:
                idx = int(src.key.split("_")[1])
                body = src_node.branches[idx].body

            # старый первый узел этой конкретной ветки — отсоединяем
            if body:
                self._detach_node(body[0])

            self._remove_from_parent(dst_node)
            body.insert(0, dst_node)
            self.parent_map[dst_node.id] = body
            return

        # обычная последовательность
        src_parent = self.parent_map.get(src_node.id, self.script.body)
        self._remove_from_parent(dst_node)
        try:
            sidx = src_parent.index(src_node)
        except ValueError:
            sidx = len(src_parent) - 1
        src_parent.insert(sidx + 1, dst_node)
        self.parent_map[dst_node.id] = src_parent

    def _remove_from_parent(self, node: AstNode):
        for body in self._all_bodies():
            if node in body:
                body.remove(node)
                return

    def _all_bodies(self) -> List[List[AstNode]]:
        res: List[List[AstNode]] = [self.script.body]
        def walk(body: List[AstNode]):
            for n in body:
                if isinstance(n, If):
                    for br in n.branches:
                        res.append(br.body); walk(br.body)
                    if n.else_body is not None:
                        res.append(n.else_body); walk(n.else_body)
        walk(self.script.body)
        return res