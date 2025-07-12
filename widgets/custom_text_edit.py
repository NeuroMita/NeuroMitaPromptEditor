# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QUrl, Signal
from PySide6.QtGui import (QColor, QFont, QKeySequence, QMouseEvent, QPainter,
                           QTextBlock, QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QWidget

from syntax.highlighter import PromptSyntaxHighlighter
from utils.logger import editor_logger


# ─────────────────────────  Line-number area  ──────────────────────────
class LineNumberArea(QWidget):
    def __init__(self, editor: "CustomTextEdit"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):                       # noqa: N802
        self._editor.paint_line_numbers(event)


# ─────────────────────────────   Editor   ──────────────────────────────
class CustomTextEdit(QPlainTextEdit):
    open_file_requested = Signal(str)
    save_requested = Signal(object)

    TAB_SPACES = 4
    COMMENT_PREFIX = "// "
    COMMENT_PREFIX_NO_SPACE = "//"
    _IGNORED_CTRL_CHARS = "\x00"

    @classmethod
    def _sanitize(cls, text):
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="replace")
        return text.translate({ord(c): None for c in cls._IGNORED_CTRL_CHARS})

    

    def __init__(self, parent=None):
        super().__init__(parent)

        # line numbers
        self._line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self._line_number_area.update)
        self.cursorPositionChanged.connect(self.viewport().update)
        self.update_line_number_area_width()

        # misc
        self.setMouseTracking(True)
        self.setTabStopDistance(
            self.fontMetrics().horizontalAdvance(' ') * self.TAB_SPACES
        )
        self.setUndoRedoEnabled(True)

        self.highlighter: PromptSyntaxHighlighter | None = None
        self._tab_file_path: str | None = None

    # ───────────  line-numbers helpers  ───────────
    def line_number_area_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return self.fontMetrics().horizontalAdvance('9') * digits + 10

    def update_line_number_area_width(self, _=0):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect: QRect, dy: int):
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(), self._line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(),
                  self.line_number_area_width(), cr.height())
        )

    def paint_line_numbers(self, event):
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor(40, 40, 40))

        current_block_num = self.textCursor().blockNumber()
        block = self.firstVisibleBlock()
        block_num = block.blockNumber()
        top = round(self.blockBoundingGeometry(block)
                    .translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        line_h = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_num + 1)
                if block_num == current_block_num:
                    painter.setPen(QColor(220, 220, 220))
                    painter.setFont(QFont(self.font().family(),
                                          self.font().pointSize(), QFont.Bold))
                else:
                    painter.setPen(QColor(150, 150, 150))
                    painter.setFont(self.font())
                painter.drawText(0, top,
                                 self._line_number_area.width() - 4, line_h,
                                 Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_num += 1

    # ───────────  subtle cursor lines  ───────────
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setPen(QColor(70, 70, 70))
        rect = self.cursorRect()
        y_top, y_bot = rect.top(), rect.bottom()
        w = self.viewport().width()
        painter.drawLine(0, y_top, w, y_top)
        painter.drawLine(0, y_bot, w, y_bot)

    # ───────────  public setters  ───────────
    def set_tab_file_path(self, path: str | None):
        self._tab_file_path = path

    def get_tab_file_path(self) -> str | None:
        return self._tab_file_path

    def set_highlighter(self, highlighter: PromptSyntaxHighlighter):
        self.highlighter = highlighter

    # ───────────  helper: формат в точке  ───────────
    def get_format_from_layout_at_point(self, point) -> QTextCharFormat | None:
        if not self.highlighter:
            return None
        cur = self.cursorForPosition(point)
        block = cur.block()
        if not block.isValid() or not block.layout():
            return None
        layout = block.layout()
        pos = cur.positionInBlock()
        for fr in layout.formats():
            if fr.start <= pos < fr.start + fr.length:
                return QTextCharFormat(fr.format)
        if pos > 0:
            for fr in layout.formats():
                if fr.start <= pos - 1 < fr.start + fr.length:
                    return QTextCharFormat(fr.format)
        return None

    # ───────────  mouse  ───────────
    def mousePressEvent(self, event: QMouseEvent):
        if (event.button() == Qt.LeftButton and
                bool(event.modifiers() & Qt.ControlModifier) and
                self.highlighter):
            fmt = self.get_format_from_layout_at_point(
                event.position().toPoint())
            if (fmt and fmt.hasProperty(self.highlighter.LinkPathPropertyId)):
                url = fmt.property(self.highlighter.LinkPathPropertyId)
                if isinstance(url, QUrl) and url.isLocalFile():
                    path = url.toLocalFile()
                    editor_logger.info(f"Ctrl+Hyperlink clicked: {path}")
                    self.open_file_requested.emit(path)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.highlighter:
            fmt = self.get_format_from_layout_at_point(
                event.position().toPoint())
            ctrl = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
            if (ctrl and fmt and
                    fmt.hasProperty(self.highlighter.LinkPathPropertyId)):
                self.viewport().setCursor(Qt.PointingHandCursor)
            else:
                self.viewport().setCursor(Qt.IBeamCursor)
        else:
            self.viewport().setCursor(Qt.IBeamCursor)
        super().mouseMoveEvent(event)

    # ───────────  key  ───────────
    def keyPressEvent(self, event):
        cur = self.textCursor()
        key = event.key()
        mod = event.modifiers()

        if event.matches(QKeySequence.StandardKey.Save):
            self.save_requested.emit(self)
            event.accept()
            return

        if key == Qt.Key_Slash and mod == Qt.ControlModifier:            # Ctrl+/
            self.toggle_comment_selection()
            event.accept()
            return

        if key == Qt.Key_Tab and mod == Qt.ControlModifier:             # Ctrl+Tab
            if cur.hasSelection():
                self.indent_selection()
            else:
                cur.insertText("\t")
            event.accept()
            return

        if key == Qt.Key_Backtab and mod == Qt.ControlModifier:         # Ctrl+Shift+Tab
            if cur.hasSelection():
                self.unindent_selection()
            event.accept()
            return

        if key == Qt.Key_Tab:                                           # Tab / Shift+Tab
            if cur.hasSelection():
                if mod == Qt.ShiftModifier:
                    self.unindent_selection()
                else:
                    self.indent_selection()
                event.accept()
                return

        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.apply_auto_indent_after_enter(event)
            return

        super().keyPressEvent(event)

    # ───────────  selection helpers  ───────────
    def _get_selected_block_numbers(self, cursor: QTextCursor):
        if not cursor.hasSelection():
            return None
        s, e = cursor.selectionStart(), cursor.selectionEnd()
        tmp = QTextCursor(self.document())
        tmp.setPosition(s)
        sb = tmp.blockNumber()
        tmp.setPosition(e)
        eb = tmp.blockNumber()
        if tmp.columnNumber() == 0 and e != s and eb > sb:
            eb -= 1
        return sb, eb

    def _reselect_blocks(self, start: int, end: int):
        cur = QTextCursor(self.document())
        sb = self.document().findBlockByNumber(start)
        eb = self.document().findBlockByNumber(end)
        if not sb.isValid() or not eb.isValid():
            return
        cur.setPosition(sb.position())
        cur.setPosition(eb.position() + len(eb.text()),
                        QTextCursor.KeepAnchor)
        self.setTextCursor(cur)

    # ───────────  indent / unindent  ───────────
    def indent_selection(self):
        cur = self.textCursor()
        rng = self._get_selected_block_numbers(cur)
        if not rng:
            return
        s, e = rng
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        for i in range(s, e + 1):
            blk = self.document().findBlockByNumber(i)
            if blk.isValid():
                edit.setPosition(blk.position())
                edit.insertText("\t")
        edit.endEditBlock()
        self._reselect_blocks(s, e)

    def unindent_selection(self):
        cur = self.textCursor()
        rng = self._get_selected_block_numbers(cur)
        if not rng:
            return
        s, e = rng
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        for i in range(s, e + 1):
            blk = self.document().findBlockByNumber(i)
            if not blk.isValid():
                continue
            edit.setPosition(blk.position())
            line = blk.text()
            if line.startswith("\t"):
                edit.deleteChar()
            else:
                rm = 0
                for ch in line[:self.TAB_SPACES]:
                    if ch == ' ':
                        rm += 1
                    else:
                        break
                for _ in range(rm):
                    edit.deleteChar()
        edit.endEditBlock()
        self._reselect_blocks(s, e)

    # ───────────  commenting  ───────────
    def _toggle_comment_for_block(self, block: QTextBlock,
                                  uncomment: bool,
                                  edit: QTextCursor):
        if not block.isValid():
            return
        edit.setPosition(block.position())
        txt = block.text()
        ws = 0
        for c in txt:
            if c.isspace():
                ws += 1
            else:
                break
        edit.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, ws)
        after = txt.lstrip()
        if uncomment:
            if after.startswith(self.COMMENT_PREFIX):
                for _ in range(len(self.COMMENT_PREFIX)):
                    edit.deleteChar()
            elif after.startswith(self.COMMENT_PREFIX_NO_SPACE):
                for _ in range(len(self.COMMENT_PREFIX_NO_SPACE)):
                    edit.deleteChar()
        else:
            edit.insertText(self.COMMENT_PREFIX_NO_SPACE)
            if after:
                edit.insertText(" ")

    def toggle_comment_selection(self):
        cur = self.textCursor()
        sel = cur.hasSelection()
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        if sel:
            rng = self._get_selected_block_numbers(cur)
            if not rng:
                edit.endEditBlock()
                return
            s, e = rng
            first = self.document().findBlockByNumber(s)
            uncomment = first.text().lstrip().startswith(
                self.COMMENT_PREFIX_NO_SPACE)
            for i in range(s, e + 1):
                blk = self.document().findBlockByNumber(i)
                self._toggle_comment_for_block(blk, uncomment, edit)
        else:
            blk = cur.block()
            uncomment = blk.text().lstrip().startswith(
                self.COMMENT_PREFIX_NO_SPACE)
            self._toggle_comment_for_block(blk, uncomment, edit)
            s = e = blk.blockNumber()
        edit.endEditBlock()
        if sel:
            self._reselect_blocks(s, e)

    # ───────────  auto-indent  ───────────
    def apply_auto_indent_after_enter(self, event):
        prev_block = self.textCursor().block()
        prev_text  = prev_block.text()

        leading_ws = ""
        for ch in prev_text:
            if ch.isspace():
                leading_ws += ch
            else:
                break

        stripped = prev_text.rstrip().upper()
        need_extra = stripped.endswith("THEN") or stripped == "ELSE"
        extra = "\t" if need_extra else ""

        super().keyPressEvent(event)

        cur = self.textCursor()
        cur.insertText(leading_ws + extra)
        self.ensureCursorVisible()
        event.accept()