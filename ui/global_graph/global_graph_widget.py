"""
ui/global_graph/global_graph_widget.py

Главный холст глобального графа промптов.

Показывает main_template.txt персонажа как flow-граф:
  - Каждый включаемый файл = нода
  - Стрелки между нодами = порядок включения
  - Кнопки на нодах открывают редакторы

Сигналы:
    open_text_requested(path)    — открыть файл в текстовом редакторе
    open_nodes_requested(path)   — открыть .script в NodeGraphEditor
    open_postscript_requested(path) — открыть .postscript в Rule Builder
    open_code_requested(path)    — открыть файл как сырой код
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import (
    QPainter, QPen, QColor, QPainterPath, QWheelEvent, QBrush,
)
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsLineItem, QGraphicsPathItem,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QSizePolicy, QMenu, QApplication,
)

from ui.global_graph.template_node import TemplateNode, NODE_W, NODE_H, _NodePortItem
from ui.global_graph.template_to_graph import build_graph_from_template


# ---------- параметры лейаута ----------
_COL_STEP  = NODE_W + 60   # горизонтальный шаг между нодами
_ROW_STEP  = NODE_H + 40   # вертикальный шаг (для wrap)
_COLS      = 4              # нод в строке до переноса
_MARGIN_X  = 40
_MARGIN_Y  = 40


class _GraphArrow(QGraphicsPathItem):
    """Стрелка-соединение между нодами."""

    _PEN_NORMAL   = QPen(QColor("#5a8fbe"), 2.0, Qt.SolidLine)
    _PEN_HOVER    = QPen(QColor("#79b8ff"), 2.5, Qt.SolidLine)
    _PEN_SELECTED = QPen(QColor("#f8c012"), 2.5, Qt.SolidLine)

    def __init__(self, src: TemplateNode, dst: TemplateNode):
        super().__init__()
        self._src = src
        self._dst = dst
        self.setPen(self._PEN_NORMAL)
        self.setZValue(-1)
        self.setFlag(QGraphicsPathItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._update()

    @property
    def source_node(self) -> TemplateNode:
        return self._src

    @property
    def target_node(self) -> TemplateNode:
        return self._dst

    def hoverEnterEvent(self, event):
        if not self.isSelected():
            self.setPen(self._PEN_HOVER)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.isSelected():
            self.setPen(self._PEN_NORMAL)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsPathItem.ItemSelectedHasChanged:
            self.setPen(self._PEN_SELECTED if value else self._PEN_NORMAL)
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        menu = QMenu()
        act_del = menu.addAction("🗑 Удалить связь")
        result = menu.exec(event.screenPos().toPoint())
        if result is act_del:
            sc = self.scene()
            if sc and hasattr(sc, "_on_arrow_delete_requested"):
                sc._on_arrow_delete_requested(self)
        event.accept()

    def _update(self):
        # Используем позиции портов нод
        start = self._src.out_port.center_scene()
        end   = self._dst.in_port.center_scene()

        same_row = abs(start.y() - end.y()) < NODE_H
        if same_row:
            cx = (start.x() + end.x()) / 2
            path = QPainterPath(start)
            path.cubicTo(QPointF(cx, start.y()), QPointF(cx, end.y()), end)
        else:
            cy = (start.y() + end.y()) / 2
            path = QPainterPath(start)
            path.cubicTo(QPointF(start.x(), cy), QPointF(end.x(), cy), end)
        self.setPath(path)


class _GlobalGraphScene(QGraphicsScene):
    """Сцена глобального графа с поддержкой перетаскивания портов."""

    # src_node, dst_node — оба TemplateNode
    connection_requested = Signal(object, object)
    # Запрос создания ноды на пустом месте холста
    create_node_requested = Signal(object)  # scene_pos: QPointF

    def __init__(self):
        super().__init__()
        self.setSceneRect(-5000, -5000, 10000, 10000)
        self.setBackgroundBrush(QColor("#0d1117"))
        self._drag_src: TemplateNode | None = None
        self._temp_edge: QGraphicsLineItem | None = None

    def _port_at(self, scene_pos: QPointF) -> "_NodePortItem | None":
        """Возвращает порт под курсором (если есть)."""
        view = self.views()[0] if self.views() else None
        if not view:
            return None
        it = self.itemAt(scene_pos, view.transform())
        if isinstance(it, _NodePortItem):
            return it
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            port = self._port_at(event.scenePos())
            if port and not port.is_input:
                # Начинаем drag с output порта
                self._drag_src = port.owner
                p = port.center_scene()
                self._temp_edge = QGraphicsLineItem(p.x(), p.y(), p.x(), p.y())
                self._temp_edge.setPen(QPen(QColor("#f8c012"), 2, Qt.DashLine))
                self._temp_edge.setZValue(100)
                self.addItem(self._temp_edge)
                event.accept()
                return
        if event.button() == Qt.RightButton:
            view = self.views()[0] if self.views() else None
            it = self.itemAt(event.scenePos(), view.transform()) if view else None
            # Пустой холст (нет элементов под курсором) → создать ноду
            if it is None:
                self.create_node_requested.emit(event.scenePos())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._temp_edge and self._drag_src:
            line = self._temp_edge.line()
            p = event.scenePos()
            self._temp_edge.setLine(line.x1(), line.y1(), p.x(), p.y())
            # Подсветить input порт под курсором
            port = self._port_at(p)
            if port and port.is_input and port.owner is not self._drag_src:
                port._set_highlighted()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._temp_edge and self._drag_src:
            port = self._port_at(event.scenePos())
            if port and port.is_input and port.owner is not self._drag_src:
                self.connection_requested.emit(self._drag_src, port.owner)
            # Убрать временную линию
            self.removeItem(self._temp_edge)
            self._temp_edge = None
            self._drag_src = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _on_arrow_delete_requested(self, arrow: _GraphArrow):
        """Вызывается из _GraphArrow.contextMenuEvent."""
        # Пробрасываем в GlobalGraphWidget через сигнал (используем connection_requested с None dst)
        self.connection_requested.emit(arrow.source_node, None)


class _GraphView(QGraphicsView):
    """QGraphicsView с поддержкой зума колёсиком и пан-перетаскиванием."""

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QGraphicsView { background: #0d1117; border: none; }")
        self._zoom = 1.0

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        new_zoom = self._zoom * factor
        if 0.2 <= new_zoom <= 4.0:
            self.scale(factor, factor)
            self._zoom = new_zoom

    def fit_all(self):
        """Подгоняет вид под все ноды."""
        items_rect = self.scene().itemsBoundingRect()
        if not items_rect.isEmpty():
            self.fitInView(items_rect.adjusted(-40, -40, 40, 40), Qt.KeepAspectRatio)
            self._zoom = self.transform().m11()


# --------------------------------------------------------------------------- #
#  Основной виджет                                                             #
# --------------------------------------------------------------------------- #

class GlobalGraphWidget(QWidget):
    """
    Центральный виджет для просмотра и редактирования структуры промпта.

    Показывает main_template.txt как интерактивный граф.
    """

    open_text_requested       = Signal(str)
    open_nodes_requested      = Signal(str)
    open_postscript_requested = Signal(str)
    open_code_requested       = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._prompts_root: str | None = None
        self._char_id: str | None = None
        self._nodes: list[TemplateNode] = []
        self._arrows: list[_GraphArrow] = []
        self._refreshing: bool = False
        self._empty_proxy = None  # QGraphicsProxyWidget для QLabel пустого состояния

        self._build_ui()

    # -- публичный API -------------------------------------------------------

    def load_character(self, prompts_root: str, char_id: str):
        """Загружает и отображает граф для персонажа."""
        self._prompts_root = prompts_root
        self._char_id = char_id
        self._refresh()

    def refresh(self):
        """Перестраивает граф (например, после сохранения main_template.txt)."""
        self._refresh()

    # -- построение UI -------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Тулбар графа ---
        toolbar = QFrame()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet("QFrame { background: #161b22; border-bottom: 1px solid #30363d; }")
        tb_row = QHBoxLayout(toolbar)
        tb_row.setContentsMargins(10, 4, 10, 4)
        tb_row.setSpacing(8)

        self._title_lbl = QLabel("Граф промпта")
        self._title_lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
        tb_row.addWidget(self._title_lbl)
        tb_row.addStretch()

        btn_fit = QPushButton("⊡ Уместить")
        btn_fit.setFixedHeight(26)
        btn_fit.setStyleSheet(_TOOLBAR_BTN_STYLE)
        btn_fit.clicked.connect(self._fit_view)
        tb_row.addWidget(btn_fit)

        btn_refresh = QPushButton("🔄 Обновить")
        btn_refresh.setFixedHeight(26)
        btn_refresh.setStyleSheet(_TOOLBAR_BTN_STYLE)
        btn_refresh.clicked.connect(self.refresh)
        tb_row.addWidget(btn_refresh)

        outer.addWidget(toolbar)

        # --- Холст ---
        self._scene = _GlobalGraphScene()
        self._scene.connection_requested.connect(self._on_connection_requested)
        self._scene.create_node_requested.connect(self._on_create_node_requested)
        self._view = _GraphView(self._scene, self)
        outer.addWidget(self._view, 1)

        # --- Пустой экран ---
        self._empty_label = QLabel("Персонаж не выбран.\nВыберите персонажа в дереве слева.")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet("color: #6e7681; font-size: 14px; background: #0d1117;")
        outer.addWidget(self._empty_label)
        self._empty_label.setVisible(True)
        self._view.setVisible(False)

    def _set_empty(self, empty: bool):
        self._empty_label.setVisible(empty)
        self._view.setVisible(not empty)

    # -- логика графа --------------------------------------------------------

    def _do_refresh_deferred(self):
        try:
            self._do_refresh()
        finally:
            self._refreshing = False

    def _refresh(self):
        # Защита от повторного входа
        if self._refreshing:
            return
        self._refreshing = True
        # Откладываем выполнение, чтобы дерево успело завершить обработку клика
        QTimer.singleShot(0, self._do_refresh_deferred)

    def _do_refresh_deferred(self):
        try:
            self._do_refresh()
        finally:
            self._refreshing = False

    def _do_refresh(self):
        self._empty_proxy = None

        # НАСТОЯЩЕЕ РЕШЕНИЕ проблемы 0xC0000409 в QGraphicsScene:
        # Вместо scene.clear() и мучительного удаления элементов по одному (что ломает C++),
        # мы просто создаем НОВУЮ сцену, а старую безопасно ставим в очередь на удаление.
        old_scene = self._scene
        self._scene = _GlobalGraphScene()
        self._scene.connection_requested.connect(self._on_connection_requested)
        self._scene.create_node_requested.connect(self._on_create_node_requested)
        self._view.setScene(self._scene)
        old_scene.deleteLater()

        self._nodes.clear()
        self._arrows.clear()

        if not self._prompts_root or not self._char_id:
            self._set_empty(True)
            return

        specs = build_graph_from_template(self._prompts_root, self._char_id)

        if not specs:
            self._set_empty(True)
            label = QLabel("main_template.txt не найден\nили не содержит включений.")
            label.setStyleSheet("color: #6e7681; font-size: 13px;")
            label.setAlignment(Qt.AlignCenter)
            self._empty_proxy = self._scene.addWidget(label)
            self._empty_proxy.setPos(0, 0)
            return

        self._set_empty(False)

        # Размещаем ноды в сетку
        for i, spec in enumerate(specs):
            col = i % _COLS
            row = i // _COLS
            x = _MARGIN_X + col * _COL_STEP
            y = _MARGIN_Y + row * _ROW_STEP

            node = TemplateNode(spec)
            node.setPos(x, y)
            self._scene.addItem(node)
            self._nodes.append(node)

            # Подключаем сигналы
            node.signals.edit_requested.connect(self.open_text_requested)
            node.signals.nodes_requested.connect(self.open_nodes_requested)
            node.signals.code_requested.connect(self.open_code_requested)
            node.signals.rules_requested.connect(self.open_postscript_requested)
            node.signals.delete_requested.connect(self._on_delete_node_requested)

        # Рисуем стрелки между всеми соседними нодами (в порядке включения)
        for i in range(len(self._nodes) - 1):
            arrow = _GraphArrow(self._nodes[i], self._nodes[i + 1])
            self._scene.addItem(arrow)
            self._arrows.append(arrow)
            self._nodes[i].add_connected_arrow(arrow)
            self._nodes[i + 1].add_connected_arrow(arrow)

        # Обновляем заголовок
        char_display = self._char_id.split("/")[-1] if "/" in self._char_id else self._char_id
        self._title_lbl.setText(f"Граф промпта: {char_display}  ({len(specs)} файл.)")

        # Подгоняем вид
        QTimer.singleShot(50, self._fit_view)

    def _fit_view(self):
        self._view.fit_all()

    # -- соединения (port drag) -----------------------------------------------

    def _on_connection_requested(self, src_node: TemplateNode, dst_node):
        """
        Пользователь соединил src → dst (или dst=None = удалить исходящую от src).
        Переставляет dst сразу после src в порядке нод, перерисовывает граф
        и перезаписывает main_template.txt.
        """
        if dst_node is None:
            # Удаление: убрать стрелку из src (src теряет преемника)
            # Находим и удаляем соответствующую стрелку
            for arrow in list(self._arrows):
                if arrow.source_node is src_node:
                    src_node.clear_connected_arrows()
                    dst_node2 = arrow.target_node
                    dst_node2.clear_connected_arrows()
                    try:
                        self._scene.removeItem(arrow)
                    except Exception:
                        pass
                    self._arrows.remove(arrow)
                    # Перебираем оставшиеся стрелки, обновляем ссылки
                    for a in self._arrows:
                        a.source_node.add_connected_arrow(a)
                        a.target_node.add_connected_arrow(a)
                    self._write_current_order()
                    return
            return

        if src_node is dst_node:
            return

        # Перестановка: перемещаем dst_node сразу после src_node
        try:
            src_idx = self._nodes.index(src_node)
            dst_idx = self._nodes.index(dst_node)
        except ValueError:
            return

        if src_idx == dst_idx - 1:
            return  # уже в нужном порядке

        # Убрать dst из текущей позиции и вставить сразу после src
        self._nodes.pop(dst_idx)
        new_src_idx = self._nodes.index(src_node)
        self._nodes.insert(new_src_idx + 1, dst_node)

        # Перестроить стрелки
        self._rebuild_arrows()
        self._write_current_order()

    def _rebuild_arrows(self):
        """Удалить все стрелки и создать заново по текущему self._nodes."""
        for arrow in list(self._arrows):
            try:
                self._scene.removeItem(arrow)
            except Exception:
                pass
        self._arrows.clear()
        for node in self._nodes:
            node.clear_connected_arrows()

        for i in range(len(self._nodes) - 1):
            arrow = _GraphArrow(self._nodes[i], self._nodes[i + 1])
            self._scene.addItem(arrow)
            self._arrows.append(arrow)
            self._nodes[i].add_connected_arrow(arrow)
            self._nodes[i + 1].add_connected_arrow(arrow)

    def _write_current_order(self):
        """Перезаписывает main_template.txt согласно текущему self._nodes."""
        ordered_raws = [n._spec["raw"] for n in self._nodes if "raw" in n._spec]
        self._write_template_order(ordered_raws)

    def _write_template_order(self, ordered_raws: list):
        """Перезаписывает порядок [<...>] включений в main_template.txt."""
        import re
        if not self._prompts_root or not self._char_id:
            return
        parts = self._char_id.split("/")
        char_base = os.path.join(self._prompts_root, *parts)
        tmpl_path = os.path.join(char_base, "main_template.txt")
        if not os.path.isfile(tmpl_path):
            return
        try:
            with open(tmpl_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return

        _RE = re.compile(r"\[<([^>]+\.(?:script|txt|system))>\]")
        matches = list(_RE.finditer(content))
        if len(matches) == 0:
            return

        # Берём только те raws, которые присутствовали в исходном файле
        orig_raws = [m.group(1) for m in matches]
        # Фил��труем ordered_raws, оставляя только те, что есть в файле
        file_raws_set = set(orig_raws)
        filtered = [r for r in ordered_raws if r in file_raws_set]
        # Добавляем не упомянутые (например postscript-ноды добавляемые отдельно)
        mentioned = set(filtered)
        for r in orig_raws:
            if r not in mentioned:
                filtered.append(r)

        if len(filtered) != len(matches):
            return  # не совпадает количество — не перезаписываем

        # Вставляем новый порядок
        result = []
        prev = 0
        for match, raw in zip(matches, filtered):
            result.append(content[prev:match.start()])
            result.append(f"[<{raw}>]")
            prev = match.end()
        result.append(content[prev:])
        new_content = "".join(result)

        try:
            with open(tmpl_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Ошибка записи шаблона",
                                 f"Не удалось сохранить main_template.txt:\n{e}")

    # -- создание / удаление нод ---------------------------------------------

    def _on_create_node_requested(self, scene_pos):
        """ПКМ на пустом холсте → меню создания новой ноды."""
        from PySide6.QtWidgets import QMenu, QInputDialog, QMessageBox
        if not self._prompts_root or not self._char_id:
            QMessageBox.information(self, "Граф", "Сначала выберите персонажа.")
            return

        menu = QMenu()
        act_txt    = menu.addAction("📄 Текстовый файл (.txt)")
        act_script = menu.addAction("⚡ Скрипт (.script)")
        act_sys    = menu.addAction("ℹ️ Системный файл (.system)")

        view = self._view
        global_pos = view.mapToGlobal(view.mapFromScene(scene_pos))
        act = menu.exec(global_pos)
        if act is None:
            return

        ext = ".txt"
        if act == act_script:
            ext = ".script"
        elif act == act_sys:
            ext = ".system"

        name, ok = QInputDialog.getText(
            self, "Новый файл", f"Имя файла (без расширения):"
        )
        if not ok or not name.strip():
            return
        name = name.strip().replace(" ", "_")
        filename = name + ext

        # Путь к папке персонажа
        parts = self._char_id.split("/")
        char_base = os.path.join(self._prompts_root, *parts)
        file_path = os.path.join(char_base, filename)

        if os.path.exists(file_path):
            QMessageBox.warning(self, "Файл существует",
                                f"Файл {filename} уже существует в папке персонажа.")
        else:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка создания", f"Не удалось создать файл:\n{e}")
                return

        # Добавляем [<filename>] в main_template.txt
        tmpl_path = os.path.join(char_base, "main_template.txt")
        try:
            existing = open(tmpl_path, "r", encoding="utf-8").read() if os.path.isfile(tmpl_path) else ""
            entry = f"[<{filename}>]"
            if entry not in existing:
                with open(tmpl_path, "a", encoding="utf-8") as f:
                    if existing and not existing.endswith("\n"):
                        f.write("\n")
                    f.write(entry + "\n")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка шаблона",
                                 f"Не удалось обновить main_template.txt:\n{e}")
            return

        self._refresh()

    def _on_delete_node_requested(self, resolved_path: str):
        """ПКМ → 'Убрать из шаблона' на ноде."""
        from PySide6.QtWidgets import QMessageBox
        # Находим ноду по пути
        target = None
        for node in self._nodes:
            if node._spec.get("resolved") == resolved_path:
                target = node
                break
        if target is None:
            return

        label = target._label
        answer = QMessageBox.question(
            self, "Убрать ноду",
            f"Убрать «{label}» из шаблона?\n"
            f"Файл на диске удалён не будет.",
            QMessageBox.Yes | QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return

        # Удаляем из списка и перестраиваем
        self._nodes.remove(target)
        self._write_current_order()
        self._rebuild_arrows()
        try:
            self._scene.removeItem(target)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
_TOOLBAR_BTN_STYLE = """
    QPushButton {
        background: #21262d; color: #8b949e;
        border: 1px solid #30363d; border-radius: 5px;
        padding: 2px 10px; font-size: 11px;
    }
    QPushButton:hover { background: #30363d; color: #e6edf3; }
    QPushButton:pressed { background: #1f6feb; color: #ffffff; }
"""
