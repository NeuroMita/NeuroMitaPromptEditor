import os
import re
from PySide6.QtCore import QRegularExpression, QUrl
from PySide6.QtGui import (
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextFormat,
    QColor,
)

from app.syntax.styles import HIGHLIGHTING_RULES_DARK_TUPLES
from app.utils.logger import editor_logger


class PromptSyntaxHighlighter(QSyntaxHighlighter):
    """
    Подсветка DSL-файлов + гиперссылки на placeholders.
    Теперь умеет раскрашивать многострочные строки \"\"\" … \"\"\".
    """

    # Property-id, в котором будем хранить QUrl (для кликабельных ссылок)
    LinkPathPropertyId = QTextFormat.UserProperty + 1

    # ключевые слова DSL, которые должны подсвечиваться без учёта регистра
    _DSL_KEYWORDS_RE = re.compile(
        r"\\b(IF|THEN|ELSEIF|ELSE|ENDIF|SET|RETURN|LOAD|LOG|AND|OR|TRUE|FALSE|NONE)\\b",
        re.IGNORECASE,
    )

    TRIPLE_QUOTE = '"""'          # маркер начала/конца многострочной строки

    # ───────────────────────────────────────────────────────
    #                         CTOR
    # ───────────────────────────────────────────────────────
    def __init__(
        self,
        parent=None,
        current_doc_path_resolver=None,
        prompts_root_resolver=None,
        hyperlink_resolver=None,
    ):
        super().__init__(parent)

        self.current_doc_path_resolver = current_doc_path_resolver
        self.prompts_root_resolver = prompts_root_resolver
        self.hyperlink_resolver = hyperlink_resolver

        # ----------- загружаем правила подписи -------------
        self.rules: list[
            tuple[QRegularExpression, QTextCharFormat, bool, str]
        ] = []

        self._triple_quote_format: QTextCharFormat | None = None

        for pattern_str, fmt, is_link_rule in HIGHLIGHTING_RULES_DARK_TUPLES:
            # сохраняем формат, который пригодится для \"\"\" … \"\"\" строк
            if ('"' in pattern_str or "'" in pattern_str) and self._triple_quote_format is None:
                self._triple_quote_format = QTextCharFormat(fmt)  # copy

            opts = QRegularExpression.NoPatternOption
            if self._DSL_KEYWORDS_RE.search(pattern_str):
                opts |= QRegularExpression.CaseInsensitiveOption

            regex = QRegularExpression(pattern_str)
            if opts:
                regex.setPatternOptions(opts)

            self.rules.append((regex, fmt, is_link_rule, pattern_str))

        # если среди правил не нашёлся string-format ‒ создаём дефолтный
        if self._triple_quote_format is None:
            self._triple_quote_format = QTextCharFormat()
            self._triple_quote_format.setForeground(QColor("#FFA500"))  # оранжевый

    # ───────────────────────────────────────────────────────
    #                    ВСПОМОГАТ. МЕТОД
    # ───────────────────────────────────────────────────────
    def _apply_multiline_string_highlighting(self, text: str):
        """
        Подсвечивает \"\"\" … \"\"\" , правильно обрабатывая
        переход на следующий блок.
        """
        fmt = self._triple_quote_format
        triple = self.TRIPLE_QUOTE

        self.setCurrentBlockState(0)
        start_idx = 0

        # Если предыдущий блок “внутри\"\"\"”
        if self.previousBlockState() == 1:
            end_idx = text.find(triple)
            if end_idx == -1:
                # Весь блок принадлежит строке
                self.setFormat(0, len(text), fmt)
                self.setCurrentBlockState(1)
                return
            # Закрываем многострочную строку
            end_idx += len(triple)
            self.setFormat(0, end_idx, fmt)
            start_idx = end_idx

        # Ищем все последующие \"\"\" … \"\"\" на текущем блоке
        while True:
            start_quote = text.find(triple, start_idx)
            if start_quote == -1:
                break

            end_quote = text.find(triple, start_quote + len(triple))
            if end_quote == -1:
                # Не найдено закрытие ‒ до конца блока плюс сохраняем state
                self.setFormat(start_quote, len(text) - start_quote, fmt)
                self.setCurrentBlockState(1)
                break
            else:
                end_quote += len(triple)
                self.setFormat(start_quote, end_quote - start_quote, fmt)
                start_idx = end_quote

    # ───────────────────────────────────────────────────────
    #                     highlightBlock
    # ───────────────────────────────────────────────────────
    def highlightBlock(self, text: str):
        # 1) обычные правила + гиперссылки
        current_doc_path = (
            self.current_doc_path_resolver()
            if self.current_doc_path_resolver
            else None
        )
        prompts_root_path = (
            self.prompts_root_resolver()
            if self.prompts_root_resolver
            else None
        )

        for regex, base_fmt, is_link_rule, pattern_dbg in self.rules:
            it = regex.globalMatch(text)
            while it.hasNext():
                match = it.next()
                start = match.capturedStart()
                length = match.capturedLength()

                # копируем формат
                try:
                    applied_fmt = QTextCharFormat(base_fmt)
                except TypeError:
                    applied_fmt = QTextCharFormat()
                    applied_fmt.merge(base_fmt)

                # ----- гиперссылки на placeholders -----
                if is_link_rule and self.hyperlink_resolver:
                    rel_path = ""
                    if match.lastCapturedIndex() >= 2 and match.captured(2):
                        rel_path = match.captured(2)
                    elif match.lastCapturedIndex() >= 1 and match.captured(1):
                        rel_path = match.captured(1)
                    if not rel_path:
                        m = re.search(r"<([^>]+)>", match.captured(0))
                        if m:
                            rel_path = m.group(1)

                    if rel_path and current_doc_path and prompts_root_path:
                        target = self.hyperlink_resolver(
                            prompts_root_path,
                            current_doc_path,
                            rel_path,
                        )
                        if target and os.path.exists(target):
                            applied_fmt.setProperty(
                                self.LinkPathPropertyId,
                                QUrl.fromLocalFile(target),
                            )

                self.setFormat(start, length, applied_fmt)

        # 2) поверх всего наносим подсветку многострочных \"\"\" … \"\"\" строк
        self._apply_multiline_string_highlighting(text)