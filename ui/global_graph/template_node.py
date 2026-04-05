"""
ui/global_graph/template_node.py

QGraphicsItem-ноды для глобального графа промптов.

Типы нод:
  "text"       📄  — обычный .txt файл
  "script"     ⚡  — .script файл (DSL)
  "postscript" 📝  — .postscript файл (постобработка)
  "system"     ℹ️  — .system файл
  missing      ⚠️  — файл не найден

Кнопки на ноде:
  [✏ Редактировать]                — открыть текстовый редактор
  [🔵 Ноды]  (только для script)  — открыть NodeGraphEditor
  [< > Код]  (для script/postscript) — открыть код
  [⚙ Правила] (для postscript)    — открыть PostScript Rule Builder
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QObject
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
    QPainterPath, QLinearGradient,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsProxyWidget,
    QPushButton, QWidget, QHBoxLayout,
)

# ---------- цвета по типу ноды ----------
_KIND_COLORS: dict[str, tuple[str, str]] = {
    "text":       ("#1f3a5a", "#2a5a8a"),   # синий
    "script":     ("#3a3a1a", "#7a6a1a"),   # жёлтый
    "postscript": ("#3a1a1a", "#7a2a2a"),   # красный
    "system":     ("#1a3a2a", "#2a6a4a"),   # зелёный
    "missing":    ("#2a2a2a", "#4a4a4a"),   # серый
}

_KIND_ICONS: dict[str, str] = {
    "text":       "📄",
    "script":     "⚡",
    "postscript": "📝",
    "system":     "ℹ️",
    "missing":    "⚠️",
}

NODE_W = 180
NODE_H = 110


class TemplateNodeSignals(QObject):
    """Сигналы для TemplateNode (QGraphicsObject не поддерживает Signal напрямую)."""
    edit_requested    = Signal(str)   # resolved path
    nodes_requested   = Signal(str)   # resolved path (.script)
    code_requested    = Signal(str)   # resolved path
    rules_requested   = Signal(str)   # resolved path (.postscript)


class TemplateNode(QGraphicsObject):
    """
    Визуальная нода в глобальном графе.

    Сигналы (через self.signals):
        edit_requested(path)   — открыть текстовый редактор
        nodes_requested(path)  — открыть NodeGraphEditor
        code_requested(path)   — открыть как код
        rules_requested(path)  — открыть PostScript Rule Builder
    """

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self._spec = spec
        self._kind  = spec.get("kind", "text")
        self._label = spec.get("label", "?")
        self._resolved = spec.get("resolved", "")
        self._exists   = spec.get("exists", False)
        self._is_common = spec.get("is_common", False)
        self._hovered  = False

        self.signals = TemplateNodeSignals()

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        # Кнопки (через QGraphicsProxyWidget)
        self._btn_proxies: list[QGraphicsProxyWidget] = []
        self._build_buttons()

    # -- QGraphicsItem protocol --

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, NODE_W, NODE_H)

    def paint(self, painter: QPainter, option, widget=None):
        kind = self._kind if self._exists else "missing"
        dark, light = _KIND_COLORS.get(kind, _KIND_COLORS["text"])

        # Фон с градиентом
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, NODE_W, NODE_H), 10, 10)

        grad = QLinearGradient(0, 0, 0, NODE_H)
        grad.setColorAt(0, QColor(light))
        grad.setColorAt(1, QColor(dark))
        painter.fillPath(path, QBrush(grad))

        # Рамка
        if self.isSelected():
            border_color = QColor("#4a9eff")
            border_w = 2.5
        elif self._hovered:
            border_color = QColor("#8b949e")
            border_w = 1.5
        else:
            border_color = QColor("#30363d")
            border_w = 1.0
        painter.setPen(QPen(border_color, border_w))
        painter.drawPath(path)

        # Заголовок (иконка + метка)
        icon = _KIND_ICONS.get(kind, "📄")
        painter.setPen(QColor("#e6edf3"))

        # Иконка
        icon_font = QFont("Segoe UI Emoji", 16)
        painter.setFont(icon_font)
        painter.drawText(QRectF(0, 8, NODE_W, 24), Qt.AlignHCenter, icon)

        # Метка файла
        label_font = QFont("Segoe UI", 9)
        label_font.setBold(True)
        painter.setFont(label_font)
        label = self._label
        if len(label) > 22:
            label = label[:20] + "…"
        painter.drawText(QRectF(6, 34, NODE_W - 12, 18), Qt.AlignHCenter, label)

        # Бейдж "Common" если общий файл
        if self._is_common:
            badge_font = QFont("Segoe UI", 7)
            painter.setFont(badge_font)
            painter.setPen(QColor("#7ed4a5"))
            painter.drawText(QRectF(6, 52, NODE_W - 12, 14), Qt.AlignHCenter, "📦 Common")
        elif not self._exists:
            badge_font = QFont("Segoe UI", 7)
            painter.setFont(badge_font)
            painter.setPen(QColor("#f0883e"))
            painter.drawText(QRectF(6, 52, NODE_W - 12, 14), Qt.AlignHCenter, "⚠️ Файл не найден")

    def hoverEnterEvent(self, e):
        self._hovered = True
        self.update()
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(e)

    # -- кнопки --------------------------------------------------------------

    def _build_buttons(self):
        """Создаёт кнопки внутри ноды через QGraphicsProxyWidget."""
        buttons: list[tuple[str, Callable]] = []

        if self._kind == "script":
            buttons.append(("🔵 Ноды", self._on_nodes))
            buttons.append(("< > Код", self._on_code))
        elif self._kind == "postscript":
            buttons.append(("⚙ Правила", self._on_rules))
            buttons.append(("< > Код", self._on_code))
        else:
            buttons.append(("✏ Редактировать", self._on_edit))
            buttons.append(("< > Код", self._on_code))

        btn_w = (NODE_W - 12) // len(buttons) - 2
        btn_y = NODE_H - 34

        for i, (label, callback) in enumerate(buttons):
            btn = QPushButton(label)
            btn.setFixedSize(btn_w, 24)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,0.08);
                    color: #c9d1d9;
                    border: 1px solid rgba(255,255,255,0.15);
                    border-radius: 4px;
                    font-size: 9px;
                    padding: 1px 3px;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.18);
                    color: #ffffff;
                }
                QPushButton:pressed { background: rgba(74, 158, 255, 0.3); }
            """)
            btn.clicked.connect(callback)

            proxy = QGraphicsProxyWidget(self)
            proxy.setWidget(btn)
            x = 6 + i * (btn_w + 4)
            proxy.setPos(x, btn_y)
            self._btn_proxies.append(proxy)

    def _on_edit(self):
        self.signals.edit_requested.emit(self._resolved)

    def _on_nodes(self):
        self.signals.nodes_requested.emit(self._resolved)

    def _on_code(self):
        self.signals.code_requested.emit(self._resolved)

    def _on_rules(self):
        self.signals.rules_requested.emit(self._resolved)
