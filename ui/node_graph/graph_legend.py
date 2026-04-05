# File: ui/node_graph/graph_legend.py
from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel

from ui.node_graph.graph_primitives import NODE_TYPE_STYLES

# (тип, читаемое название)
_LEGEND_ITEMS = [
    ("SET",             "Установить переменную"),
    ("LOG",             "Записать в лог"),
    ("ADD_SYSTEM_INFO", "Системная информация"),
    ("RETURN",          "Вернуть результат"),
    ("IF",              "Условие"),
    ("SEED_MEMORY",     "Добавить в память"),
]


class _ColorDot(QWidget):
    """Маленький прямоугольник с градиентом цвета типа ноды."""
    def __init__(self, dark_hex: str, light_hex: str, parent=None):
        super().__init__(parent)
        self._dark = QColor(dark_hex)
        self._light = QColor(light_hex)
        self.setFixedSize(14, 14)

    def paintEvent(self, event):
        from PySide6.QtGui import QLinearGradient
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, 0, 14)
        grad.setColorAt(0, self._light)
        grad.setColorAt(1, self._dark)
        p.setBrush(QBrush(grad))
        p.setPen(QPen(self._dark.darker(140), 1))
        p.drawRoundedRect(1, 1, 12, 12, 3, 3)
        p.end()


class NodeLegend(QWidget):
    """
    Компактная легенда типов нод. Размещается поверх GraphView
    через setParent(view) + абсолютное позиционирование.
    Свёрнута по умолчанию.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        parent.installEventFilter(self)
        self.setStyleSheet("""
            NodeLegend {
                background: rgba(22, 22, 22, 210);
                border: 1px solid #444;
                border-radius: 6px;
            }
            QLabel { color: #CCCCCC; font-size: 8pt; background: transparent; }
            QPushButton {
                background: transparent; color: #AAAAAA;
                border: none; font-size: 8pt; padding: 2px 6px;
            }
            QPushButton:hover { color: #FFFFFF; }
        """)

        self._expanded = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 6)
        outer.setSpacing(2)

        # Заголовок / кнопка
        hdr = QHBoxLayout()
        hdr.setSpacing(0)
        self._toggle_btn = QPushButton("? Легенда")
        self._toggle_btn.setFixedHeight(22)
        self._toggle_btn.clicked.connect(self._toggle)
        hdr.addWidget(self._toggle_btn)
        outer.addLayout(hdr)

        # Тело (скрыто по умолчанию)
        self._body = QWidget(self)
        self._body.setStyleSheet("background: transparent;")
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(0, 4, 0, 0)
        body_lay.setSpacing(3)

        for ntype, label in _LEGEND_ITEMS:
            style = NODE_TYPE_STYLES.get(ntype)
            if not style:
                continue
            emoji, dark_hex, light_hex = style
            row = QHBoxLayout()
            row.setSpacing(4)
            dot = _ColorDot(dark_hex, light_hex, self._body)
            emoji_lbl = QLabel(emoji)
            emoji_lbl.setFixedWidth(18)
            text_lbl = QLabel(label)
            row.addWidget(dot)
            row.addWidget(emoji_lbl)
            row.addWidget(text_lbl)
            row.addStretch(1)
            body_lay.addLayout(row)

        outer.addWidget(self._body)
        self._body.hide()

        self._update_size()
        self.show()

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self._body.show()
            self._toggle_btn.setText("✕ Легенда")
        else:
            self._body.hide()
            self._toggle_btn.setText("? Легенда")
        self._update_size()
        self._reposition()

    def _update_size(self):
        self.adjustSize()

    def _reposition(self):
        """Прибиться к правому нижнему углу родителя."""
        p = self.parent()
        if p is None:
            return
        margin = 12
        x = p.width() - self.width() - margin
        y = p.height() - self.height() - margin
        self.move(max(0, x), max(0, y))

    def reposition(self):
        self._reposition()

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self.parent() and event.type() == QEvent.Resize:
            self._reposition()
        return False
