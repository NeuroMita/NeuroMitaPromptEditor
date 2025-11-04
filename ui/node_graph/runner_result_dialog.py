# File: ui/node_graph/runner_result_dialog.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QListWidget,
    QListWidgetItem, QDialogButtonBox, QWidget, QSplitter, QPushButton,
    QTabWidget, QTreeWidget, QTreeWidgetItem, QLineEdit, QFileDialog, QMessageBox
)

from ui.node_graph.preview_highlighter import SimplePromptHighlighter


class RunnerResultDialog(QDialog):
    """
    Диалог результата выполнения воркфлоу (узлового .script):
    - Вкладки: Обзор, Итоговый текст, Шаги выполнения, Системные, Логи, Переменные.
    - Переменные: отдельные табы 'До', 'После' и 'Изменения' (таблица с подсветкой).
    - Шаги: список слева, подробности справа понятным языком.
    """
    def __init__(self,
                 title: str,
                 final_text: str,
                 sys_infos: List[str],
                 logs: List[str],
                 vars_before: Dict[str, Any],
                 vars_after: Dict[str, Any],
                 steps: Optional[List[Dict[str, Any]]] = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(1120, 760)
        self.setModal(False)

        self._final_text = final_text or ""
        self._sys_infos = sys_infos or []
        self._logs = logs or []
        self._vars_before = vars_before or {}
        self._vars_after = vars_after or {}
        self._steps = steps or []

        root = QVBoxLayout(self)
        root.setSpacing(8)

        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.North)

        # 1) Обзор
        tabs.addTab(self._build_overview_tab(), "Обзор")

        # 2) Итоговый текст
        tabs.addTab(self._build_final_text_tab(), "Итоговый текст")

        # 3) Шаги выполнения
        tabs.addTab(self._build_steps_tab(), "Шаги выполнения")

        # 4) Системные сообщения
        tabs.addTab(self._build_sys_tab(), "Системные")

        # 5) Логи
        tabs.addTab(self._build_logs_tab(), "Логи")

        # 6) Переменные (внутри — свои вкладки: До/После/Изменения)
        tabs.addTab(self._build_vars_tab(), "Переменные")

        root.addWidget(tabs)

        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        root.addWidget(btns)

        # выбрать первый шаг по умолчанию
        try:
            if hasattr(self, "_steps_list") and self._steps_list.count() > 0:
                self._steps_list.setCurrentRow(0)
        except Exception:
            pass

    # ---------- Tab: Обзор ----------
    def _build_overview_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        # Сводка по выполнению
        total_steps = len(self._steps)
        err_count = sum(1 for s in self._steps if s.get("error"))
        chosen_if = sum(1 for s in self._steps if (s.get("type") == "IF" and s.get("branch")))
        summary = QLabel(
            f"Итог: получен текст длиной {len(self._final_text)} символов.\n"
            f"Выполнено шагов: {total_steps}, выбрано IF-веток: {chosen_if}, ошибок: {err_count}.\n"
            f"Системных сообщений: {len(self._sys_infos)}, записей в лог: {len(self._logs)}."
        )
        summary.setWordWrap(True)
        lay.addWidget(summary)

        # Кратко — изменения переменных (строкой)
        delta_lines, changed_cnt, new_cnt = self._format_delta_lines(self._vars_before, self._vars_after)
        lbl = QLabel(f"Изменения переменных: изменено {changed_cnt}, новых {new_cnt}.")
        lay.addWidget(lbl)

        if delta_lines:
            preview = QPlainTextEdit()
            preview.setReadOnly(True)
            preview.setFont(QFont("Consolas", 9))
            preview.setPlainText("\n".join(delta_lines[:40] + (["…"] if len(delta_lines) > 40 else [])))
            lay.addWidget(preview, 1)

        return w

    # ---------- Tab: Итоговый текст ----------
    def _build_final_text_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        row = QHBoxLayout()
        self.len_lbl = QLabel(f"Длина: {len(self._final_text)} символов")
        btn_copy = QPushButton("Копировать")
        btn_copy.clicked.connect(lambda: self._copy_text(self._final_text))
        btn_save = QPushButton("Сохранить…")
        btn_save.clicked.connect(lambda: self._save_text(self._final_text))
        row.addWidget(self.len_lbl)
        row.addStretch(1)
        row.addWidget(btn_copy)
        row.addWidget(btn_save)
        lay.addLayout(row)

        self.final_text_edit = QPlainTextEdit()
        self.final_text_edit.setReadOnly(True)
        self.final_text_edit.setFont(QFont("Consolas", 10))
        self.final_text_edit.setPlainText(self._final_text)
        SimplePromptHighlighter(self.final_text_edit.document())
        lay.addWidget(self.final_text_edit, 1)

        return w

    # ---------- Tab: Шаги выполнения ----------
    def _build_steps_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Маршрут выполнения (слева) и подробности шага (справа):"))

        split = QSplitter(Qt.Horizontal)

        # Список шагов
        left = QWidget()
        l_lay = QVBoxLayout(left)
        self._steps_filter = QLineEdit()
        self._steps_filter.setPlaceholderText("Фильтр по тексту/типу/ветке…")
        self._steps_filter.textChanged.connect(self._refilter_steps)
        l_lay.addWidget(self._steps_filter)

        self._steps_list = QListWidget()
        self._populate_steps_list()  # заполнение
        self._steps_list.currentItemChanged.connect(self._on_step_selected)
        l_lay.addWidget(self._steps_list, 1)

        split.addWidget(left)

        # Подробности
        right = QWidget()
        r_lay = QVBoxLayout(right)
        self.step_details = QPlainTextEdit()
        self.step_details.setReadOnly(True)
        self.step_details.setFont(QFont("Consolas", 9))
        r_lay.addWidget(self.step_details, 1)
        split.addWidget(right)

        lay.addWidget(split, 1)
        return w

    def _populate_steps_list(self):
        self._steps_list.clear()
        for st in self._steps:
            label = self._format_step_label(st)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, st)
            if st.get("error"):
                item.setForeground(QColor("#E57373"))
            self._steps_list.addItem(item)

    def _refilter_steps(self, text: str):
        t = (text or "").strip().lower()
        self._steps_list.clear()
        for st in self._steps:
            label = self._format_step_label(st)
            if not t or t in label.lower():
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, st)
                if st.get("error"):
                    item.setForeground(QColor("#E57373"))
                self._steps_list.addItem(item)
        if self._steps_list.count() > 0:
            self._steps_list.setCurrentRow(0)
        else:
            self.step_details.setPlainText("Нет шагов по текущему фильтру.")

    def _format_step_label(self, st: Dict[str, Any]) -> str:
        ln = st.get("line")
        tp = st.get("type") or ""
        title = st.get("title") or ""
        err = " [ОШИБКА]" if st.get("error") else ""
        br = f"  → {st.get('branch')}" if st.get("type") == "IF" and st.get("branch") else ""
        return f"L{ln or '-'}: {tp} — {title}{br}{err}"

    def _on_step_selected(self, cur: Optional[QListWidgetItem], prev: Optional[QListWidgetItem] = None):
        st = cur.data(Qt.UserRole) if cur else None
        if not st:
            self.step_details.setPlainText("")
            return

        lines: List[str] = []
        lines.append(self._human_step_title(st))

        if st.get("expr"):
            lines.append("\nВыражение:")
            lines.append(st.get("expr") or "")

        if st.get("error"):
            lines.append("\nОшибка:")
            lines.append(st.get("error") or "")

        if st.get("preview") and not st.get("is_return"):
            lines.append("\nЧто видно в превью:")
            lines.append(st.get("preview") or "")

        vd = st.get("vars_delta") or {}
        if vd:
            lines.append("\nИзменения переменных:")
            for k, pair in vd.items():
                try:
                    old, new = pair
                except Exception:
                    old, new = None, pair
                lines.append(f"  {k}: {repr(old)} -> {repr(new)}")

        if st.get("sys_info_added"):
            lines.append("\nДобавлен системный блок (фрагмент):")
            lines.append(st.get("sys_info_added") or "")

        if st.get("is_return"):
            lines.append("\nРезультат RETURN (полный):")
            lines.append(st.get("return_text") or "")

        self.step_details.setPlainText("\n".join(lines))

    def _human_step_title(self, st: Dict[str, Any]) -> str:
        tp = (st.get("type") or "").upper()
        ln = st.get("line")
        if tp == "SET":
            # Пытаемся назвать по изменённой переменной
            vd = st.get("vars_delta") or {}
            if vd:
                var = next(iter(vd.keys()))
                old, new = vd[var] if isinstance(vd[var], (list, tuple)) and len(vd[var]) == 2 else (None, vd[var])
                return f"Строка {ln}: установка переменной {var} = {repr(new)} (раньше: {repr(old)})"
            return f"Строка {ln}: установка переменной"
        if tp == "LOG":
            return f"Строка {ln}: запись в лог"
        if tp == "ADD_SYSTEM_INFO":
            return f"Строка {ln}: добавление системного блока"
        if tp == "IF":
            br = st.get("branch")
            br_txt = f" — выбрана ветка: {br}" if br else ""
            return f"Строка {ln}: условная развилка{br_txt}"
        if tp == "RETURN":
            return f"Строка {ln}: завершение — возврат результата ({len(self._final_text)} символов)"
        return f"Строка {ln}: шаг типа {tp}"

    # ---------- Tab: Системные ----------
    def _build_sys_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Системные сообщения (ADD_SYSTEM_INFO):"))

        self.sys_list = QListWidget()
        for s in self._sys_infos:
            item = QListWidgetItem((s if len(s) <= 160 else s[:160] + "…") or "")
            item.setData(Qt.UserRole, s)
            self.sys_list.addItem(item)
        self.sys_list.itemDoubleClicked.connect(self._open_full_item)
        lay.addWidget(self.sys_list, 1)

        row = QHBoxLayout()
        btn_copy = QPushButton("Скопировать все")
        btn_copy.clicked.connect(lambda: self._copy_text("\n\n---\n\n".join(self._sys_infos)))
        row.addStretch(1)
        row.addWidget(btn_copy)
        lay.addLayout(row)
        return w

    # ---------- Tab: Логи ----------
    def _build_logs_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Логи выполнения (команды LOG):"))

        self.log_list = QListWidget()
        for s in self._logs:
            self.log_list.addItem(s)
        lay.addWidget(self.log_list, 1)

        row = QHBoxLayout()
        btn_copy = QPushButton("Скопировать всё")
        btn_copy.clicked.connect(lambda: self._copy_text("\n".join(self._logs)))
        row.addStretch(1)
        row.addWidget(btn_copy)
        lay.addLayout(row)
        return w

    # ---------- Tab: Переменные ----------
    def _build_vars_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        tabs = QTabWidget()
        # До
        before_text = "\n".join(f"{k} = {repr(v)}" for k, v in sorted(self._vars_before.items()))
        tabs.addTab(self._build_vars_text_tab(before_text, "Скопировать «До»"), "До")

        # После
        after_text = "\n".join(f"{k} = {repr(v)}" for k, v in sorted(self._vars_after.items()))
        tabs.addTab(self._build_vars_text_tab(after_text, "Скопировать «После»"), "После")

        # Изменения — таблица
        tabs.addTab(self._build_vars_changes_tab(), "Изменения")

        lay.addWidget(tabs)
        return w

    def _build_vars_text_tab(self, text: str, btn_title: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        edit = QPlainTextEdit()
        edit.setReadOnly(True)
        edit.setFont(QFont("Consolas", 10))
        edit.setPlainText(text or "")
        lay.addWidget(edit, 1)
        row = QHBoxLayout()
        btn_copy = QPushButton(btn_title)
        btn_copy.clicked.connect(lambda: self._copy_text(text))
        row.addStretch(1)
        row.addWidget(btn_copy)
        lay.addLayout(row)
        return w

    def _build_vars_changes_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        changes, changed_cnt, new_cnt = self._compute_changes(self._vars_before, self._vars_after)

        hdr = QLabel(f"Изменено: {changed_cnt} • Новых: {new_cnt}")
        lay.addWidget(hdr)

        tree = QTreeWidget()
        tree.setColumnCount(3)
        tree.setHeaderLabels(["Переменная", "Было", "Стало"])
        tree.header().setStretchLastSection(True)

        for row in changes:
            name = row["name"]
            old = row.get("old")
            new = row.get("new")
            typ = row["type"]  # "changed" | "new"
            it = QTreeWidgetItem([name, repr(old), repr(new)])
            if typ == "new":
                it.setForeground(0, QColor("#98C379"))
                it.setForeground(2, QColor("#98C379"))
            else:
                it.setForeground(1, QColor("#ABB2BF"))
                it.setForeground(2, QColor("#61AFEF"))
            tree.addTopLevelItem(it)

        lay.addWidget(tree, 1)

        btn_row = QHBoxLayout()
        btn_copy = QPushButton("Скопировать список изменений")
        btn_copy.clicked.connect(lambda: self._copy_text("\n".join(self._format_delta_lines(self._vars_before, self._vars_after)[0])))
        btn_row.addStretch(1)
        btn_row.addWidget(btn_copy)
        lay.addLayout(btn_row)

        return w

    # ---------- helpers ----------
    def _format_delta_lines(self, before: Dict[str, Any], after: Dict[str, Any]) -> Tuple[List[str], int, int]:
        changes, changed_cnt, new_cnt = self._compute_changes(before, after)
        lines: List[str] = []
        for ch in changes:
            if ch["type"] == "new":
                lines.append(f"+ {ch['name']} = {repr(ch['new'])}")
            else:
                lines.append(f"~ {ch['name']}: {repr(ch['old'])} → {repr(ch['new'])}")
        return lines, changed_cnt, new_cnt

    def _compute_changes(self, before: Dict[str, Any], after: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int, int]:
        changes: List[Dict[str, Any]] = []
        changed_cnt = 0
        new_cnt = 0
        all_keys = sorted(set(before.keys()) | set(after.keys()))
        for k in all_keys:
            if k in before and k in after:
                if before[k] != after[k]:
                    changes.append({"name": k, "type": "changed", "old": before[k], "new": after[k]})
                    changed_cnt += 1
            elif k not in before and k in after:
                changes.append({"name": k, "type": "new", "old": None, "new": after[k]})
                new_cnt += 1
        return changes, changed_cnt, new_cnt

    def _open_full_item(self, item: QListWidgetItem):
        dlg = QDialog(self)
        dlg.setWindowTitle("Полный текст")
        dlg.setMinimumSize(760, 540)
        lay = QVBoxLayout(dlg)
        txt = QPlainTextEdit()
        txt.setReadOnly(True)
        txt.setFont(QFont("Consolas", 10))
        txt.setPlainText(item.data(Qt.UserRole) or "")
        lay.addWidget(txt)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Save | QDialogButtonBox.Copy)
        btns.accepted.connect(dlg.accept)

        def _save():
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить текст", "", "Текст (*.txt)")
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(txt.toPlainText())
            except Exception as e:
                QMessageBox.critical(self, "Сохранение", f"Ошибка: {e}")

        def _copy():
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(txt.toPlainText() or "")

        btns.button(QDialogButtonBox.Save).clicked.connect(_save)
        btns.button(QDialogButtonBox.Copy).clicked.connect(_copy)
        lay.addWidget(btns)
        dlg.exec()

    def _copy_text(self, s: str):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(s or "")

    def _save_text(self, s: str):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить результат", "", "Текст (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(s or "")
        except Exception as e:
            QMessageBox.critical(self, "Сохранение", f"Ошибка: {e}")