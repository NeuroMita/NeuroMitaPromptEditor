# File: ui/node_graph/tag_text_edit.py
from __future__ import annotations
import re
from typing import List

from PySide6.QtCore import QRectF, Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QTextCursor, QFontMetrics
from PySide6.QtWidgets import QTextEdit


class TagTextEdit(QTextEdit):
    """
    QTextEdit с визуальными чипами для вставок [[...]] и подсветкой переменных {var}.
    Все чипы — обычный текст (редактируются/удаляются как текст), но отрисовываются
    поверх как скругленные плашки.
    """
    CHIP_RE = re.compile(r"\[\[([^\]]+)\]\]")          # [[...]]
    VAR_RE  = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")

    CHIP_BG   = QColor("#304FFE")
    CHIP_FG   = QColor("#E8EAED")
    CHIP_BR   = QColor("#1A237E")
    VAR_FG    = QColor("#00BFA5")

    CHIP_PADX = 6
    CHIP_PADY = 2
    CHIP_RADIUS = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

    def paintEvent(self, e):
        # 1) сначала обычный текст
        super().paintEvent(e)

        # 2) поверх — чипы и подсветка переменных
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, True)

        text = self.toPlainText()
        if not text:
            return

        # чипы [[...]]
        for m in self.CHIP_RE.finditer(text):
            start = m.start()
            length = m.end() - m.start()
            label = m.group(1).strip()
            for r in self._range_line_rects(start, length):
                # фон плашки
                bg = QRectF(r.left() - self.CHIP_PADX, r.top() + 1, r.width() + 2 * self.CHIP_PADX, r.height() - 2)
                painter.setPen(QPen(self.CHIP_BR, 1.2))
                painter.setBrush(QBrush(self.CHIP_BG))
                painter.drawRoundedRect(bg, self.CHIP_RADIUS, self.CHIP_RADIUS)

                # текст плашки, укоротим при необходимости
                painter.setPen(QPen(self.CHIP_FG))
                text_to_draw = label
                if len(text_to_draw) > 48:
                    text_to_draw = text_to_draw[:45] + "..."
                painter.drawText(bg.adjusted(6, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, text_to_draw)

        # подчеркнем переменные {var}
        painter.setPen(QPen(self.VAR_FG, 1.5))
        for m in self.VAR_RE.finditer(text):
            start = m.start()
            length = m.end() - m.start()
            for r in self._range_line_rects(start, length):
                painter.drawLine(r.bottomLeft() + QPointF(0, -1), r.bottomRight() + QPointF(0, -1))

    # ---------- helpers ----------
    def _range_line_rects(self, start: int, length: int) -> List[QRectF]:
        """
        Возвращает список прямоугольников в координатах viewport() для диапазона текста.
        Диапазон безопасно ограничивается границами документа, чтобы избежать
        QTextCursor::setPosition out of range.
        """
        rects: List[QRectF] = []
        if length <= 0:
            return rects

        doc = self.document()
        # characterCount включает финальный перенос; допустимый максимум = count-1
        max_pos = max(0, doc.characterCount() - 1)

        def clamp(p: int) -> int:
            if p < 0:
                return 0
            if p > max_pos:
                return max_pos
            return p

        start = clamp(start)
        end_exclusive = clamp(start + length)

        if end_exclusive <= start:
            return rects

        cur = QTextCursor(doc)
        cur.setPosition(start)

        while cur.position() < end_exclusive:
            block = cur.block()
            if not block.isValid():
                break

            block_pos = block.position()
            block_len = block.length()  # включает терминатор строки

            blk_start = max(start, block_pos)
            blk_end_excl = min(end_exclusive, block_pos + block_len)
            blk_end_vis = max(blk_start, blk_end_excl - 1)  # последняя видимая позиция

            c1 = QTextCursor(doc); c1.setPosition(clamp(blk_start))
            c2 = QTextCursor(doc); c2.setPosition(clamp(blk_end_vis))

            r1 = self.cursorRect(c1)
            r2 = self.cursorRect(c2)

            if r2.left() <= r1.left():
                fm = QFontMetrics(self.font())
                chcount = max(1, blk_end_vis - blk_start)
                width = max(10, fm.horizontalAdvance("W") * chcount)
                rects.append(QRectF(r1.left(), r1.top(), width, r1.height()))
            else:
                rects.append(QRectF(r1.left(), r1.top(), r2.left() - r1.left(), r1.height()))

            next_pos = clamp(blk_end_excl)
            if next_pos <= cur.position():
                break
            cur.setPosition(next_pos)

        return rects