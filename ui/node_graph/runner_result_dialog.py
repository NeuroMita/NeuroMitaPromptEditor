# File: ui/node_graph/runner_result_dialog.py
# File: ui/node_graph/runner_result_dialog.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional

from PySide6.QtCore import Qt
        # noqa
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QListWidget,
    QListWidgetItem, QDialogButtonBox, QWidget, QSplitter, QPushButton, QFrame
)

from ui.node_graph.preview_highlighter import SimplePromptHighlighter


class RunnerResultDialog(QDialog):
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
        self.setMinimumSize(1100, 720)
        self.setModal(False)
        self._steps = steps or []

        lay = QVBoxLayout(self)

        # Верхняя сводка
        summary = self._build_summary(final_text, self._steps, sys_infos, logs, vars_before, vars_after)
        lay.addWidget(summary)

        split = QSplitter(Qt.Horizontal)

        # Левая панель — итоговый текст
        left = QWidget()
        l_lay = QVBoxLayout(left)
        title_lbl = QLabel("Итоговый текст")
        title_lbl.setStyleSheet("font-weight:bold;")
        l_lay.addWidget(title_lbl)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Consolas", 10))
        self.text.setPlainText(final_text or "")
        SimplePromptHighlighter(self.text.document())
        l_lay.addWidget(self.text, 1)

        # кнопки для результата
        btn_row = QHBoxLayout()
        self.len_lbl = QLabel(f"Длина: {len(final_text)} символов")
        self.copy_btn = QPushButton("Копировать")
        self.copy_btn.clicked.connect(lambda: self._copy_text(final_text))
        self.save_btn = QPushButton("Сохранить…")
        self.save_btn.clicked.connect(lambda: self._save_text(final_text))
        btn_row.addWidget(self.len_lbl)
        btn_row.addStretch(1)
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.save_btn)
        l_lay.addLayout(btn_row)

        split.addWidget(left)

        # Правая панель — вертикальный сплиттер: Отчёт -> Системные -> Логи -> Переменные
        right = QSplitter(Qt.Vertical)

        # Отчёт выполнения
        exec_w = QWidget()
        exec_l = QVBoxLayout(exec_w)
        exec_title = QLabel("Отчёт выполнения (маршрут)")
        exec_title.setStyleSheet("font-weight:bold;")
        exec_l.addWidget(exec_title)

        self.exec_list = QListWidget()
        self.exec_list.setSelectionMode(QListWidget.SingleSelection)
        for st in self._steps:
            label = self._format_step_label(st)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, st)
            if st.get("error"):
                item.setForeground(QColor("#E57373"))  # красный
            self.exec_list.addItem(item)
        self.exec_list.currentItemChanged.connect(self._on_step_selected)
        exec_l.addWidget(self.exec_list, 2)

        self.exec_details = QPlainTextEdit()
        self.exec_details.setReadOnly(True)
        self.exec_details.setFont(QFont("Consolas", 9))
        exec_l.addWidget(self.exec_details, 3)

        right.addWidget(exec_w)

        # Системные сообщения
        sys_w = QWidget()
        sys_l = QVBoxLayout(sys_w)
        sys_hdr = QLabel("Системные сообщения (ADD_SYSTEM_INFO)")
        sys_hdr.setStyleSheet("font-weight:bold;")
        sys_l.addWidget(sys_hdr)
        self.sys_list = QListWidget()
        for s in sys_infos or []:
            item = QListWidgetItem((s if len(s) <= 160 else s[:160] + "…") or "")
            item.setData(Qt.UserRole, s)
            self.sys_list.addItem(item)
        self.sys_list.itemDoubleClicked.connect(self._open_full_item)
        sys_l.addWidget(self.sys_list)
        right.addWidget(sys_w)

        # Логи
        log_w = QWidget()
        log_l = QVBoxLayout(log_w)
        log_hdr = QLabel("Логи (LOG)")
        log_hdr.setStyleSheet("font-weight:bold;")
        log_l.addWidget(log_hdr)
        self.log_list = QListWidget()
        for s in logs or []:
            self.log_list.addItem(s)
        log_l.addWidget(self.log_list)
        right.addWidget(log_w)

        # Переменные
        var_w = QWidget()
        var_l = QVBoxLayout(var_w)
        var_hdr = QLabel("Переменные")
        var_hdr.setStyleSheet("font-weight:bold;")
        var_l.addWidget(var_hdr)
        self.var_before = QPlainTextEdit(); self.var_before.setReadOnly(True); self.var_before.setFont(QFont("Consolas", 9))
        self.var_after = QPlainTextEdit();  self.var_after.setReadOnly(True);  self.var_after.setFont(QFont("Consolas", 9))
        self.var_delta = QPlainTextEdit();  self.var_delta.setReadOnly(True);  self.var_delta.setFont(QFont("Consolas", 9))
        var_split = QSplitter(Qt.Vertical)
        var_split2 = QSplitter(Qt.Horizontal)
        before_joined = "\n".join(f"{k} = {repr(v)}" for k, v in sorted(vars_before.items()))
        after_joined  = "\n".join(f"{k} = {repr(v)}" for k, v in sorted(vars_after.items()))
        delta_joined  = "\n".join(self._format_deltas(vars_before, vars_after))
        self.var_before.setPlainText(before_joined)
        self.var_after.setPlainText(after_joined)
        self.var_delta.setPlainText(delta_joined)
        top_pair = QWidget(); top_l = QHBoxLayout(top_pair); top_l.setContentsMargins(0,0,0,0)
        top_l.addWidget(self._group("До", self.var_before), 1)
        top_l.addWidget(self._group("После", self.var_after), 1)
        var_split2.addWidget(top_pair)
        var_split.addWidget(var_split2)
        var_split.addWidget(self._group("Изменения", self.var_delta))
        var_l.addWidget(var_split, 1)
        right.addWidget(var_w)

        split.addWidget(right)
        lay.addWidget(split, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)

        # выбрать первый шаг по умолчанию
        if self.exec_list.count() > 0:
            self.exec_list.setCurrentRow(0)

    def _build_summary(self, final_text: str, steps: List[Dict[str, Any]], sys_infos: List[str],
                       logs: List[str], vars_before: Dict[str, Any], vars_after: Dict[str, Any]) -> QWidget:
        box = QWidget()
        l = QHBoxLayout(box)
        l.setContentsMargins(0, 0, 0, 4)

        # вычисления
        total_nodes = len(steps)
        errors = sum(1 for s in steps if s.get("error"))
        chosen_if = sum(1 for s in steps if s.get("type") == "IF" and s.get("branch"))

        info_lbl = QLabel(f"Выполнено узлов: {total_nodes} | IF-веток выбрано: {chosen_if} | Ошибок: {errors} | "
                          f"SYS_INFO: {len(sys_infos)} | LOG: {len(logs)}")
        info_lbl.setStyleSheet("color:#E6EDF3;")
        l.addWidget(info_lbl)

        l.addStretch(1)
        return box

    def _group(self, title: str, w: QWidget) -> QWidget:
        box = QWidget()
        l = QVBoxLayout(box)
        lbl = QLabel(title)
        lbl.setStyleSheet("font-weight:bold;")
        l.addWidget(lbl)
        l.addWidget(w)
        return box

    def _open_full_item(self, item: QListWidgetItem):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox, QPlainTextEdit
        dlg = QDialog(self)
        dlg.setWindowTitle("Полный текст")
        dlg.setMinimumSize(720, 520)
        lay = QVBoxLayout(dlg)
        txt = QPlainTextEdit()
        txt.setReadOnly(True)
        txt.setFont(QFont("Consolas", 10))
        txt.setPlainText(item.data(Qt.UserRole) or "")
        lay.addWidget(txt)
        btns = QDialogButtonBox(QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        lay.addWidget(btns)
        dlg.exec()

    def _copy_text(self, s: str):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(s or "")

    def _save_text(self, s: str):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить результат", "", "Текст (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(s or "")
        except Exception as e:
            QMessageBox.critical(self, "Сохранение", f"Ошибка: {e}")

    def _format_deltas(self, before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        keys = sorted(set(before.keys()) | set(after.keys()))
        for k in keys:
            b = before.get(k, None); a = after.get(k, None)
            if b != a:
                lines.append(f"{k}: {repr(b)} -> {repr(a)}")
        if not lines:
            lines.append("(нет изменений)")
        return lines

    # ----- execution report -----
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
            self.exec_details.setPlainText("")
            return
        lines: List[str] = []
        lines.append(f"Тип: {st.get('type')}")
        if st.get("line") is not None:
            lines.append(f"Строка: {st.get('line')}")
        if st.get("title"):
            lines.append(f"Заголовок: {st.get('title')}")
        if st.get("subtitle"):
            lines.append(f"Описание: {st.get('subtitle')}")
        if st.get("branch"):
            lines.append(f"Выбрана ветка IF: {st.get('branch')}")

        if st.get("expr"):
            lines.append("\nВыражение:")
            lines.append(st.get("expr") or "")

        if st.get("error"):
            lines.append("\nОШИБКА:")
            lines.append(st.get("error") or "")

        if st.get("preview"):
            lines.append("\nПревью:")
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
            lines.append("\nADD_SYSTEM_INFO (фрагмент):")
            lines.append(st.get("sys_info_added") or "")

        if st.get("is_return"):
            lines.append("\nПолный результат RETURN:")
            lines.append(st.get("return_text") or "")

        self.exec_details.setPlainText("\n".join(lines))