# File: ui/node_graph/editor_widget.py
from __future__ import annotations
from typing import Optional, List
import os
import re
import logging
import traceback

from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSplitter,
    QLabel, QPlainTextEdit, QMenu, QMessageBox, QFileDialog
)
from PySide6.QtGui import QShortcut, QKeySequence

from logic.dsl_ast import Script, Set, Log, AddSystemInfo, Return, If, IfBranch, AstNode
from logic.dsl_parser import parse_script, ParseError
from logic.dsl_codegen import generate_script
from ui.node_graph.graph_scene import GraphScene, GraphView
from ui.node_graph.graph_primitives import NodeItem, PortItem
from ui.node_graph.inspector_widget import Inspector
from ui.node_graph.controller import NodeGraphController
from ui.node_graph.preview_highlighter import SimplePromptHighlighter

log = logging.getLogger("node_graph.editor")
log.setLevel(logging.DEBUG)
log.propagate = True


class NodeGraphEditor(QWidget):
    text_updated = Signal(str)

    _INLINE_LOAD_RE = re.compile(
        r"""\bLOAD
             (?:\s+([A-Z0-9_]+))?
             \s+FROM\s+
             (['"])(.+?)\2
        """,
        re.IGNORECASE | re.VERBOSE,
    )
    _LOAD_REL_RE = re.compile(r"""\bLOAD(?:_REL|REL)\s+(['"])(.+?)\1""", re.IGNORECASE)
    _SECTION_MARKER_RE = re.compile(r"^[ \t]*\[(?:#|/)\s*[A-Z0-9_]+\s*\][ \t]*\r?\n?", re.IGNORECASE | re.MULTILINE)
    _TAG_SECTION_RE_TMPL = r"\[#\s*{tag}\s*\](.*?)\s*\[/\s*{tag}\s*\]"

    def __init__(self, base_dir: Optional[str] = None, prompts_root: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._base_dir = base_dir
        self._prompts_root = prompts_root
        self._ast: Script = Script()
        self._errors: List[ParseError] = []
        self._start_item: Optional[NodeItem] = None
        self._start_pos: QPointF = QPointF(-320, 0)

        # --------- UI ----------
        self.scene = GraphScene(self)
        self.view = GraphView(self.scene, self)

        self.inspector = Inspector(self)
        self.inspector.set_preview_provider(self._preview_for_expr)
        self.inspector.set_file_picker(self._pick_file_for_attach)
        self.inspector.ast_changed.connect(self._on_ast_changed)

        self.controller = NodeGraphController(self.scene)

        self.scene.node_selected.connect(self._on_node_selected)
        self.scene.connection_finished.connect(self._on_connection_finished)
        self.scene.request_create_menu.connect(self._on_request_create_menu)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(False)
        self.preview.setStyleSheet("background:#1f2329;color:#e6edf3;")
        self.preview.setPlaceholderText("Сгенерированный .script / редактируемый текст")
        SimplePromptHighlighter(self.preview.document())

        self.btn_from_text = QPushButton("Пересобрать граф из текста")
        self.btn_to_text = QPushButton("Обновить текст из графа")
        self.btn_toggle_preview = QPushButton("Скрыть превью")
        self.btn_from_text.clicked.connect(self._rebuild_from_preview_text)
        self.btn_to_text.clicked.connect(self._apply_ast_to_preview)
        self.btn_toggle_preview.clicked.connect(self._toggle_preview)

        top_row = QHBoxLayout()
        top_row.addWidget(self.btn_from_text)
        top_row.addWidget(self.btn_to_text)
        top_row.addStretch(1)
        top_row.addWidget(self.btn_toggle_preview)

        top_split = QSplitter(Qt.Horizontal)
        top_split.addWidget(self.view)
        top_split.addWidget(self.inspector)
        top_split.setStretchFactor(0, 5)
        top_split.setStretchFactor(1, 1)
        top_split.setSizes([1400, 380])

        main_split = QSplitter(Qt.Vertical)
        main_split.addWidget(top_split)
        main_split.addWidget(self.preview)
        main_split.setStretchFactor(0, 5)
        main_split.setStretchFactor(1, 1)
        main_split.setSizes([900, 220])

        lay = QVBoxLayout(self)
        lay.addLayout(top_row)
        lay.addWidget(main_split)

        # Delete shortcut (works for any child focus inside editor)
        self._del_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self)
        self._del_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._del_shortcut.activated.connect(self._delete_selected_nodes)

        # стартовая нода
        self._ensure_start_node()
        self._refresh_preview()

    def _fit_scene_rect(self, pad: float = 200.0):
        """
        Расширяет sceneRect под фактические границы всех элементов (ноды, рёбра),
        чтобы скроллом можно было долистать до любой конечной ноды.
        """
        try:
            items = list(self.scene.items())
            if not items:
                # запас по умолчанию
                from PySide6.QtCore import QRectF
                self.scene.setSceneRect(QRectF(-1000, -1000, 2000, 2000))
                return

            rect = None
            for it in items:
                try:
                    r = it.sceneBoundingRect()
                except Exception:
                    continue
                rect = r if rect is None else rect.united(r)

            if rect is None:
                from PySide6.QtCore import QRectF
                rect = QRectF(-1000, -1000, 2000, 2000)

            rect = rect.adjusted(-pad, -pad, pad, pad)

            # не даём совсем маленьких размеров (чтобы не "схлопывалась" сцена)
            min_w, min_h = 2000.0, 1200.0
            if rect.width() < min_w:
                rect.setWidth(min_w)
            if rect.height() < min_h:
                rect.setHeight(min_h)

            self.scene.setSceneRect(rect)
        except Exception:
            # если что-то пошло не так — не падаем
            pass

    # ---------- helpers ----------
    @staticmethod
    def _is_item_alive(item) -> bool:
        try:
            return (item is not None) and (item.scene() is not None)
        except RuntimeError:
            return False

    # ---------- public ----------
    def load_text(self, text: str):
        self.preview.setPlainText(text)
        self._rebuild_from_preview_text()

    def export_text(self) -> str:
        return self.preview.toPlainText()

    # ---------- parse/build ----------
    def _rebuild_from_preview_text(self):
        try:
            txt = self.preview.toPlainText()
            ast, errs = parse_script(txt)
            self._ast = ast
            self._errors = errs
            if errs:
                msg = "\n".join(str(e) for e in errs)
                QMessageBox.warning(self, "Парсер DSL", msg)
            self.controller.set_ast(self._ast)
            # умная авторасстановка при парсинге из текста
            self.controller.rebuild(keep_positions=False)
            self._ensure_start_node()
            self._draw_start_edge()
        except Exception as e:
            QMessageBox.critical(self, "NodeGraphEditor", f"Ошибка rebuild:\n{e}\n{traceback.format_exc()}")
        self._fit_scene_rect()

    # ---------- inspector / preview ----------
    def _on_node_selected(self, ast_node: AstNode):
        self.inspector.set_ast(ast_node)

    def _on_ast_changed(self):
        try:
            self.controller.rebuild(keep_positions=False)
            self._ensure_start_node()
            self._draw_start_edge()
            self._fit_scene_rect()
            self._refresh_preview()
        except Exception as e:
            QMessageBox.critical(self, "NodeGraphEditor", f"Ошибка обновления AST:\n{e}\n{traceback.format_exc()}")

    def _refresh_preview(self):
        self.preview.blockSignals(True)
        self.preview.setPlainText(generate_script(self._ast))
        self.preview.blockSignals(False)

    def _apply_ast_to_preview(self):
        self._refresh_preview()
        self.text_updated.emit(self.preview.toPlainText())

    def _toggle_preview(self):
        visible = self.preview.isVisible()
        self.preview.setVisible(not visible)
        self.btn_toggle_preview.setText("Показать превью" if visible else "Скрыть превью")

    # ---------- START node ----------
    def _ensure_start_node(self):
        # НЕ ЗВОНИТЬ .scene() БЕЗ ПРОВЕРКИ
        if self._start_item and self._is_item_alive(self._start_item):
            # уже добавлена — ничего не делаем
            return
        # Старая ссылка могла указывать на удалённый C++ объект — обнулим
        self._start_item = None
        # создаём новую
        start = NodeItem("START", "Entry point", payload="_START_")
        start.add_out_port("exec", "exec out")
        self.scene.add_node_item(start, self._start_pos)
        start.set_move_callback(lambda it: self._remember_start_pos_safe())
        self._start_item = start

    def _remember_start_pos_safe(self):
        if self._start_item and self._is_item_alive(self._start_item):
            self._start_pos = self._start_item.pos()

    def _draw_start_edge(self):
        # перерисуем рёбра и добавим ребро START -> первый узел (если он есть)
        self.controller.refresh_edges()
        if not (self._start_item and self._is_item_alive(self._start_item)):
            self._ensure_start_node()
        if self._ast.body:
            first = self._ast.body[0]
            it_first = self.controller.node2item.get(first.id)
            if it_first and self._start_item and self._is_item_alive(self._start_item):
                self.scene.add_edge_between_ports(self._start_item.out_port("exec"), it_first.in_port("exec"))

    # ---------- connections ----------
    def _on_connection_finished(self, src: PortItem, dst: PortItem):
        try:
            # соединение из START — переместить dst в начало сценария
            if self._start_item and self._is_item_alive(self._start_item) and src.owner is self._start_item:
                dst_node = self.controller.item2node.get(dst.owner)
                if dst_node:
                    self.controller._remove_from_parent(dst_node)
                    self._ast.body.insert(0, dst_node)
                    self.controller.parent_map[dst_node.id] = self._ast.body
                    self._draw_start_edge()
                    self._refresh_preview()
                return

            self.controller.connect_ports(src, dst)
            self._draw_start_edge()
            self._fit_scene_rect()
            self._refresh_preview()
        except Exception as e:
            QMessageBox.critical(self, "NodeGraphEditor", f"Ошибка соединения:\n{e}\n{traceback.format_exc()}")

        

    # ---------- creation menu ----------
    def _on_request_create_menu(self, source_port: Optional[PortItem], scene_pos):
        # Защита: если порт/владелец уже удалён — не использовать как источник
        try:
            if not (source_port and source_port.owner and source_port.owner.scene() is self.scene):
                source_port = None
        except RuntimeError:
            source_port = None

        menu = QMenu(self)
        a_set = menu.addAction("SET")
        a_log = menu.addAction("LOG")
        a_asi = menu.addAction("ADD_SYSTEM_INFO")
        a_ret = menu.addAction("RETURN")
        a_if = menu.addAction("IF")

        act = menu.exec(self.view.mapToGlobal(self.view.mapFromScene(scene_pos)))
        if not act:
            return

        if act == a_set:
            node = Set(var="var", expr="0", local=False)
        elif act == a_log:
            node = Log(expr='"debug"')
        elif act == a_asi:
            node = AddSystemInfo(expr='LOAD "Main/part.txt"')
        elif act == a_ret:
            node = Return(expr='"text"')
        else:
            node = If(branches=[IfBranch(cond="True")])

        # добавляем в AST, создаём ноду ровно в месте клика
        self.controller.insert_after(None, node)
        self.controller.create_item_for_node(node, scene_pos)

        # если нода создаётся из перетягиваемой связи — подключим к источнику
        if source_port:
            try:
                src_item_alive = source_port.owner if (source_port.owner and source_port.owner.scene() is self.scene) else None
            except RuntimeError:
                src_item_alive = None

            if src_item_alive:
                src_ast = self.controller.item2node.get(src_item_alive)
                if src_ast:
                    src_item = self.controller.node2item.get(src_ast.id)
                    dst_item = self.controller.node2item.get(node.id)
                    if src_item and dst_item:
                        src_port_new = src_item.out_port(source_port.key)
                        dst_port_new = dst_item.in_port("exec")
                        if src_port_new and dst_port_new:
                            self.controller.connect_ports(src_port_new, dst_port_new)

        # обновим только рёбра и рисуем START-ребро
        self._draw_start_edge()
        self._fit_scene_rect()
        self._refresh_preview()

    # ---------- file picker for attachments ----------
    def _pick_file_for_attach(self) -> Optional[str]:
        start_dir = self._base_dir or self._prompts_root or os.getcwd()
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать файл", start_dir,
                                              "Текстовые файлы (*.txt *.script *.system);;Все файлы (*)")
        if not path:
            return None
        try:
            abspath = os.path.abspath(path)
            if self._base_dir and os.path.commonpath([abspath, os.path.abspath(self._base_dir)]) == os.path.abspath(self._base_dir):
                rel = os.path.relpath(abspath, self._base_dir)
                return rel.replace("\\", "/")
            if self._prompts_root and os.path.commonpath([abspath, os.path.abspath(self._prompts_root)]) == os.path.abspath(self._prompts_root):
                rel = os.path.relpath(abspath, self._prompts_root)
                return rel.replace("\\", "/")
        except Exception:
            pass
        return path

    # ---------- file preview helpers ----------
    def _resolve_path(self, rel_path: str) -> Optional[str]:
        if not rel_path:
            return None
        if os.path.isabs(rel_path) and os.path.exists(rel_path):
            return rel_path
        if self._base_dir:
            p = os.path.normpath(os.path.join(self._base_dir, rel_path))
            if os.path.exists(p):
                return p
        if self._prompts_root:
            p = os.path.normpath(os.path.join(self._prompts_root, rel_path))
            if os.path.exists(p):
                return p
        return None

    def _read_file(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"[Ошибка чтения файла: {e}]"

    def _extract_tag_section(self, raw: str, tag_name: str) -> str:
        tag_up = tag_name.upper()
        pattern = re.compile(self._TAG_SECTION_RE_TMPL.format(tag=re.escape(tag_up)), re.IGNORECASE | re.DOTALL)
        m = pattern.search(raw)
        if not m:
            return f"[Тег [#{tag_name}] не найден]"
        content = m.group(1)
        if content.startswith("\n"):
            content = content[1:]
        return content

    def _remove_tag_markers(self, text: str) -> str:
        return self._SECTION_MARKER_RE.sub("", text)
    
    def _delete_selected_nodes(self):
        """
        Удаление выделенных нод (кроме START) по Delete.
        """
        selected = [it for it in self.scene.selectedItems() if hasattr(it, "payload")]
        removed_any = False
        for it in selected:
            ast = getattr(it, "payload", None)
            # START имеет payload "_START_" (строка) — не удаляем
            if isinstance(ast, AstNode):
                self.controller.delete_node(ast)
                removed_any = True

        if removed_any:
            # мягкая перестройка (сохраняем позиции, не дёргаем, т.к. удаление — локальная операция)
            self.controller.rebuild(keep_positions=True)
            self._ensure_start_node()
            self._draw_start_edge()
            self._fit_scene_rect()
            self._refresh_preview()
        

    def _preview_for_expr(self, expr: str) -> str:
        if not expr:
            return ""
        chunks: List[str] = []

        for m in self._INLINE_LOAD_RE.finditer(expr):
            tag = m.group(1)
            rel = m.group(3)
            path = self._resolve_path(rel) or rel
            if not os.path.isabs(path) or not os.path.exists(path):
                chunks.append(f"LOAD {tag+' ' if tag else ''}FROM \"{rel}\"\n⇒ [файл не найден]")
                continue
            raw = self._read_file(path)
            if tag:
                content = self._extract_tag_section(raw, tag)
            else:
                content = self._remove_tag_markers(raw)
            chunks.append(f"LOAD {tag+' ' if tag else ''}FROM \"{rel}\"\n⇒\n{content}")

        for m in self._LOAD_REL_RE.finditer(expr):
            rel = m.group(2)
            path = self._resolve_path(rel) or rel
            if not os.path.isabs(path) or not os.path.exists(path):
                chunks.append(f"LOAD_REL \"{rel}\"\n⇒ [файл не найден]")
                continue
            raw = self._read_file(path)
            content = self._remove_tag_markers(raw)
            chunks.append(f"LOAD_REL \"{rel}\"\n⇒\n{content}")

        return "\n\n---\n\n".join(chunks) if chunks else ""