# File: ui/node_graph/inspector_widget.py
from __future__ import annotations
from typing import Optional, Callable, List
import re

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFormLayout, QLineEdit,
    QCheckBox, QListWidget, QListWidgetItem, QPushButton,
    QHBoxLayout, QFrame, QAbstractItemView, QTabWidget, QSizePolicy
)
from PySide6.QtGui import QTextOption

from logic.dsl_ast import AstNode, Set, Log, AddSystemInfo, Return, If, IfBranch
from ui.node_graph.tag_text_edit import TagTextEdit


class AutoResizingTextEdit(TagTextEdit):
    """
    Авто-растущий редактор по контенту (wrap-aware).
    Основан на TagTextEdit ради единого стиля, но чипы переменных выключены.
    """
    heightChanged = Signal(int)

    def __init__(self, parent=None, min_lines: int = 3, max_lines: int = 20):
        super().__init__(parent)
        self.set_show_var_chips(False)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._min_lines = min_lines
        self._max_lines = max_lines
        self.document().contentsChanged.connect(self._recalc_height)
        try:
            self.document().documentLayout().documentSizeChanged.connect(lambda *_: self._recalc_height())
        except Exception:
            pass

    def set_line_limits(self, min_lines: int, max_lines: int):
        self._min_lines = min_lines
        self._max_lines = max_lines
        self._recalc_height()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._recalc_height()

    def _recalc_height(self):
        doc_h = self.document().documentLayout().documentSize().height()
        fm = self.fontMetrics()
        line_h = max(1, fm.lineSpacing())
        min_h = self._min_lines * line_h
        max_h = self._max_lines * line_h
        frame = self.frameWidth() * 2
        pad = 8
        desired = int(min(max(doc_h, min_h), max_h) + frame + pad)
        if abs(self.height() - desired) > 2:
            self.setFixedHeight(desired)
            self.heightChanged.emit(desired)


class Inspector(QWidget):
    """
    Инспектор (строгий стиль) с авто-растущим редактором и превью:
    - SET/LOG/ADD_SYSTEM_INFO: вкладки 'Редактор/Превью' (для LOG/ASI превью отключено).
    - RETURN: тоже 'Редактор/Превью' (как просили).
    - RETURN: кнопки-чипы для быстрого вставления шаблонов LOAD/LOAD_REL в редактор выражения.
    - IF: список условий.
    """
    ast_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ast: Optional[AstNode] = None
        self._preview_provider: Optional[Callable[[str], str]] = None
        self._file_picker: Optional[Callable[[], Optional[str]]] = None

        self.setMinimumWidth(420)
        self.setStyleSheet("""
            QWidget { background: #1A1A1A; color: #E0E0E0; }
            QLabel { color: #E0E0E0; font-size: 9pt; }
            QLineEdit {
                background: #2A2A2A; color: #FFFFFF;
                border: 1px solid #444444; border-radius: 2px; padding: 4px;
            }
            QPushButton {
                background: #2A2A2A; color: #FFFFFF;
                border: 1px solid #444444; border-radius: 2px; padding: 6px 12px;
            }
            QPushButton:hover { background: #353535; border: 1px solid #666666; }
            QPushButton:pressed { background: #1A1A1A; }
            QCheckBox { color: #E0E0E0; }
            QListWidget {
                background: #2A2A2A; color: #FFFFFF; border: 1px solid #444444; border-radius: 2px;
            }
            QTabWidget::pane { border: 1px solid #444444; }
            QTabBar::tab { background:#2A2A2A; color:#fff; padding:6px 10px; }
            QTabBar::tab:selected { background:#3A3A3A; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self.title_lbl = QLabel("Свойства узла")
        self.title_lbl.setStyleSheet("font-weight: bold; font-size: 10pt; color: #FFFFFF;")
        root.addWidget(self.title_lbl)

        # Описание ноды
        self.description_lbl = QLabel("")
        self.description_lbl.setWordWrap(True)
        self.description_lbl.setStyleSheet("color: #999999; font-size: 8.5pt; padding: 6px; background: #252525; border-radius: 2px;")
        self.description_lbl.setMinimumHeight(32)
        root.addWidget(self.description_lbl)

        self.form = QFormLayout()
        self.form.setSpacing(6)
        root.addLayout(self.form)

        # ----------------- Общие поля для SET/LOG/ASI -----------------
        self.var_lbl = QLabel("Переменная:")
        self.var_edit = QLineEdit()
        self.expr_lbl = QLabel("Выражение:")

        self.set_tabs = QTabWidget()
        self.set_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.expr_edit = AutoResizingTextEdit(min_lines=3, max_lines=20)
        self.expr_edit.heightChanged.connect(self._sync_tabs_height)

        self.set_preview = TagTextEdit()
        self.set_preview.setReadOnly(True)
        self.set_preview.set_show_var_chips(True)

        self.set_tabs.addTab(self.expr_edit, "Редактор")
        self.set_tabs.addTab(self.set_preview, "Превью")
        self.set_tabs.currentChanged.connect(self._refresh_set_preview)

        self.local_chk = QCheckBox("LOCAL")

        self.form.addRow(self.var_lbl, self.var_edit)
        self.form.addRow(self.expr_lbl, self.set_tabs)
        self.form.addRow(QLabel(""), self.local_chk)

        # ----------------- RETURN: редактор/превью + чипы -----------------
        self.sep_before_return = self._hline()
        self.return_expr_label = QLabel("Выражение:")
        self.ret_tabs = QTabWidget()
        self.ret_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.ret_expr_edit = AutoResizingTextEdit(min_lines=3, max_lines=20)
        self.ret_expr_edit.heightChanged.connect(self._sync_ret_tabs_height)

        self.ret_preview = TagTextEdit()
        self.ret_preview.setReadOnly(True)
        self.ret_preview.set_show_var_chips(True)

        self.ret_tabs.addTab(self.ret_expr_edit, "Редактор")
        self.ret_tabs.addTab(self.ret_preview, "Превью")
        self.ret_tabs.currentChanged.connect(self._refresh_return_preview)

        # Палитра чипов для RETURN (вставляют шаблон прямо в редактор выражения)
        chip_style = """
            QPushButton {
                background: #444444; color: #FFFFFF;
                border: 1px solid #666666; border-radius: 3px;
                padding: 4px 10px; font-size: 8pt;
            }
            QPushButton:hover { background: #555555; }
        """
        self.pal_row = QHBoxLayout()
        self.btn_chip_load = QPushButton("LOAD");      self.btn_chip_load.setStyleSheet(chip_style)
        self.btn_chip_tag  = QPushButton("LOAD TAG");  self.btn_chip_tag.setStyleSheet(chip_style)
        self.btn_chip_rel  = QPushButton("LOAD_REL");  self.btn_chip_rel.setStyleSheet(chip_style)
        self.btn_pick_file = QPushButton("Выбрать файл…")

        # Вставляем DSL-токены (НЕ [[...]]), т.к. редактируем выражение напрямую
        self.btn_chip_load.clicked.connect(lambda: self._insert_chip_return('LOAD "path/to.txt"'))
        self.btn_chip_tag.clicked.connect(lambda: self._insert_chip_return('LOAD SECTION FROM "path/to.txt"'))
        self.btn_chip_rel.clicked.connect(lambda: self._insert_chip_return('LOAD_REL "path/to.txt"'))
        self.btn_pick_file.clicked.connect(self._pick_file_for_return)

        for b in (self.btn_chip_load, self.btn_chip_tag, self.btn_chip_rel, self.btn_pick_file):
            self.pal_row.addWidget(b)
        self.pal_row.addStretch(1)

        # ----------------- IF -----------------
        self.sep_before_if = self._hline()
        self.if_label = QLabel("Условия:")
        self.if_list = QListWidget()
        self.if_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.if_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.if_list.setDefaultDropAction(Qt.MoveAction)
        self.if_list.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.if_list.model().rowsMoved.connect(self._on_if_reordered)
        self.if_list.itemChanged.connect(self._on_if_item_changed)
        self.if_btn_row = QHBoxLayout()
        self.btn_add_cond = QPushButton("+ Условие")
        self.btn_add_else = QPushButton("+ Иначе")
        self.btn_del_selected = QPushButton("Удалить")
        self.btn_del_selected.setEnabled(False)
        self.btn_add_cond.clicked.connect(self._on_add_cond)
        self.btn_add_else.clicked.connect(self._on_toggle_else)
        self.btn_del_selected.clicked.connect(self._on_delete_selected)
        self.if_list.currentRowChanged.connect(self._on_branch_selected)
        for b in (self.btn_add_cond, self.btn_add_else, self.btn_del_selected):
            self.if_btn_row.addWidget(b)
        self.if_btn_row.addStretch(1)

        # APPLY
        self.sep_before_apply = self._hline()
        self.apply_btn = QPushButton("Применить изменения")
        self.apply_btn.clicked.connect(self._apply)

        # Сборка нижних секций
        root.addWidget(self.sep_before_return)
        root.addWidget(self.return_expr_label)
        root.addWidget(self.ret_tabs)
        root.addLayout(self.pal_row)

        root.addWidget(self.sep_before_if)
        root.addWidget(self.if_label)
        root.addWidget(self.if_list)
        root.addLayout(self.if_btn_row)

        root.addWidget(self.sep_before_apply)
        root.addWidget(self.apply_btn)
        root.addStretch(1)

        self._hide_all()
        self._show_empty(True)

    # API
    def set_preview_provider(self, func: Callable[[str], str]):
        self._preview_provider = func

    def set_file_picker(self, func: Callable[[], Optional[str]]):
        self._file_picker = func

    # Helpers
    def _hline(self):
        l = QFrame()
        l.setFrameShape(QFrame.HLine)
        l.setStyleSheet("background: #333333;")
        l.setMaximumHeight(1)
        return l

    def _hide_all(self):
        for w in (
            self.description_lbl,
            # SET/LOG/ASI часть
            self.var_lbl, self.var_edit, self.expr_lbl, self.set_tabs, self.local_chk,
            # RETURN часть
            self.sep_before_return, self.return_expr_label, self.ret_tabs,
            self.btn_chip_load, self.btn_chip_tag, self.btn_chip_rel, self.btn_pick_file,
            # IF часть
            self.sep_before_if, self.if_label, self.if_list,
            self.btn_add_cond, self.btn_add_else, self.btn_del_selected,
            # APPLY
            self.sep_before_apply, self.apply_btn
        ):
            w.hide()

    def _show_empty(self, on: bool):
        if on:
            self.title_lbl.setText("Свойства узла")

    def set_ast(self, ast: Optional[AstNode]):
        self._ast = ast
        self._build()

    # ---- авто-высота вкладок на основе высоты редактора ----
    def _sync_tabs_height(self, editor_h: int):
        try:
            self.set_preview.setFixedHeight(editor_h)
            tb_h = self.set_tabs.tabBar().sizeHint().height()
            total = editor_h + tb_h + 8
            self.set_tabs.setFixedHeight(total)
        except Exception:
            pass

    def _sync_ret_tabs_height(self, editor_h: int):
        try:
            self.ret_preview.setFixedHeight(editor_h)
            tb_h = self.ret_tabs.tabBar().sizeHint().height()
            total = editor_h + tb_h + 8
            self.ret_tabs.setFixedHeight(total)
        except Exception:
            pass

    # ---- превью для SET/LOG/ASI ----
    def _refresh_set_preview(self, idx: int | None = None):
        if not isinstance(self._ast, Set):
            return
        expr = self.expr_edit.toPlainText().strip()
        if not expr:
            self.set_preview.setPlainText("")
            return
        tokens = self._split_top_level(expr)
        out: List[str] = []
        for tk in tokens:
            t = tk.strip()
            if self._looks_like_q3(t) or self._looks_like_q1(t):
                out.append(self._unquote_any(t))
            elif t.upper().startswith("LOAD ") or t.upper().startswith("LOAD_REL "):
                if self._preview_provider:
                    pv = self._preview_provider(t)
                    out.append(pv if pv else t)
                else:
                    out.append(t)
            else:
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", t):
                    out.append("{%s}" % t)
                else:
                    out.append(t)
        self.set_preview.setPlainText("".join(out))
        self._sync_tabs_height(self.expr_edit.height())

    # ---- превью для RETURN ----
    def _refresh_return_preview(self, idx: int | None = None):
        if not isinstance(self._ast, Return):
            return
        expr = self.ret_expr_edit.toPlainText().strip()
        if not expr:
            self.ret_preview.setPlainText("")
            return
        tokens = self._split_top_level(expr)
        out: List[str] = []
        for tk in tokens:
            t = tk.strip()
            if self._looks_like_q3(t) or self._looks_like_q1(t):
                out.append(self._unquote_any(t))
            elif t.upper().startswith("LOAD ") or t.upper().startswith("LOAD_REL "):
                if self._preview_provider:
                    pv = self._preview_provider(t)
                    out.append(pv if pv else t)
                else:
                    out.append(t)
            else:
                if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", t):
                    out.append("{%s}" % t)
                else:
                    out.append(t)
        self.ret_preview.setPlainText("".join(out))
        self._sync_ret_tabs_height(self.ret_expr_edit.height())

    def _build(self):
        self._hide_all()
        if self._ast is None:
            self._show_empty(True)
            return

        if not isinstance(self._ast, AstNode):
            self.title_lbl.setText("START")
            self.description_lbl.setText("Начальная точка выполнения скрипта.")
            self.description_lbl.show()
            return

        # Описание
        desc = self._get_description(self._ast)
        if desc:
            self.description_lbl.setText(desc)
            self.description_lbl.show()

        # SET
        if isinstance(self._ast, Set):
            self.title_lbl.setText("Установить переменную")
            self.var_edit.setText(self._ast.var)
            self.expr_edit.setPlainText(self._ast.expr)
            self.local_chk.setChecked(self._ast.local)

            self.var_lbl.show(); self.var_edit.show()
            self.expr_lbl.show(); self.set_tabs.show()
            self.local_chk.show()

            self.set_tabs.setTabEnabled(1, True)
            self._sync_tabs_height(self.expr_edit.height())
            self.sep_before_apply.show(); self.apply_btn.show()
            return

        # LOG (без превью)
        if isinstance(self._ast, Log):
            self.title_lbl.setText("Записать в лог")
            self.expr_edit.setPlainText(self._ast.expr)
            self.var_lbl.hide(); self.var_edit.hide()
            self.expr_lbl.show(); self.set_tabs.show()
            self.set_tabs.setCurrentIndex(0)
            self.set_tabs.setTabEnabled(1, False)
            self.local_chk.hide()
            self._sync_tabs_height(self.expr_edit.height())
            self.sep_before_apply.show(); self.apply_btn.show()
            return

        # ADD_SYSTEM_INFO (без превью)
        if isinstance(self._ast, AddSystemInfo):
            self.title_lbl.setText("Системная информация")
            self.expr_edit.setPlainText(self._ast.expr)
            self.var_lbl.hide(); self.var_edit.hide()
            self.expr_lbl.show(); self.set_tabs.show()
            self.set_tabs.setCurrentIndex(0)
            self.set_tabs.setTabEnabled(1, False)
            self.local_chk.hide()
            self._sync_tabs_height(self.expr_edit.height())
            self.sep_before_apply.show(); self.apply_btn.show()
            return

        # RETURN — теперь тоже Выражение с вкладками
        if isinstance(self._ast, Return):
            self.title_lbl.setText("Вернуть результат")
            self.ret_expr_edit.setPlainText(self._ast.expr)

            self.sep_before_return.show()
            self.return_expr_label.show()
            self.ret_tabs.show()
            self.btn_chip_load.show(); self.btn_chip_tag.show(); self.btn_chip_rel.show(); self.btn_pick_file.show()

            self._sync_ret_tabs_height(self.ret_expr_edit.height())
            self._refresh_return_preview()
            self.sep_before_apply.show(); self.apply_btn.show()
            return

        # IF
        if isinstance(self._ast, If):
            self.title_lbl.setText("Условие")
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
            self._on_branch_selected(self.if_list.currentRow())
            self.sep_before_apply.show(); self.apply_btn.show()
            return

        self.title_lbl.setText(type(self._ast).__name__)

    def _get_description(self, node: AstNode) -> str:
        if isinstance(node, Set):
            return "Создаёт или изменяет переменную. LOCAL — видна только внутри текущего блока."
        elif isinstance(node, Log):
            return "Выводит значение выражения в лог для отладки."
        elif isinstance(node, AddSystemInfo):
            return "Добавляет системные инструкции, обычно загружает файл в начало промпта."
        elif isinstance(node, Return):
            return "Возвращает итоговый текст промпта. Завершает выполнение скрипта."
        elif isinstance(node, If):
            return "Условная развилка: выполняет разные ветки кода в зависимости от условий."
        return ""

    def _on_branch_selected(self, idx: int):
        if not isinstance(self._ast, If):
            self.btn_del_selected.setEnabled(False); return
        if idx < 0:
            self.btn_del_selected.setEnabled(False); return
        it = self.if_list.item(idx)
        if not it:
            self.btn_del_selected.setEnabled(False); return
        is_else = (it.data(Qt.UserRole) == "ELSE")
        self.btn_del_selected.setEnabled(is_else or idx > 0)

    # --- RETURN chips insert ---
    def _insert_chip_return(self, snippet: str):
        if not self.ret_tabs.isVisible():
            return
        cur = self.ret_expr_edit.textCursor()
        cur.insertText(snippet)
        self.ret_expr_edit.setTextCursor(cur)
        self._refresh_return_preview()

    def _pick_file_for_return(self):
        if not self._file_picker:
            return
        path = self._file_picker()
        if not path:
            return
        self._insert_chip_return(f'LOAD "{path}"')

    # --- IF handlers ---
    def _on_add_cond(self):
        if not isinstance(self._ast, If): return
        it = QListWidgetItem("True")
        it.setFlags(it.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.if_list.addItem(it)
        self.if_list.setCurrentItem(it)
        self._sync_if_from_ui()
        self.ast_changed.emit()

    def _on_toggle_else(self):
        if not isinstance(self._ast, If): return
        has_else = any(self.if_list.item(i).data(Qt.UserRole) == "ELSE" for i in range(self.if_list.count()))
        if has_else:
            for i in range(self.if_list.count()):
                it = self.if_list.item(i)
                if it.data(Qt.UserRole) == "ELSE":
                    self.if_list.takeItem(i)
                    break
        else:
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
        if not isinstance(self._ast, If): return
        idx = self.if_list.currentRow()
        if idx < 0: return
        it = self.if_list.item(idx)
        if not it: return
        if it.data(Qt.UserRole) != "ELSE" and idx == 0: return
        self.if_list.takeItem(idx)
        self._sync_if_from_ui()
        self.ast_changed.emit()

    def _sync_if_from_ui(self):
        if not isinstance(self._ast, If): return
        conds: List[str] = []
        has_else = False
        for i in range(self.if_list.count()):
            it = self.if_list.item(i)
            if it.data(Qt.UserRole) == "ELSE":
                has_else = True
            else:
                conds.append(it.text().strip())

        old_bodies = [br.body for br in self._ast.branches]
        self._ast.branches = []
        for idx, cond in enumerate(conds):
            body = old_bodies[idx] if idx < len(old_bodies) else []
            self._ast.branches.append(IfBranch(cond=cond, body=body))

        self._ast.else_body = ([] if has_else else None)

    def _apply(self):
        if self._ast is None: return
        if isinstance(self._ast, Set):
            self._ast.var = self.var_edit.text().strip()
            self._ast.expr = self.expr_edit.toPlainText().strip()
            self._ast.local = self.local_chk.isChecked()
        elif isinstance(self._ast, (Log, AddSystemInfo)):
            self._ast.expr = self.expr_edit.toPlainText().strip()
        elif isinstance(self._ast, Return):
            # Теперь редактируем выражение напрямую
            self._ast.expr = self.ret_expr_edit.toPlainText().strip()
        self.ast_changed.emit()

    # ---------- utils for RETURN text<->expr (оставлены для совместимости) ----------
    CHIP_TOKEN_RE = re.compile(r"\[\[(.+?)\]\]")

    def _expr_to_text(self, expr: str) -> tuple[str, bool]:
        if not expr: return "", True
        tokens = self._split_top_level(expr)
        if not tokens: return expr, False
        out: List[str] = []
        for tk in tokens:
            tk = tk.strip()
            if self._looks_like_q3(tk) or self._looks_like_q1(tk):
                out.append(self._unquote_any(tk))
            elif tk.upper().startswith("LOAD ") or tk.upper().startswith("LOAD_REL "):
                out.append(f"[[{tk}]]")  # исторически поддерживали
            else:
                return expr, False
        return "".join(out), True

    # ---------- tokenization helpers ----------
    def _split_top_level(self, expr: str) -> List[str]:
        parts: List[str] = []
        buf: List[str] = []
        q = None
        esc = False
        i = 0
        n = len(expr)
        while i < n:
            if q is None and expr.startswith('"""', i):
                q = '"""'; i += 3; continue
            ch = expr[i]
            if q in ("'", '"'):
                if esc:
                    buf.append(ch); esc = False; i += 1; continue
                if ch == "\\":
                    buf.append(ch); esc = True; i += 1; continue
                buf.append(ch)
                if ch == q:
                    q = None
                i += 1; continue
            if q == '"""':
                if expr.startswith('"""', i):
                    buf.append('"""'); i += 3; q = None; continue
                buf.append(ch); i += 1; continue
            if ch == "'":
                q = "'"; buf.append(ch); i += 1; continue
            if ch == '"':
                q = '"'; buf.append(ch); i += 1; continue
            if ch == "+":
                parts.append("".join(buf).strip()); buf = []; i += 1; continue
            buf.append(ch); i += 1
        if buf:
            parts.append("".join(buf).strip())
        return [p for p in parts if p]

    def _looks_like_q3(self, s: str) -> bool:
        return s.startswith('"""') and s.endswith('"""')

    def _looks_like_q1(self, s: str) -> bool:
        return (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'"))

    def _unquote_any(self, s: str) -> str:
        if self._looks_like_q3(s):
            return s[3:-3]
        if self._looks_like_q1(s):
            inner = s[1:-1]
            return self._unescape(inner)
        return s

    def _unescape(self, s: str) -> str:
        out = []
        esc = False
        for ch in s:
            if esc:
                if ch == "n": out.append("\n")
                elif ch == "t": out.append("\t")
                elif ch == "r": out.append("\r")
                else: out.append(ch)
                esc = False
            else:
                if ch == "\\":
                    esc = True
                else:
                    out.append(ch)
        if esc:
            out.append("\\")
        return "".join(out)