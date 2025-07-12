import os
import re
from PySide6.QtCore import QRegularExpression, QUrl
from PySide6.QtGui import (
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextFormat,
    QColor,
    QFont,
)

from syntax.styles import HIGHLIGHTING_RULES_DARK_TUPLES, SyntaxStyleDark
from utils.logger import editor_logger


class PromptSyntaxHighlighter(QSyntaxHighlighter):
    """
    Подсветка DSL-файлов + гиперссылки на placeholders.
    Теперь умеет:
        • раскрашивать многострочные строки \"\"\" … \"\"\"
        • распознавать команду:   LOAD <TAG> FROM "file.txt"
        • НЕ подсвечивать DSL-ключевые слова в обычных .txt-файлах
    """

    # Property-id, в котором будем хранить QUrl (для кликабельных ссылок)
    LinkPathPropertyId = QTextFormat.UserProperty + 1

    # ключевые слова DSL, которые должны подсвечиваться без учёта регистра
    _DSL_KEYWORDS_RE = re.compile(
        r"\b(IF|THEN|ELSEIF|ELSE|ENDIF|SET|RETURN|LOAD|LOG|AND|OR|TRUE|FALSE|NONE|LOCAL)\b",
        re.IGNORECASE,
    )

    TRIPLE_QUOTE = '"""'   # маркер начала/конца многострочной строки

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
        self.prompts_root_resolver     = prompts_root_resolver
        self.hyperlink_resolver        = hyperlink_resolver

        # ---------- загружаем правила подсветки ----------
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

        # ────────────────────────────────────────────────────────
        #      ДОБАВЛЯЕМ 2 НОВЫХ ПРАВИЛА ПОДСВЕТКИ
        # ────────────────────────────────────────────────────────

        # 1) LOAD <TAG> FROM "file.txt"
        load_tag_fmt = QTextCharFormat()
        load_tag_fmt.setForeground(QColor("#569CD6"))         # синий
        load_tag_fmt.setFontWeight(QFont.Bold)

        load_tag_regex = QRegularExpression(
            r"\bLOAD\s+[A-Z0-9_]+\s+FROM\s+['\"][^'\"]+['\"]",
            QRegularExpression.CaseInsensitiveOption,
        )
        self.rules.append((load_tag_regex, load_tag_fmt, False, "LOAD TAG FROM"))

        # 2) Маркеры секций тегов  [#TAG]  [/TAG]
        section_fmt = QTextCharFormat()
        section_fmt.setForeground(QColor("#C586C0"))          # сиреневый
        section_fmt.setFontWeight(QFont.Bold)

        section_regex = QRegularExpression(
            r"\[(?:#|/)\s*[A-Z0-9_]+\s*]",
            QRegularExpression.CaseInsensitiveOption,
        )
        self.rules.append((section_regex, section_fmt, False, "[#TAG]/[/TAG]"))

        # ────────────────────────────────────────────────────────
        #          {{INSERTS}} (бывшие {{TAGS}})
        # ────────────────────────────────────────────────────────
        tag_fmt = QTextCharFormat()
        tag_fmt.setForeground(QColor("#FFAC33"))              # ярко-оранжевый
        tag_fmt.setFontWeight(QFont.Bold)

        tag_regex = QRegularExpression(r"\{\{[A-Z0-9_]+\}\}")
        self.rules.append((tag_regex, tag_fmt, False, "{{TAG}}"))

        # --- дефолтный цвет для \"\"\"…\"\"\" (если не найден выше) ----
        if self._triple_quote_format is None:
            self._triple_quote_format = QTextCharFormat()
            self._triple_quote_format.setForeground(QColor("#FFA500"))  # оранж.

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
        # --------- определяем тип файла (.script / .txt) ---------------
        current_doc_path = (
            self.current_doc_path_resolver()
            if self.current_doc_path_resolver
            else None
        )
        is_txt_file = (
            current_doc_path is not None
            and current_doc_path.lower().endswith(".txt")
        )

        prompts_root_path = (
            self.prompts_root_resolver()
            if self.prompts_root_resolver
            else None
        )

        is_postscript_file = current_doc_path is not None and current_doc_path.lower().endswith(".postscript")

        if is_postscript_file:
            if not hasattr(self, 'postscript_rules'):
                self.highlight_postscript()
            rules_to_apply = self.postscript_rules
        else:
            rules_to_apply = self.rules

        # --------- применяем все правила -------------------------------
        for regex, base_fmt, is_link_rule, pattern_dbg in rules_to_apply:
            #  ❗️Отключаем DSL-ключевые слова внутри .txt-файла
            if is_txt_file and self._DSL_KEYWORDS_RE.search(regex.pattern()):
                continue

            it = regex.globalMatch(text)
            while it.hasNext():
                match  = it.next()
                start  = match.capturedStart()
                length = match.capturedLength()

                # копируем формат (иначе PySide иногда даёт shared-ссылку)
                try:
                    applied_fmt = QTextCharFormat(base_fmt)
                except TypeError:
                    applied_fmt = QTextCharFormat()
                    applied_fmt.merge(base_fmt)

                # ---------- гиперссылки на placeholders ----------------
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

        # --------- поверх всего — раскраска \"\"\" … \"\"\" -------------
        self._apply_multiline_string_highlighting(text)


    def highlight_postscript(self):
        # In PromptSyntaxHighlighter constructor or a new method for postscript rules
        self.postscript_rules = []
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(SyntaxStyleDark.Keyword["foreground"])  # Assuming Keyword style exists
        string_format = QTextCharFormat()
        string_format.setForeground(SyntaxStyleDark.String["foreground"])
        comment_format = QTextCharFormat()
        comment_format.setForeground(SyntaxStyleDark.Comment["foreground"])

        # Postscript Keywords
        postscript_keywords = r"\b(RULE|MATCH|TEXT|REGEX|CAPTURE|AS|ACTIONS|END_ACTIONS|END_RULE|SET|LOG|REMOVE_MATCH|REPLACE_MATCH|WITH|FLOAT|INT|STR|DEFAULT|LOCAL)\b"
        self.postscript_rules.append(
            (QRegularExpression(postscript_keywords, QRegularExpression.CaseInsensitiveOption), keyword_format, False, "Postscript Keywords"))

        # Strings
        self.postscript_rules.append((QRegularExpression(r"(\".*?\"|\'.*?\')"), string_format, False, "Strings"))

        # Comments
        self.postscript_rules.append((QRegularExpression(r"//[^\n]*"), comment_format, False, "Comments"))

        # Variable names (simple example)
        # self.postscript_rules.append((QRegularExpression(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b"), default_text_format)) # If needed
