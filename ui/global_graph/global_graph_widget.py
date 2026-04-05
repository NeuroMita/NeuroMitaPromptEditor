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
    QPainter, QPen, QColor, QPainterPath, QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsLineItem, QGraphicsPathItem,
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QSizePolicy,
)

from ui.global_graph.template_node import TemplateNode, NODE_W, NODE_H
from ui.global_graph.template_to_graph import build_graph_from_template


# ---------- параметры лейаута ----------
_COL_STEP  = NODE_W + 60   # горизонтальный шаг между нодами
_ROW_STEP  = NODE_H + 40   # вертикальный шаг (для wrap)
_COLS      = 4              # нод в строке до переноса
_MARGIN_X  = 40
_MARGIN_Y  = 40


class _GraphArrow(QGraphicsPathItem):
    """Стрелка-соединение между нодами."""

    def __init__(self, src: TemplateNode, dst: TemplateNode):
        super().__init__()
        self._src = src
        self._dst = dst
        self.setPen(QPen(QColor("#404a56"), 1.5, Qt.SolidLine))
        self.setZValue(-1)
        self._update()

    def _update(self):
        sp = self._src.pos() + QPointF(NODE_W, NODE_H / 2)
        dp = self._dst.pos() + QPointF(0, NODE_H / 2)
        cx = (sp.x() + dp.x()) / 2

        path = QPainterPath(sp)
        path.cubicTo(QPointF(cx, sp.y()), QPointF(cx, dp.y()), dp)
        self.setPath(path)


class _GlobalGraphScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        self.setSceneRect(-5000, -5000, 10000, 10000)
        self.setBackgroundBrush(QColor("#0d1117"))


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

    def _refresh(self):
        self._scene.clear()
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
            proxy = self._scene.addWidget(label)
            proxy.setPos(0, 0)
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

        # Рисуем стрелки в горизонтальном направлении (в пределах строки)
        for i in range(len(self._nodes) - 1):
            curr = self._nodes[i]
            nxt  = self._nodes[i + 1]
            # Стрелку рисуем только если они в одной строке
            curr_row = i // _COLS
            nxt_row  = (i + 1) // _COLS
            if curr_row == nxt_row:
                arrow = _GraphArrow(curr, nxt)
                self._scene.addItem(arrow)
                self._arrows.append(arrow)

        # Обновляем заголовок
        char_display = self._char_id.split("/")[-1] if "/" in self._char_id else self._char_id
        self._title_lbl.setText(f"Граф промпта: {char_display}  ({len(specs)} файл.)")

        # Подгоняем вид
        QTimer.singleShot(50, self._fit_view)

    def _fit_view(self):
        self._view.fit_all()


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
