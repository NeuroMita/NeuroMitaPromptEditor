# ui/node_graph/inspector_widget.py
from __future__ import annotations
from typing import Optional, Callable, List
import re

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFormLayout, QLineEdit,
    QCheckBox, QListWidget, QListWidgetItem, QPushButton,
    QHBoxLayout, QFrame, QFileDialog, QAbstractItemView
)

from logic.dsl_ast import AstNode, Set, Log, AddSystemInfo, Return, If, IfBranch
from ui.node_graph.tag_text_edit import TagTextEdit


class Inspector(QWidget):
    """
    Упрощённый инспектор:
    - RETURN: большая textarea (TagTextEdit) + минимальная палитра вставок (перетягиваемые/кликабельные "чипы").
              Никаких выражений/плюсов в инспекторе — итоговый DSL виден снизу в общем превью.
    - IF: простой список условий (перетаскиваемый). Две кнопки — 'Добавить условие', 'Добавить Иначе'.
          Условия редактируются двойным кликом прямо в списке. Удаление — клавиша Delete.
    - SET/LOG/ADD_SYSTEM_INFO: только поля (и минимальные вставки при желании).
    """
    ast_changed = Signal()

    CHIP_STYLE = "padding:4px 8px; border-radius:6px; background:#304FFE; color:#E8EAED;"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ast: Optional[AstNode] = None
        self._preview_provider: Optional[Callable[[str], str]] = None
        self._file_picker: Optional[Callable[[], Optional[str]]] = None

        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Заголовок
        self.title_lbl = QLabel("Свойства узла")
        self.title_lbl.setStyleSheet("font-weight: bold;")
        root.addWidget(self.title_lbl)

        # Форма
        self.form = QFormLayout()
        root.addLayout(self.form)

        # ЯВНЫЕ ярлыки, чтобы их можно было скрывать (исправляет "пустые строки" у START)
        self.var_lbl = QLabel("Переменная:")
        self.var_edit = QLineEdit()

        self.expr_lbl = QLabel("Выражение:")
        self.expr_edit = QLineEdit()

        self.local_chk = QCheckBox("LOCAL")

        self.form.addRow(self.var_lbl, self.var_edit)
        self.form.addRow(self.expr_lbl, self.expr_edit)
        self.form.addRow(QLabel(""), self.local_chk)

        # Сепараторы (можем скрывать)
        self.sep_before_return = self._hline()
        self.sep_before_if = self._hline()
        self.sep_before_apply = self._hline()

        # RETURN
        self.return_label = QLabel("Текст результата:")
        self.return_edit = TagTextEdit()
        self.return_edit.setPlaceholderText("Пиши здесь текст. Вставки как [[LOAD \"Main/core.txt\"]], переменные как {var}.")
        self.return_edit.setMinimumHeight(160)

        # Палитра чипов для RETURN
        self.pal_row = QHBoxLayout()
        self.btn_chip_load = QPushButton("LOAD");     self.btn_chip_load.setStyleSheet(self.CHIP_STYLE)
        self.btn_chip_tag  = QPushButton("LOAD TAG"); self.btn_chip_tag.setStyleSheet(self.CHIP_STYLE)
        self.btn_chip_rel  = QPushButton("LOAD_REL"); self.btn_chip_rel.setStyleSheet(self.CHIP_STYLE)
        self.btn_pick_file = QPushButton("Из файла…")
        self.btn_chip_load.clicked.connect(lambda: self._insert_chip_return('[[LOAD "path/to.txt"]]', True))
        self.btn_chip_tag.clicked.connect(lambda: self._insert_chip_return('[[LOAD SECTION FROM "path/to.txt"]]', True))
        self.btn_chip_rel.clicked.connect(lambda: self._insert_chip_return('[[LOAD_REL "path/to.txt"]]', True))
        self.btn_pick_file.clicked.connect(self._pick_file_for_return)
        for b in (self.btn_chip_load, self.btn_chip_tag, self.btn_chip_rel, self.btn_pick_file):
            self.pal_row.addWidget(b)
        self.pal_row.addStretch(1)

        # IF — упрощённый
        self.if_label = QLabel("Условия:")
        self.if_list = QListWidget()
        self.if_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.if_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.if_list.setDefaultDropAction(Qt.MoveAction)
        self.if_list.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked)
        self.if_list.model().rowsMoved.connect(self._on_if_reordered)
        self.if_list.itemChanged.connect(self._on_if_item_changed)
        # Кнопки IF (минимальные)
        self.if_btn_row = QHBoxLayout()
        self.btn_add_cond = QPushButton("Добавить условие")
        self.btn_add_else = QPushButton("Добавить Иначе")
        # Кнопка удаления (как просили): активна для elif и else, неактивна для первой IF-ветки
        self.btn_del_selected = QPushButton("Удалить выбранное")
        self.btn_del_selected.setEnabled(False)
        self.btn_add_cond.clicked.connect(self._on_add_cond)
        self.btn_add_else.clicked.connect(self._on_toggle_else)
        self.btn_del_selected.clicked.connect(self._on_delete_selected)
        self.if_list.currentRowChanged.connect(self._on_branch_selected)  # обновлять состояние кнопки удаления
        for b in (self.btn_add_cond, self.btn_add_else, self.btn_del_selected):
            self.if_btn_row.addWidget(b)
        self.if_btn_row.addStretch(1)

        # APPLY
        self.apply_btn = QPushButton("Применить изменения")
        self.apply_btn.clicked.connect(self._apply)

        # Сборка
        root.addWidget(self.sep_before_return)
        root.addWidget(self.return_label)
        root.addWidget(self.return_edit)
        root.addLayout(self.pal_row)

        root.addWidget(self.sep_before_if)
        root.addWidget(self.if_label)
        root.addWidget(self.if_list)
        root.addLayout(self.if_btn_row)

        root.addWidget(self.sep_before_apply)
        root.addWidget(self.apply_btn)

        # ВАЖНО: стретч в самом конце — вы просили "добавь стретч после всех строк"
        # Это прибирает "паддинг" у START — контент прижимается к верху.
        root.addStretch(1)

        self._hide_all()
        self._show_empty(True)
        
    # ---------- API ----------
    def set_preview_provider(self, func: Callable[[str], str]):
        self._preview_provider = func

    def set_file_picker(self, func: Callable[[], Optional[str]]):
        self._file_picker = func

    # ---------- Helpers ----------
    def _hline(self):
        l = QFrame()
        l.setFrameShape(QFrame.HLine)
        l.setFrameShadow(QFrame.Sunken)
        return l

    def _hide_all(self):
        # Скрываем вообще все элементы, включая лейблы, чтобы не оставалось "пустых" подписей
        for w in (
            self.var_lbl, self.var_edit, self.expr_lbl, self.expr_edit, self.local_chk,
            self.sep_before_return, self.return_label, self.return_edit,
            self.btn_chip_load, self.btn_chip_tag, self.btn_chip_rel, self.btn_pick_file,
            self.sep_before_if, self.if_label, self.if_list,
            self.btn_add_cond, self.btn_add_else, self.btn_del_selected,
            self.sep_before_apply, self.apply_btn
        ):
            w.hide()

    def _show_empty(self, on: bool):
        if on:
            self.title_lbl.setText("Свойства узла")

    def set_ast(self, ast: Optional[AstNode]):
        self._ast = ast
        self._build()

    def _build(self):
        self._hide_all()
        if self._ast is None:
            self._show_empty(True)
            return

        # START (payload может быть не-AstNode в редакторе)
        if not isinstance(self._ast, AstNode):
            self.title_lbl.setText("START")
            # Ничего лишнего не показываем — паддинга не останется благодаря stretch()
            return

        # SET
        if isinstance(self._ast, Set):
            self.title_lbl.setText("SET")
            self.var_edit.setText(self._ast.var)
            self.expr_edit.setText(self._ast.expr)
            self.local_chk.setChecked(self._ast.local)
            self.var_lbl.show();  self.var_edit.show()
            self.expr_lbl.show(); self.expr_edit.show()
            self.local_chk.show()
            self.sep_before_apply.show(); self.apply_btn.show()
            return

        # LOG
        if isinstance(self._ast, Log):
            self.title_lbl.setText("LOG")
            self.expr_edit.setText(self._ast.expr)
            self.expr_lbl.show(); self.expr_edit.show()
            self.sep_before_apply.show(); self.apply_btn.show()
            return

        # ADD_SYSTEM_INFO
        if isinstance(self._ast, AddSystemInfo):
            self.title_lbl.setText("ADD_SYSTEM_INFO")
            self.expr_edit.setText(self._ast.expr)
            self.expr_lbl.show(); self.expr_edit.show()
            self.sep_before_apply.show(); self.apply_btn.show()
            return

        # RETURN — чистая textarea + палитра
        if isinstance(self._ast, Return):
            self.title_lbl.setText("RETURN")
            txt, ok = self._expr_to_text(self._ast.expr)
            self.return_edit.setPlainText(txt if ok else "")
            self.sep_before_return.show()
            self.return_label.show(); self.return_edit.show()
            self.btn_chip_load.show(); self.btn_chip_tag.show(); self.btn_chip_rel.show(); self.btn_pick_file.show()
            self.sep_before_apply.show(); self.apply_btn.show()
            return

        # IF — список условий + две кнопки + кнопка удаления
        if isinstance(self._ast, If):
            self.title_lbl.setText("IF")
            self.if_list.clear()
            for br in self._ast.branches:
                it = QListWidgetItem(br.cond)
                it.setFlags(it.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.if_list.addItem(it)
            if self._ast.else_body is not None:
                it = QListWidgetItem("ELSE")
                it.setData(Qt.UserRole, "ELSE")
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.if_list.addItem(it)

            self.sep_before_if.show()
            self.if_label.show(); self.if_list.show()
            self.btn_add_cond.show(); self.btn_add_else.show(); self.btn_del_selected.show()
            # Выставим начальное состояние кнопки удаления
            self._on_branch_selected(self.if_list.currentRow())
            self.sep_before_apply.show(); self.apply_btn.show()
            return

        # default
        self.title_lbl.setText(type(self._ast).__name__)

    def _on_branch_selected(self, idx: int):
        """
        Обновляет доступность кнопки 'Удалить выбранное':
        - Первая ветка IF (idx == 0) — кнопка неактивна (нельзя удалять оригинальный IF).
        - Любая другая ветка (ELSEIF) — активна.
        - ELSE — активна.
        """
        if not isinstance(self._ast, If):
            self.btn_del_selected.setEnabled(False)
            return
        if idx < 0:
            self.btn_del_selected.setEnabled(False)
            return
        it = self.if_list.item(idx)
        if not it:
            self.btn_del_selected.setEnabled(False)
            return
        is_else = (it.data(Qt.UserRole) == "ELSE")
        # Первая условная ветка — нельзя
        if not is_else and idx == 0:
            self.btn_del_selected.setEnabled(False)
        else:
            self.btn_del_selected.setEnabled(True)

    # ---------- RETURN chips ----------
    def _insert_chip_return(self, snippet: str, at_cursor: bool):
        if not self.return_edit.isVisible():
            return
        if at_cursor:
            cur = self.return_edit.textCursor()
            cur.insertText(snippet)
            self.return_edit.setTextCursor(cur)
        else:
            self.return_edit.append(snippet)

    def _pick_file_for_return(self):
        if not self._file_picker:
            return
        path = self._file_picker()
        if not path:
            return
        # простая вставка LOAD из файла
        self._insert_chip_return(f'[[LOAD "{path}"]]', True)

    # ---------- IF UX ----------
    def _on_add_cond(self):
        if not isinstance(self._ast, If):
            return
        it = QListWidgetItem("True")
        it.setFlags(it.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.if_list.addItem(it)
        self.if_list.setCurrentItem(it)
        self._sync_if_from_ui()
        self.ast_changed.emit()

    def _on_toggle_else(self):
        if not isinstance(self._ast, If):
            return
        # проверяем, есть ли ELSE
        has_else = any(self.if_list.item(i).data(Qt.UserRole) == "ELSE" for i in range(self.if_list.count()))
        if has_else:
            # убрать ELSE
            for i in range(self.if_list.count()):
                it = self.if_list.item(i)
                if it.data(Qt.UserRole) == "ELSE":
                    self.if_list.takeItem(i)
                    break
        else:
            # добавить ELSE
            it = QListWidgetItem("ELSE")
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setData(Qt.UserRole, "ELSE")
            self.if_list.addItem(it)

        self._sync_if_from_ui()
        self.ast_changed.emit()

    def _on_if_reordered(self, *args, **kwargs):
        if isinstance(self._ast, If):
            self._sync_if_from_ui()
            self.ast_changed.emit()

    def _on_if_item_changed(self, it: QListWidgetItem):
        if isinstance(self._ast, If):
            self._sync_if_from_ui()
            self.ast_changed.emit()

    def keyPressEvent(self, e):
        # Delete удаляет и ELSE, и любые ELSEIF, но не первую IF-ветку
        if e.key() == Qt.Key_Delete and isinstance(self._ast, If) and self.if_list.isVisible():
            idx = self.if_list.currentRow()
            if idx >= 0:
                it = self.if_list.item(idx)
                if it and not (idx == 0 and it.data(Qt.UserRole) != "ELSE"):
                    self.if_list.takeItem(idx)
                    self._sync_if_from_ui()
                    self.ast_changed.emit()
                    return
        super().keyPressEvent(e)

    def _on_delete_selected(self):
        if not isinstance(self._ast, If):
            return
        idx = self.if_list.currentRow()
        if idx < 0:
            return
        it = self.if_list.item(idx)
        if not it:
            return
        # Нельзя удалить первую условную ветку (оригинальный IF)
        if it.data(Qt.UserRole) != "ELSE" and idx == 0:
            return
        self.if_list.takeItem(idx)
        self._sync_if_from_ui()
        self.ast_changed.emit()

    def _sync_if_from_ui(self):
        if not isinstance(self._ast, If):
            return
        conds: List[str] = []
        has_else = False
        for i in range(self.if_list.count()):
            it = self.if_list.item(i)
            if it.data(Qt.UserRole) == "ELSE":
                has_else = True
            else:
                conds.append(it.text().strip())

        # сохранить старые body по индексам, чтобы не терять содержимое веток
        old_bodies = [br.body for br in self._ast.branches]
        self._ast.branches = []
        for idx, cond in enumerate(conds):
            body = old_bodies[idx] if idx < len(old_bodies) else []
            self._ast.branches.append(IfBranch(cond=cond, body=body))

        # ELSE — сразу материализуем/удаляем тело (это добавит/уберёт выход 'else' после rebuild)
        self._ast.else_body = ([] if has_else else None)

    # ---------- APPLY ----------
    def _apply(self):
        if self._ast is None:
            return
        if isinstance(self._ast, Set):
            self._ast.var = self.var_edit.text().strip()
            self._ast.expr = self.expr_edit.text().strip()
            self._ast.local = self.local_chk.isChecked()
        elif isinstance(self._ast, (Log, AddSystemInfo)):
            self._ast.expr = self.expr_edit.text().strip()
        elif isinstance(self._ast, Return):
            # конвертируем textarea -> выражение
            self._ast.expr = self._text_to_expr(self.return_edit.toPlainText())

        self.ast_changed.emit()

    # ---------- text<->expr for RETURN ----------
    CHIP_TOKEN_RE = re.compile(r"\[\[(.+?)\]\]")

    def _text_to_expr(self, text: str) -> str:
        parts: List[str] = []
        last = 0
        for m in self.CHIP_TOKEN_RE.finditer(text):
            if m.start() > last:
                plain = text[last:m.start()]
                if plain:
                    parts.append(self._q3(plain))
            token = m.group(1).strip()
            parts.append(token)
            last = m.end()
        if last < len(text):
            plain = text[last:]
            if plain:
                parts.append(self._q3(plain))
        if not parts:
            parts = [self._q3("")]
        return " + ".join(p for p in parts if p)

    def _expr_to_text(self, expr: str) -> tuple[str, bool]:
        if not expr:
            return "", True
        tokens = self._split_top_level(expr)
        if not tokens:
            return expr, False
        out: List[str] = []
        for tk in tokens:
            tk = tk.strip()
            if self._looks_like_q3(tk) or self._looks_like_q1(tk):
                out.append(self._unquote_any(tk))
            elif tk.upper().startswith("LOAD ") or tk.upper().startswith("LOAD_REL "):
                out.append(f"[[{tk}]]")
            else:
                return expr, False
        return "".join(out), True

    def _split_top_level(self, expr: str) -> List[str]:
        parts: List[str] = []
        buf: List[str] = []
        q = None
        i = 0
        while i < len(expr):
            ch = expr[i]
            if expr.startswith('"""', i):
                if q is None: q = '"""'; i += 3; continue
                elif q == '"""': q = None; i += 3; continue
            elif ch in ("'", '"') and q is None:
                q = ch; i += 1; continue
            elif ch in ("'", '"') and q == ch:
                q = None; i += 1; continue
            if ch == "+" and q is None:
                parts.append("".join(buf).strip()); buf = []; i += 1; continue
            buf.append(ch); i += 1
        if buf: parts.append("".join(buf).strip())
        return [p for p in parts if p]

    def _looks_like_q3(self, s: str) -> bool:
        return s.startswith('"""') and s.endswith('"""')

    def _looks_like_q1(self, s: str) -> bool:
        return (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'"))

    def _unquote_any(self, s: str) -> str:
        if self._looks_like_q3(s): return s[3:-3]
        if self._looks_like_q1(s): return s[1:-1]
        return s

    def _q3(self, t: str) -> str:
        safe = t.replace('"""', '\\"""')
        return f'"""{safe}"""'