"""
widgets/post_dsl_rule_list.py

Визуальный список PostScript-правил с кнопками Add/Edit/Delete.
Читает и записывает .postscript файлы через logic/post_dsl_engine.py.

Использование как центрального виджета при открытии .postscript файла.
Можно переключаться между визуальным видом и кодовым редактором.
"""
from __future__ import annotations

import os
from typing import Optional, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QFrame,
    QMessageBox, QTextEdit, QTabWidget, QSizePolicy,
)

from logic.post_dsl_engine import parse_postscript, PostDslRule
from widgets.post_dsl_rule_widget import PostScriptRuleDialog, RuleSpec


# --------------------------------------------------------------------------- #
#  Карточка одного правила                                                     #
# --------------------------------------------------------------------------- #

class _RuleCard(QFrame):
    """Карточка правила в списке."""

    edit_requested   = Signal(int)   # index
    delete_requested = Signal(int)   # index
    move_up          = Signal(int)
    move_down        = Signal(int)

    def __init__(self, index: int, spec: RuleSpec, parent=None):
        super().__init__(parent)
        self._index = index
        self._spec = spec
        self._build(spec)
        self.setStyleSheet("""
            QFrame {
                background: #1c2128;
                border: 1px solid #30363d;
                border-radius: 6px;
            }
            QFrame:hover { border-color: #4a9eff; }
        """)

    def _build(self, spec: RuleSpec):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 8, 8)
        lay.setSpacing(8)

        # Иконка типа
        icon = "🔍" if spec.match_type == "REGEX" else "📝"
        ico_lbl = QLabel(icon)
        ico_lbl.setStyleSheet("font-size: 18px; background: transparent;")
        lay.addWidget(ico_lbl)

        # Описание правила
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        name_lbl = QLabel(spec.name)
        name_lbl.setStyleSheet("font-weight: bold; color: #e6edf3; font-size: 12px; background: transparent;")
        info_col.addWidget(name_lbl)

        pattern_short = spec.pattern[:60] + ("…" if len(spec.pattern) > 60 else "")
        pat_lbl = QLabel(f"{spec.match_type}: {pattern_short}")
        pat_lbl.setStyleSheet("color: #8b949e; font-size: 10px; font-family: Consolas; background: transparent;")
        info_col.addWidget(pat_lbl)

        # Сводка действий
        actions_summary = []
        if spec.actions:
            actions_summary.append(f"{len(spec.actions)} действ.")
        if spec.remove_match:
            actions_summary.append("REMOVE")
        if spec.replace_with:
            actions_summary.append("REPLACE")
        if spec.captures:
            actions_summary.append(f"CAPTURE({', '.join(spec.captures)})")
        if actions_summary:
            act_lbl = QLabel(" · ".join(actions_summary))
            act_lbl.setStyleSheet("color: #7ed4a5; font-size: 9px; background: transparent;")
            info_col.addWidget(act_lbl)

        lay.addLayout(info_col, 1)

        # Кнопки управления
        btn_col = QVBoxLayout()
        btn_col.setSpacing(2)

        btn_edit = QPushButton("✏")
        btn_edit.setFixedSize(28, 28)
        btn_edit.setToolTip("Редактировать правило")
        btn_edit.setStyleSheet(_ICON_BTN)
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(self._index))
        btn_col.addWidget(btn_edit)

        btn_del = QPushButton("🗑")
        btn_del.setFixedSize(28, 28)
        btn_del.setToolTip("Удалить правило")
        btn_del.setStyleSheet(_ICON_BTN)
        btn_del.clicked.connect(self._on_delete)
        btn_col.addWidget(btn_del)

        lay.addLayout(btn_col)

        arrows = QVBoxLayout()
        arrows.setSpacing(2)
        btn_up = QPushButton("▲")
        btn_up.setFixedSize(22, 22)
        btn_up.setStyleSheet(_ICON_BTN)
        btn_up.clicked.connect(lambda: self.move_up.emit(self._index))
        arrows.addWidget(btn_up)
        btn_dn = QPushButton("▼")
        btn_dn.setFixedSize(22, 22)
        btn_dn.setStyleSheet(_ICON_BTN)
        btn_dn.clicked.connect(lambda: self.move_down.emit(self._index))
        arrows.addWidget(btn_dn)
        lay.addLayout(arrows)

    def _on_delete(self):
        if QMessageBox.question(
            self, "Удалить правило",
            f"Удалить правило «{self._spec.name}»?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) == QMessageBox.Yes:
            self.delete_requested.emit(self._index)


# --------------------------------------------------------------------------- #
#  Основной виджет                                                             #
# --------------------------------------------------------------------------- #

class PostScriptRuleList(QWidget):
    """
    Визуальный редактор PostScript-файла.

    Содержит:
    - Вкладку «Правила» (список карточек)
    - Вкладку «Код» (сырой текстовый редактор для продвинутых)

    Сигналы:
        content_changed() — контент изменился (для отслеживания несохранённых изменений)
    """

    content_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path: Optional[str] = None
        self._specs: list[RuleSpec] = []
        self._building = False
        self._build_ui()

    # -- публичный API -------------------------------------------------------

    def load_file(self, path: str):
        """Загружает .postscript файл."""
        self._file_path = path
        try:
            text = open(path, encoding="utf-8").read()
        except Exception as e:
            text = ""
        self._load_text(text)

    def get_text(self) -> str:
        """Возвращает текущий .postscript текст (из активной вкладки)."""
        if self._tabs.currentIndex() == 1:  # Код
            return self._code_editor.toPlainText()
        return self._specs_to_text()

    def save(self):
        """Сохраняет файл."""
        if not self._file_path:
            return
        text = self.get_text()
        with open(self._file_path, "w", encoding="utf-8") as f:
            f.write(text)

    # -- UI ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Тулбар
        toolbar = QFrame()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet("QFrame { background: #161b22; border-bottom: 1px solid #30363d; }")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(10, 6, 10, 6)
        tb.setSpacing(8)

        self._title_lbl = QLabel("PostScript правила")
        self._title_lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
        tb.addWidget(self._title_lbl)
        tb.addStretch()

        btn_add = QPushButton("+ Добавить правило")
        btn_add.setStyleSheet(_TOOLBAR_BTN)
        btn_add.clicked.connect(self._on_add)
        tb.addWidget(btn_add)

        outer.addWidget(toolbar)

        # Вкладки: Правила / Код
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setStyleSheet("""
            QTabBar::tab { padding: 5px 14px; }
            QTabBar::tab:selected { border-bottom: 2px solid #4a9eff; }
        """)
        self._tabs.currentChanged.connect(self._on_tab_switched)

        # --- Вкладка "Правила" ---
        rules_page = QWidget()
        rules_lay = QVBoxLayout(rules_page)
        rules_lay.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #0d1117; }")

        self._cards_widget = QWidget()
        self._cards_widget.setStyleSheet("background: #0d1117;")
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(12, 12, 12, 12)
        self._cards_layout.setSpacing(8)
        self._cards_layout.setAlignment(Qt.AlignTop)

        scroll.setWidget(self._cards_widget)
        rules_lay.addWidget(scroll, 1)
        self._tabs.addTab(rules_page, "⚙ Правила")

        # --- Вкладка "Код" ---
        self._code_editor = QTextEdit()
        self._code_editor.setFont(QFont("Consolas", 10))
        self._code_editor.setStyleSheet("""
            QTextEdit {
                background: #1f2329; color: #e6edf3;
                border: none;
            }
        """)
        self._code_editor.textChanged.connect(self._on_code_changed)
        self._tabs.addTab(self._code_editor, "< > Код")

        outer.addWidget(self._tabs, 1)

    def _rebuild_cards(self):
        """Перестраивает список карточек из self._specs."""
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._specs:
            hint = QLabel("Правил нет. Нажмите «+ Добавить правило».")
            hint.setStyleSheet("color: #6e7681; font-style: italic;")
            hint.setAlignment(Qt.AlignCenter)
            self._cards_layout.addWidget(hint)
            return

        for i, spec in enumerate(self._specs):
            card = _RuleCard(i, spec)
            card.edit_requested.connect(self._on_edit)
            card.delete_requested.connect(self._on_delete)
            card.move_up.connect(self._on_move_up)
            card.move_down.connect(self._on_move_down)
            self._cards_layout.addWidget(card)

        name = os.path.basename(self._file_path) if self._file_path else "PostScript"
        self._title_lbl.setText(f"{name}  ({len(self._specs)} правил)")

    # -- загрузка/сохранение -------------------------------------------------

    def _load_text(self, text: str):
        self._building = True
        try:
            rules, _ = parse_postscript(text)
            self._specs = [RuleSpec.from_engine_rule(r) for r in rules]
            self._rebuild_cards()
            # Синхронизируем код-вкладку
            self._code_editor.blockSignals(True)
            self._code_editor.setPlainText(text)
            self._code_editor.blockSignals(False)
        finally:
            self._building = False

    def _specs_to_text(self) -> str:
        parts = [spec.to_postscript() for spec in self._specs]
        return "\n\n".join(parts)

    # -- обработчики ---------------------------------------------------------

    def _on_add(self):
        dlg = PostScriptRuleDialog(parent=self)
        if dlg.exec() == PostScriptRuleDialog.Accepted:
            self._specs.append(dlg.get_spec())
            self._rebuild_cards()
            self._sync_code_from_specs()
            self.content_changed.emit()

    def _on_edit(self, index: int):
        if 0 <= index < len(self._specs):
            dlg = PostScriptRuleDialog(self._specs[index], parent=self)
            if dlg.exec() == PostScriptRuleDialog.Accepted:
                self._specs[index] = dlg.get_spec()
                self._rebuild_cards()
                self._sync_code_from_specs()
                self.content_changed.emit()

    def _on_delete(self, index: int):
        if 0 <= index < len(self._specs):
            del self._specs[index]
            self._rebuild_cards()
            self._sync_code_from_specs()
            self.content_changed.emit()

    def _on_move_up(self, index: int):
        if index > 0:
            self._specs[index], self._specs[index - 1] = self._specs[index - 1], self._specs[index]
            self._rebuild_cards()
            self._sync_code_from_specs()
            self.content_changed.emit()

    def _on_move_down(self, index: int):
        if index < len(self._specs) - 1:
            self._specs[index], self._specs[index + 1] = self._specs[index + 1], self._specs[index]
            self._rebuild_cards()
            self._sync_code_from_specs()
            self.content_changed.emit()

    def _on_tab_switched(self, idx: int):
        if idx == 0 and not self._building:
            # Переключились на Правила → синхронизируем из кода
            self._load_text(self._code_editor.toPlainText())
        elif idx == 1 and not self._building:
            # Переключились на Код → синхронизируем из правил
            self._sync_code_from_specs()

    def _sync_code_from_specs(self):
        self._building = True
        self._code_editor.blockSignals(True)
        self._code_editor.setPlainText(self._specs_to_text())
        self._code_editor.blockSignals(False)
        self._building = False

    def _on_code_changed(self):
        if not self._building:
            self.content_changed.emit()


# --------------------------------------------------------------------------- #
_TOOLBAR_BTN = """
    QPushButton {
        background: #1f6feb; color: #ffffff;
        border: none; border-radius: 5px;
        padding: 4px 14px; font-size: 11px;
    }
    QPushButton:hover { background: #388bfd; }
    QPushButton:pressed { background: #1158c7; }
"""

_ICON_BTN = """
    QPushButton {
        background: #21262d; color: #8b949e;
        border: 1px solid #30363d; border-radius: 4px;
    }
    QPushButton:hover { background: #30363d; color: #e6edf3; }
    QPushButton:pressed { background: #1f6feb; color: #fff; }
"""
