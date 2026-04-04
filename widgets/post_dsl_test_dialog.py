# widgets/post_dsl_test_dialog.py
"""
Диалог тестирования PostDSL-скрипта.
Принимает текст .postscript и словарь переменных из vars_dock.
Показывает: изменённый текст, переменные до/после, лог правил.
"""
from __future__ import annotations

from typing import Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QPlainTextEdit, QTabWidget,
    QWidget, QTableWidget, QTableWidgetItem, QListWidget,
    QListWidgetItem, QDialogButtonBox, QSizePolicy,
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt

from syntax.styles import SyntaxStyleDark


_MONO = QFont("Consolas", 10)

_STYLE_EDIT = f"""
    QPlainTextEdit {{
        background-color: {SyntaxStyleDark.TextEditBackground.name()};
        color: {SyntaxStyleDark.DefaultText.name()};
        border: 1px solid #3C3F41;
    }}
"""

_STYLE_TABLE = f"""
    QTableWidget {{
        background-color: {SyntaxStyleDark.TextEditBackground.name()};
        color: {SyntaxStyleDark.DefaultText.name()};
        gridline-color: #3C3F41;
        border: 1px solid #3C3F41;
    }}
    QHeaderView::section {{
        background-color: #2B2B2B;
        color: #BBBBBB;
        padding: 4px;
        border: none;
    }}
"""

_STYLE_LIST = f"""
    QListWidget {{
        background-color: {SyntaxStyleDark.TextEditBackground.name()};
        color: {SyntaxStyleDark.DefaultText.name()};
        border: 1px solid #3C3F41;
    }}
"""


class PostDslTestDialog(QDialog):
    """
    Диалог тестирования PostDSL.

    Параметры:
        script_text  — содержимое .postscript файла
        variables    — словарь переменных (из vars_dock)
        parent       — родительское окно
    """

    def __init__(
        self,
        script_text: str,
        variables: Dict[str, Any],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Тест PostDSL")
        self.setMinimumSize(900, 580)
        self.setModal(False)

        self._script_text = script_text
        self._init_variables = dict(variables)

        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Верхняя метка ──────────────────────────────────────────
        hint = QLabel(
            "Введите пробный LLM-ответ и нажмите «Применить правила ▶» "
            "чтобы увидеть результат PostDSL-обработки."
        )
        hint.setStyleSheet("color: #AAAAAA;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # ── Главный разделитель (ввод | вывод) ─────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)
        root.addWidget(splitter, 1)

        # ── Левая панель: ввод ──────────────────────────────────────
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(4)

        left_lay.addWidget(QLabel("Пробный LLM-ответ:"))
        self._input_edit = QPlainTextEdit()
        self._input_edit.setFont(_MONO)
        self._input_edit.setStyleSheet(_STYLE_EDIT)
        self._input_edit.setPlaceholderText(
            "Вставьте сюда текст ответа LLM…\n\nНапример:\n*Мита улыбается* Привет! [EMOTION:happy]"
        )
        left_lay.addWidget(self._input_edit, 1)

        self._run_btn = QPushButton("Применить правила ▶")
        self._run_btn.setFixedHeight(32)
        self._run_btn.clicked.connect(self._run)
        left_lay.addWidget(self._run_btn)

        splitter.addWidget(left)

        # ── Правая панель: вкладки результатов ─────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        # Вкладка 1: Результат
        self._result_edit = QPlainTextEdit()
        self._result_edit.setReadOnly(True)
        self._result_edit.setFont(_MONO)
        self._result_edit.setStyleSheet(_STYLE_EDIT)
        self._result_edit.setPlaceholderText("Здесь появится изменённый текст…")
        self._tabs.addTab(self._result_edit, "Результат")

        # Вкладка 2: Переменные
        self._vars_table = QTableWidget()
        self._vars_table.setColumnCount(3)
        self._vars_table.setHorizontalHeaderLabels(["Переменная", "До", "После"])
        self._vars_table.horizontalHeader().setStretchLastSection(True)
        self._vars_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._vars_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._vars_table.setStyleSheet(_STYLE_TABLE)
        self._tabs.addTab(self._vars_table, "Переменные")

        # Вкладка 3: Лог правил
        self._log_list = QListWidget()
        self._log_list.setFont(_MONO)
        self._log_list.setStyleSheet(_STYLE_LIST)
        self._tabs.addTab(self._log_list, "Лог правил")

        splitter.addWidget(self._tabs)
        splitter.setSizes([380, 480])

        # ── Кнопки закрытия ────────────────────────────────────────
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    # ────────────────────────────────────────────────────────────────
    def _run(self):
        from logic.post_dsl_engine import PostDslRunner

        response_text = self._input_edit.toPlainText()

        runner = PostDslRunner(self._script_text, self._init_variables)
        vars_before = dict(self._init_variables)

        try:
            result = runner.process(response_text)
        except Exception as e:
            result = f"[ОШИБКА] {e}"

        vars_after = dict(runner.variables)

        # Результат
        self._result_edit.setPlainText(result)

        # Переменные
        self._populate_vars_table(vars_before, vars_after)

        # Лог
        self._log_list.clear()
        for entry in runner.rule_log:
            item = QListWidgetItem(entry)
            if entry.startswith("✅"):
                item.setForeground(QColor("#98C379"))  # зелёный
            elif entry.startswith("○"):
                item.setForeground(QColor("#5C6370"))  # серый
            elif "[LOG" in entry:
                item.setForeground(QColor("#61AFEF"))  # синий
            self._log_list.addItem(item)

        # Переключаем на «Результат» при первом запуске
        self._tabs.setCurrentIndex(0)

    def _populate_vars_table(
        self, before: Dict[str, Any], after: Dict[str, Any]
    ):
        all_keys = sorted(set(before) | set(after))
        self._vars_table.setRowCount(len(all_keys))

        for row, key in enumerate(all_keys):
            val_before = before.get(key)
            val_after = after.get(key)

            key_item = QTableWidgetItem(key)
            key_item.setFont(_MONO)
            before_item = QTableWidgetItem(repr(val_before))
            after_item = QTableWidgetItem(repr(val_after))

            changed = val_before != val_after
            is_new = key not in before

            if is_new:
                for it in (key_item, after_item):
                    it.setForeground(QColor("#98C379"))  # зелёный — новая
            elif changed:
                after_item.setForeground(QColor("#61AFEF"))  # синий — изменилась

            self._vars_table.setItem(row, 0, key_item)
            self._vars_table.setItem(row, 1, before_item)
            self._vars_table.setItem(row, 2, after_item)

        self._vars_table.resizeColumnToContents(0)
        self._vars_table.resizeColumnToContents(1)
