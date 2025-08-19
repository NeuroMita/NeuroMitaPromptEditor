# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QTextBlock,
    QTextCharFormat,
    QTextCursor,
    QGuiApplication,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QWidget, QTextEdit

from syntax.highlighter import PromptSyntaxHighlighter
from utils.logger import editor_logger


# ─────────────────────────  Line-number area  ──────────────────────────
class LineNumberArea(QWidget):
    def __init__(self, editor: "CustomTextEdit"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):  # noqa: N802
        self._editor.paint_line_numbers(event)


# ─────────────────────────────   Editor   ──────────────────────────────
class CustomTextEdit(QPlainTextEdit):
    open_file_requested = Signal(str)
    save_requested = Signal(object)

    TAB_SPACES = 4
    COMMENT_PREFIX = "// "
    COMMENT_PREFIX_NO_SPACE = "//"
    _IGNORED_CTRL_CHARS = "\x00"

    # Пары для автоскобок и подсветки
    _BRACKETS_OPEN = "([{\'\""
    _BRACKETS_MAP = {
        "(": ")",
        "[": "]",
        "{": "}",
        "'": "'",
        '"': '"',
    }
    _BRACKETS_REVERSE = {v: k for k, v in _BRACKETS_MAP.items()}

    # Палитра
    _CLR_LINENUM_BG = QColor(40, 40, 40)
    _CLR_LINENUM_FG = QColor(150, 150, 150)
    _CLR_LINENUM_FG_ACTIVE = QColor(220, 220, 220)

    _CLR_CURRENT_LINE = QColor(70, 80, 100, 80)
    _CLR_MATCH_BRACKETS = QColor(120, 180, 220, 130)
    _CLR_SELECTION_MATCH = QColor(200, 200, 120, 90)
    _CLR_TRAILING_WS = QColor(220, 120, 120, 60)
    _CLR_RECT_SELECTION = QColor(110, 170, 255, 90)

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
        self.cursorPositionChanged.connect(self._update_extra_selections)
        self.selectionChanged.connect(self._update_extra_selections)
        self.update_line_number_area_width()

        # misc
        self.setMouseTracking(True)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * self.TAB_SPACES)
        self.setUndoRedoEnabled(True)

        # подсветчик (внешний)
        self.highlighter: PromptSyntaxHighlighter | None = None
        self._tab_file_path: str | None = None

        # состояния прямоугольного выделения
        self._rect_active: bool = False
        self._rect_anchor: Optional[Tuple[int, int]] = None  # (blockNumber, vcol)
        self._rect_cursor: Optional[Tuple[int, int]] = None  # (blockNumber, vcol)
        self._rect_extra: List[QTextEdit.ExtraSelection] = []

        # первичная отрисовка
        self._update_extra_selections()

    # ───────────  line-numbers helpers  ───────────
    def line_number_area_width(self) -> int:
        digits = len(str(max(1, self.blockCount())))
        return self.fontMetrics().horizontalAdvance("9") * digits + 10

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
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def paint_line_numbers(self, event):
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), self._CLR_LINENUM_BG)

        current_block_num = self.textCursor().blockNumber()
        block = self.firstVisibleBlock()
        block_num = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        line_h = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_num + 1)
                if block_num == current_block_num:
                    painter.setPen(self._CLR_LINENUM_FG_ACTIVE)
                    painter.setFont(QFont(self.font().family(), self.font().pointSize(), QFont.Bold))
                else:
                    painter.setPen(self._CLR_LINENUM_FG)
                    painter.setFont(self.font())
                painter.drawText(
                    0, top, self._line_number_area.width() - 4, line_h, Qt.AlignRight, number
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_num += 1

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
        # Ctrl+клик по ссылке
        if (
            event.button() == Qt.LeftButton
            and bool(event.modifiers() & Qt.ControlModifier)
            and self.highlighter
        ):
            fmt = self.get_format_from_layout_at_point(event.position().toPoint())
            if fmt and fmt.hasProperty(self.highlighter.LinkPathPropertyId):
                url = fmt.property(self.highlighter.LinkPathPropertyId)
                if isinstance(url, QUrl) and url.isLocalFile():
                    path = url.toLocalFile()
                    editor_logger.info(f"Ctrl+Hyperlink clicked: {path}")
                    self.open_file_requested.emit(path)
                    event.accept()
                    return

        # Alt+ЛКМ — прямоугольное выделение
        if event.button() == Qt.LeftButton and bool(event.modifiers() & Qt.AltModifier):
            self._start_rect_selection(event.position().toPoint())
            event.accept()
            return

        # обычный клик — если было прямоугольное выделение, сбрасываем
        if self._rect_active:
            self._clear_rect_selection()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # Курсор при Ctrl над ссылкой
        if self.highlighter:
            fmt = self.get_format_from_layout_at_point(event.position().toPoint())
            ctrl = bool(QApplication.keyboardModifiers() & Qt.ControlModifier)
            if ctrl and fmt and fmt.hasProperty(self.highlighter.LinkPathPropertyId):
                self.viewport().setCursor(Qt.PointingHandCursor)
            else:
                self.viewport().setCursor(Qt.IBeamCursor)
        else:
            self.viewport().setCursor(Qt.IBeamCursor)

        # drag при Alt — обновление прямоугольного выделения
        if self._rect_active and (event.buttons() & Qt.LeftButton):
            self._update_rect_selection(event.position().toPoint())
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._rect_active and event.button() == Qt.LeftButton:
            # фиксируем выделение; остаётся активно для Copy/Cut
            self._apply_rect_extra_selections()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # Зум колесом при Ctrl
    def wheelEvent(self, event):
        if QApplication.keyboardModifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoomIn(1)
            elif delta < 0:
                self.zoomOut(1)
            event.accept()
            return
        super().wheelEvent(event)

    # ───────────  key  ───────────
    def keyPressEvent(self, event):
        cur = self.textCursor()
        key = event.key()
        mod = event.modifiers()

        # Сохранение
        if event.matches(QKeySequence.StandardKey.Save):
            self.save_requested.emit(self)
            event.accept()
            return

        # Esc — сброс прямоугольного выделения
        if key == Qt.Key_Escape and self._rect_active:
            self._clear_rect_selection()
            event.accept()
            return

        # Комментирование
        if key == Qt.Key_Slash and mod == Qt.ControlModifier:  # Ctrl+/
            self.toggle_comment_selection()
            event.accept()
            return

        # Индентация
        if key == Qt.Key_Tab and mod == Qt.ControlModifier:  # Ctrl+Tab
            if cur.hasSelection():
                self.indent_selection()
            else:
                cur.insertText("\t")
            event.accept()
            return

        if key == Qt.Key_Backtab and mod == Qt.ControlModifier:  # Ctrl+Shift+Tab
            if cur.hasSelection():
                self.unindent_selection()
            event.accept()
            return

        if key == Qt.Key_Tab:  # Tab / Shift+Tab
            if cur.hasSelection():
                if mod == Qt.ShiftModifier:
                    self.unindent_selection()
                else:
                    self.indent_selection()
                event.accept()
                return

        # Прямоугольное выделение: операции буфера обмена и удаления
        if self._rect_active:
            if event.matches(QKeySequence.Copy):
                self._rect_copy_to_clipboard()
                event.accept()
                return
            if event.matches(QKeySequence.Cut):
                self._rect_cut_to_clipboard()
                event.accept()
                return
            if event.matches(QKeySequence.Paste):
                self._rect_paste_from_clipboard()
                event.accept()
                return
            if key in (Qt.Key_Delete, Qt.Key_Backspace):
                self._rect_delete_selection()
                event.accept()
                return

        # Умный Home/End
        if key in (Qt.Key_Home, Qt.Key_End) and mod in (Qt.NoModifier, Qt.ShiftModifier):
            if self._smart_home_end(key == Qt.Key_End, select=(mod == Qt.ShiftModifier)):
                event.accept()
                return

        # Авто-скобки/кавычки
        if mod == Qt.NoModifier and self._handle_auto_brackets(event):
            event.accept()
            return

        # Авто-отступ по Enter
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
        cur.setPosition(eb.position() + len(eb.text()), QTextCursor.KeepAnchor)
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
                for ch in line[: self.TAB_SPACES]:
                    if ch == " ":
                        rm += 1
                    else:
                        break
                for _ in range(rm):
                    edit.deleteChar()
        edit.endEditBlock()
        self._reselect_blocks(s, e)

    # ───────────  commenting  ───────────
    def _toggle_comment_for_block(self, block: QTextBlock, uncomment: bool, edit: QTextCursor):
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
            uncomment = first.text().lstrip().startswith(self.COMMENT_PREFIX_NO_SPACE)
            for i in range(s, e + 1):
                blk = self.document().findBlockByNumber(i)
                self._toggle_comment_for_block(blk, uncomment, edit)
        else:
            blk = cur.block()
            uncomment = blk.text().lstrip().startswith(self.COMMENT_PREFIX_NO_SPACE)
            self._toggle_comment_for_block(blk, uncomment, edit)
            s = e = blk.blockNumber()
        edit.endEditBlock()
        if sel:
            self._reselect_blocks(s, e)

    # ───────────  auto-indent  ───────────
    def apply_auto_indent_after_enter(self, event):
        prev_block = self.textCursor().block()
        prev_text = prev_block.text()

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
        self.setTextCursor(cur)
        self.ensureCursorVisible()
        event.accept()

    # ───────────  ExtraSelections (current line, brackets, matches, rect)  ───────────
    def _update_extra_selections(self):
        selections: List[QTextEdit.ExtraSelection] = []

        # Текущая строка
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(self._CLR_CURRENT_LINE)
        sel.format.setProperty(QTextFormat.FullWidthSelection, True)  # type: ignore
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        selections.append(sel)

        # Подсветка парных скобок
        bracket_pairs = self._find_matching_brackets()
        for a, b in bracket_pairs:
            for pos in (a, b):
                bs = QTextEdit.ExtraSelection()
                bs.format.setBackground(self._CLR_MATCH_BRACKETS)
                cur = QTextCursor(self.document())
                cur.setPosition(pos)
                cur.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, 1)
                bs.cursor = cur
                selections.append(bs)

        # Подсветка всех вхождений выделения (если выделено слово/фрагмент)
        selc = self.textCursor()
        if selc.hasSelection():
            text = selc.selectedText()
            if 2 <= len(text) <= 64 and "\u2029" not in text:  # без многострочного
                doc_text = self.document().toPlainText()
                start = 0
                while True:
                    idx = doc_text.find(text, start)
                    if idx == -1:
                        break
                    msel = QTextEdit.ExtraSelection()
                    msel.format.setBackground(self._CLR_SELECTION_MATCH)
                    cur2 = QTextCursor(self.document())
                    cur2.setPosition(idx)
                    cur2.setPosition(idx + len(text), QTextCursor.KeepAnchor)
                    msel.cursor = cur2
                    selections.append(msel)
                    start = idx + len(text)

        # Прямоугольное выделение — добавляем его "подсветку"
        selections.extend(self._rect_extra)

        self.setExtraSelections(selections)

    # ───────────  matching brackets  ───────────
    def _find_matching_brackets(self) -> List[Tuple[int, int]]:
        res: List[Tuple[int, int]] = []
        c = self.textCursor()
        pos = c.position()

        # Смотрим символ слева и справа
        doc = self.document()
        def char_at(p: int) -> Optional[str]:
            if p < 0 or p >= doc.characterCount() - 1:  # -1: Qt "EOF" char
                return None
            return doc.toPlainText()[p]

        left = char_at(pos - 1)
        right = char_at(pos)

        target_pos = None
        opening = None
        direction = 0

        if left in self._BRACKETS_MAP:
            opening = left
            target_pos = pos - 1
            direction = +1
        elif right in self._BRACKETS_REVERSE:
            opening = self._BRACKETS_REVERSE[right]
            target_pos = pos
            direction = -1

        if target_pos is None or opening is None:
            return res

        closing = self._BRACKETS_MAP[opening]
        text = doc.toPlainText()
        depth = 0
        i = target_pos
        n = len(text) - 1

        if direction > 0:
            # Вперёд, ищем closing
            for j in range(i, n):
                ch = text[j]
                if ch == opening:
                    depth += 1
                elif ch == closing:
                    depth -= 1
                    if depth == 0:
                        res.append((i, j))
                        break
        else:
            # Назад, ищем opening
            for j in range(i, -1, -1):
                ch = text[j]
                if ch == closing:
                    depth += 1
                elif ch == opening:
                    depth -= 1
                    if depth == 0:
                        res.append((j, i))
                        break
        return res

    # ───────────  smart Home/End  ───────────
    def _smart_home_end(self, is_end: bool, select: bool) -> bool:
        cur = self.textCursor()
        block = cur.block()
        text = block.text()
        if is_end:
            target = block.position() + len(text)
        else:
            # первый непробельный
            stripped = len(text) - len(text.lstrip())
            cur_col = cur.position() - block.position()
            target = block.position() + (0 if cur_col == stripped else stripped)

        m = QTextCursor.MoveAnchor if not select else QTextCursor.KeepAnchor
        cur.setPosition(target, m)
        self.setTextCursor(cur)
        return True

    # ───────────  auto brackets  ───────────
    def _handle_auto_brackets(self, event) -> bool:
        ch = event.text()
        if not ch:
            return False

        cur = self.textCursor()
        next_char = None
        doc = self.document().toPlainText()
        if cur.position() < len(doc):
            next_char = doc[cur.position()]

        # Оборачивание выделения
        if cur.hasSelection() and ch in self._BRACKETS_OPEN:
            pair = self._BRACKETS_MAP[ch]
            t = cur.selectedText()
            cur.insertText(f"{ch}{t}{pair}")
            return True

        # Авто-вставка парной
        if ch in self._BRACKETS_OPEN and not cur.hasSelection():
            pair = self._BRACKETS_MAP[ch]
            # не вставляем двойную, если справа уже стоит закрывающая
            if next_char and next_char.strip() and next_char not in ")]}\"'":
                cur.insertText(ch)
                return True
            cur.insertText(ch + pair)
            # сместиться назад внутрь пары
            cur.movePosition(QTextCursor.Left)
            self.setTextCursor(cur)
            return True

        # Пропуск закрывающей, если она уже стоит
        if ch in self._BRACKETS_REVERSE and next_char == ch:
            cur.movePosition(QTextCursor.Right)
            self.setTextCursor(cur)
            return True

        return False

    # ───────────  Rectangular (Alt) selection helpers  ───────────
    def _cursor_block_and_vcol_at_point(self, pt: QPoint) -> Tuple[int, int]:
        c = self.cursorForPosition(pt)
        block = c.block()
        text = block.text()
        pos_in_block = c.positionInBlock()
        vcol = self._visible_column_of(text, pos_in_block)
        return block.blockNumber(), vcol

    def _start_rect_selection(self, pt: QPoint):
        self._rect_active = True
        self._rect_anchor = self._cursor_block_and_vcol_at_point(pt)
        self._rect_cursor = self._rect_anchor
        self._apply_rect_extra_selections()

    def _update_rect_selection(self, pt: QPoint):
        if not self._rect_active or self._rect_anchor is None:
            return
        self._rect_cursor = self._cursor_block_and_vcol_at_point(pt)
        self._apply_rect_extra_selections()

    def _clear_rect_selection(self):
        self._rect_active = False
        self._rect_anchor = None
        self._rect_cursor = None
        self._rect_extra = []
        self._update_extra_selections()

    def _apply_rect_extra_selections(self):
        self._rect_extra = []
        if not (self._rect_active and self._rect_anchor and self._rect_cursor):
            self._update_extra_selections()
            return

        (a_block, a_col) = self._rect_anchor
        (b_block, b_col) = self._rect_cursor
        top = min(a_block, b_block)
        bot = max(a_block, b_block)
        left = min(a_col, b_col)
        right = max(a_col, b_col)

        doc = self.document()
        for bn in range(top, bot + 1):
            block = doc.findBlockByNumber(bn)
            if not block.isValid():
                continue
            text = block.text()
            start_pos_in_block = self._pos_from_visible_column(text, left)
            end_pos_in_block = self._pos_from_visible_column(text, right)
            if end_pos_in_block < start_pos_in_block:
                start_pos_in_block, end_pos_in_block = end_pos_in_block, start_pos_in_block

            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(self._CLR_RECT_SELECTION)
            cur = QTextCursor(doc)
            cur.setPosition(block.position() + start_pos_in_block)
            cur.setPosition(block.position() + end_pos_in_block, QTextCursor.KeepAnchor)
            sel.cursor = cur
            self._rect_extra.append(sel)

        self._update_extra_selections()

    # Clipboard ops for rect selection
    def _rect_ranges(self) -> Tuple[int, int, int, int, List[Tuple[QTextBlock, int, int, int, int]]]:
        assert self._rect_active and self._rect_anchor and self._rect_cursor
        (a_block, a_col) = self._rect_anchor
        (b_block, b_col) = self._rect_cursor
        top = min(a_block, b_block)
        bot = max(a_block, b_block)
        left = min(a_col, b_col)
        right = max(a_col, b_col)

        ranges = []
        doc = self.document()
        for bn in range(top, bot + 1):
            block = doc.findBlockByNumber(bn)
            text = block.text()
            s = self._pos_from_visible_column(text, left)
            e = self._pos_from_visible_column(text, right)
            # запомним также видимые колонки для выравнивания при копировании
            v_s = self._visible_column_of(text, s)
            v_e = self._visible_column_of(text, e)
            ranges.append((block, s, e, v_s, v_e))
        return top, bot, left, right, ranges

    def _rect_copy_to_clipboard(self):
        if not (self._rect_active and self._rect_anchor and self._rect_cursor):
            return
        _, _, left, right, ranges = self._rect_ranges()
        width = right - left
        parts = []
        for block, s, e, v_s, v_e in ranges:
            text = block.text()
            piece = text[s:e]
            # Дополняем пробелами справа, если надо, чтобы сохранить "прямоугольник"
            visible_width = v_e - v_s
            if visible_width < width:
                piece += " " * (width - visible_width)
            parts.append(piece)
        QGuiApplication.clipboard().setText("\n".join(parts))

    def _rect_cut_to_clipboard(self):
        if not (self._rect_active and self._rect_anchor and self._rect_cursor):
            return
        self._rect_copy_to_clipboard()
        _, _, _, _, ranges = self._rect_ranges()
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        # удаляем снизу вверх, чтобы не ломать позиции
        for block, s, e, _, _ in reversed(ranges):
            cur = QTextCursor(self.document())
            cur.setPosition(block.position() + s)
            cur.setPosition(block.position() + e, QTextCursor.KeepAnchor)
            cur.removeSelectedText()
        edit.endEditBlock()
        self._clear_rect_selection()

    def _rect_delete_selection(self):
        if not (self._rect_active and self._rect_anchor and self._rect_cursor):
            return
        _, _, _, _, ranges = self._rect_ranges()
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        for block, s, e, _, _ in reversed(ranges):
            cur = QTextCursor(self.document())
            cur.setPosition(block.position() + s)
            cur.setPosition(block.position() + e, QTextCursor.KeepAnchor)
            cur.removeSelectedText()
        edit.endEditBlock()
        self._clear_rect_selection()

    def _rect_paste_from_clipboard(self):
        if not (self._rect_active and self._rect_anchor and self._rect_cursor):
            return
        text = QGuiApplication.clipboard().text()
        lines = text.split("\n")
        top, _, left, _, _ = self._rect_ranges()
        doc = self.document()

        edit = QTextCursor(doc)
        edit.beginEditBlock()

        # гарантируем наличие нужного числа блоков
        last_block_num = doc.blockCount() - 1
        need_last = top + len(lines) - 1
        while last_block_num < need_last:
            cur = QTextCursor(doc)
            cur.movePosition(QTextCursor.End)
            cur.insertBlock()
            last_block_num += 1

        for idx, line in enumerate(lines):
            bn = top + idx
            block = doc.findBlockByNumber(bn)
            btxt = block.text()

            # позиция вставки по видимой колонке
            pos = self._pos_from_visible_column(btxt, left)
            cur = QTextCursor(doc)
            cur.setPosition(block.position() + pos)

            # добиваем пробелами до нужной видимой колонки
            cur_vcol = self._visible_column_of(btxt, pos)
            if cur_vcol < left:
                cur.insertText(" " * (left - cur_vcol))
            cur.insertText(line)

        edit.endEditBlock()
        self._clear_rect_selection()

    # ───────────  visible column helpers (tabs-aware)  ───────────
    def _visible_column_of(self, text: str, pos: int) -> int:
        # pos — индекс символа в строке
        col = 0
        for i, ch in enumerate(text[:pos]):
            if ch == "\t":
                step = self.TAB_SPACES - (col % self.TAB_SPACES)
                col += step
            else:
                col += 1
        return col

    def _pos_from_visible_column(self, text: str, vcol: int) -> int:
        col = 0
        for i, ch in enumerate(text):
            if col >= vcol:
                return i
            if ch == "\t":
                step = self.TAB_SPACES - (col % self.TAB_SPACES)
                col += step
            else:
                col += 1
            if col > vcol:
                # ставим за символ, который "перешагнул" колонку
                return i + 1
        return len(text)