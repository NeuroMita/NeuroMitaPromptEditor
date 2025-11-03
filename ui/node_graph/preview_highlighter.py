# ui/node_graph/preview_highlighter.py
from __future__ import annotations
from typing import List, Tuple
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat
from PySide6.QtCore import QRegularExpression
from syntax.styles import HIGHLIGHTING_RULES_DARK_TUPLES

class SimplePromptHighlighter(QSyntaxHighlighter):
    def __init__(self, doc):
        super().__init__(doc)
        self._rules: List[Tuple[QRegularExpression, QTextCharFormat]] = []
        for pattern, fmt, _flag in HIGHLIGHTING_RULES_DARK_TUPLES:
            self._rules.append((QRegularExpression(pattern), fmt))

    def highlightBlock(self, text: str):
        for rx, fmt in self._rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)