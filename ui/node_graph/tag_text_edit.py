# File: ui/node_graph/tag_text_edit.py
from __future__ import annotations
import re
from typing import List

from PySide6.QtCore import QRectF, Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QTextCursor, QFontMetrics, QFont, QPainter
from PySide6.QtWidgets import QTextEdit


class TagTextEdit(QTextEdit):
    """
    QTextEdit с визуальными чипами:
    - [[...]] — серые плашки (LOAD и пр.);
    - {var} — аккуратные чипы переменных (рамка + лёгкая подложка), текст читаемый.
      Включается set_show_var_chips(True).
    """
    CHIP_RE = re.compile(r"\[\[([^\]]+)\]\]")
    VAR_RE  = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

    # плашки [[...]]
    CHIP_BG   = QColor("#444444")
    CHIP_FG   = QColor("#FFFFFF")
    CHIP_BR   = QColor("#666666")

    # чипы переменных
    VAR_CHIP_BG = QColor(46, 125, 50, 60)   # #2E7D32, но полупрозрачный
    VAR_CHIP_BR = QColor("#00C853")         # яркая зелёная рамка
    VAR_CHIP_FG = QColor("#E6F4EA")         # светлая надпись если понадобилось бы рисовать поверх

    CHIP_PADX = 6
    CHIP_PADY = 2
    CHIP_RADIUS = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self._show_var_chips = False
        self.setStyleSheet("""
            QTextEdit {
                background: #1A1A1A;
                color: #E0E0E0;
                border: 1px solid #444444;
                border-radius: 2px;
                padding: 4px;
            }
        """)

    def set_show_var_chips(self, on: bool):
        self._show_var_chips = on
        self.viewport().update()

    def paintEvent(self, e):
        # 1) сперва об��чный текст
        super().paintEvent(e)

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, True)

        text = self.toPlainText()
        if not text:
            return

        # 2) [[...]] — серые плашки поверх (как раньше)
        for m in self.CHIP_RE.finditer(text):
            start = m.start()
            length = m.end() - m.start()
            label = m.group(1).strip()

            for r in self._range_line_rects(start, length):
                bg = QRectF(
                    r.left() - self.CHIP_PADX,
                    r.top() + 1,
                    r.width() + 2 * self.CHIP_PADX,
                    r.height() - 2
                )
                painter.setPen(QPen(self.CHIP_BR, 1.0))
                painter.setBrush(QBrush(self.CHIP_BG))
                painter.drawRoundedRect(bg, self.CHIP_RADIUS, self.CHIP_RADIUS)

                painter.setPen(QPen(self.CHIP_FG))
                font = QFont()
                font.setPointSize(8)
                painter.setFont(font)
                text_to_draw = label if len(label) <= 40 else (label[:37] + "...")
                painter.drawText(bg.adjusted(4, 0, -4, 0), Qt.AlignVCenter | Qt.AlignLeft, text_to_draw)

        # 3) {var} — аккуратные чипы: полупрозрачная подложка рисуется ПОД текстом,
        #    затем тонкая рамка — поверх. Так текст не закрывается и читаем.
        if self._show_var_chips:
            for m in self.VAR_RE.finditer(text):
                start = m.start()
                length = m.end() - m.start()
                for r in self._range_line_rects(start, length):
                    # подложку рисуем позади текста
                    painter.save()
                    painter.setCompositionMode(QPainter.CompositionMode_DestinationOver)
                    bg = QRectF(
                        r.left() - self.CHIP_PADX + 1,
                        r.top() + 2,
                        r.width() + 2 * self.CHIP_PADX - 2,
                        r.height() - 4
                    )
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(self.VAR_CHIP_BG))
                    painter.drawRoundedRect(bg, self.CHIP_RADIUS, self.CHIP_RADIUS)
                    painter.restore()

                    # рамка поверх
                    painter.setPen(QPen(self.VAR_CHIP_BR, 1.2))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRoundedRect(bg, self.CHIP_RADIUS, self.CHIP_RADIUS)

    # ---------- helpers ----------
    def _range_line_rects(self, start: int, length: int) -> List[QRectF]:
        rects: List[QRectF] = []
        if length <= 0:
            return rects

        doc = self.document()
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
            blk_end_vis = max(blk_start, blk_end_excl - 1)

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