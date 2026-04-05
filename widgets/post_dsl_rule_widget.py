"""
widgets/post_dsl_rule_widget.py

Диалог для визуального редактирования одного PostScript правила.

Формат .postscript:
    RULE rule_name
        MATCH REGEX "pattern" CAPTURE (var1, var2)
        ACTIONS
            SET attitude += {match_1}
            REMOVE_MATCH
            REPLACE_MATCH WITH "replaced"
        END_ACTIONS
    END_RULE
"""
from __future__ import annotations

from typing import Optional
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QCheckBox, QTextEdit, QPushButton,
    QLabel, QDialogButtonBox, QGroupBox, QScrollArea, QFrame,
    QSizePolicy, QMessageBox,
)
from PySide6.QtGui import QFont


# --------------------------------------------------------------------------- #
#  Модель одного правила                                                       #
# --------------------------------------------------------------------------- #

@dataclass
class RuleSpec:
    """Данные одного PostScript-правила (VM-friendly)."""
    name: str           = "new_rule"
    match_type: str     = "REGEX"     # "REGEX" | "TEXT"
    pattern: str        = ""
    captures: list[str] = field(default_factory=list)
    actions: list[str]  = field(default_factory=list)
    remove_match: bool  = False
    replace_with: str   = ""          # если не пустой — REPLACE_MATCH WITH ...

    @classmethod
    def from_engine_rule(cls, rule) -> "RuleSpec":
        """Конвертирует PostDslRule → RuleSpec."""
        spec = cls(
            name=rule.name,
            match_type=rule.match_type,
            pattern=rule.pattern_str,
            captures=list(rule.capture_names),
            actions=list(rule.action_lines),
            remove_match=rule.remove_match_flag,
            replace_with=rule.replace_with_expr or "",
        )
        return spec

    def to_postscript(self) -> str:
        """Генерирует .postscript-текст для этого правила."""
        lines = [f"RULE {self.name}"]

        cap_part = ""
        if self.captures:
            cap_part = f" CAPTURE ({', '.join(self.captures)})"
        pattern_safe = self.pattern.replace('"', '\\"')
        lines.append(f'    MATCH {self.match_type} "{pattern_safe}"{cap_part}')

        has_actions = self.actions or self.remove_match or self.replace_with
        if has_actions:
            lines.append("    ACTIONS")
            for act in self.actions:
                lines.append(f"        {act}")
            if self.remove_match:
                lines.append("        REMOVE_MATCH")
            if self.replace_with:
                lines.append(f'        REPLACE_MATCH WITH {self.replace_with}')
            lines.append("    END_ACTIONS")

        lines.append("END_RULE")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
#  Диалог редактирования правила                                               #
# --------------------------------------------------------------------------- #

class PostScriptRuleDialog(QDialog):
    """
    Диалог для визуального редактирования одного PostScript-правила.

    Использование:
        dlg = PostScriptRuleDialog(spec, parent)
        if dlg.exec() == QDialog.Accepted:
            new_spec = dlg.get_spec()
    """

    def __init__(self, spec: Optional[RuleSpec] = None, parent=None):
        super().__init__(parent)
        self._spec = spec or RuleSpec()
        self.setWindowTitle("Редактор правила PostScript")
        self.resize(500, 540)
        self.setModal(True)
        self._build_ui()
        self._load_spec(self._spec)

    def get_spec(self) -> RuleSpec:
        return self._collect_spec()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # 1. Название правила
        form = QFormLayout()
        form.setSpacing(6)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("attitude_change")
        self._name_edit.setStyleSheet(_FIELD_STYLE)
        form.addRow("Название:", self._name_edit)
        lay.addLayout(form)

        # 2. MATCH
        grp_match = QGroupBox("Условие совпадения (MATCH)")
        grp_match.setStyleSheet(_GROUP_STYLE)
        match_lay = QVBoxLayout(grp_match)
        match_lay.setSpacing(6)

        row_type = QHBoxLayout()
        row_type.addWidget(QLabel("Тип:"))
        self._match_type = QComboBox()
        self._match_type.addItems(["REGEX", "TEXT"])
        self._match_type.setStyleSheet(_COMBO_STYLE)
        row_type.addWidget(self._match_type)
        row_type.addStretch()
        match_lay.addLayout(row_type)

        match_lay.addWidget(QLabel("Паттерн:"))
        self._pattern_edit = QLineEdit()
        self._pattern_edit.setPlaceholderText(r"attitude[:\s]+(\d+)")
        self._pattern_edit.setStyleSheet(_FIELD_STYLE)
        match_lay.addWidget(self._pattern_edit)

        match_lay.addWidget(QLabel("Группы захвата CAPTURE (через запятую):"))
        self._captures_edit = QLineEdit()
        self._captures_edit.setPlaceholderText("match_1, match_2")
        self._captures_edit.setToolTip("Имена групп из паттерна. Используются в действиях как {match_1}")
        self._captures_edit.setStyleSheet(_FIELD_STYLE)
        match_lay.addWidget(self._captures_edit)
        lay.addWidget(grp_match)

        # 3. ACTIONS
        grp_act = QGroupBox("Действия (ACTIONS)")
        grp_act.setStyleSheet(_GROUP_STYLE)
        act_lay = QVBoxLayout(grp_act)

        act_lay.addWidget(QLabel("Строки действий (по одной на строку):"))
        self._actions_edit = QTextEdit()
        self._actions_edit.setPlaceholderText("SET attitude += {match_1}\nSET stress = max(0, stress - 5)")
        self._actions_edit.setFont(QFont("Consolas", 10))
        self._actions_edit.setFixedHeight(100)
        self._actions_edit.setStyleSheet(_TEXTEDIT_STYLE)
        act_lay.addWidget(self._actions_edit)

        # Флаги
        flags_row = QHBoxLayout()
        self._remove_cb = QCheckBox("REMOVE_MATCH (удалить совпадение из текста)")
        self._remove_cb.setStyleSheet("color: #c9d1d9;")
        flags_row.addWidget(self._remove_cb)
        act_lay.addLayout(flags_row)

        repl_row = QHBoxLayout()
        repl_row.addWidget(QLabel("REPLACE_MATCH WITH:"))
        self._replace_edit = QLineEdit()
        self._replace_edit.setPlaceholderText('""  или  "{match_1} заменено"')
        self._replace_edit.setStyleSheet(_FIELD_STYLE)
        repl_row.addWidget(self._replace_edit, 1)
        act_lay.addLayout(repl_row)

        lay.addWidget(grp_act)

        # 4. Предпросмотр кода
        self._preview_lbl = QLabel("Предпросмотр кода:")
        lay.addWidget(self._preview_lbl)
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFixedHeight(90)
        self._preview.setFont(QFont("Consolas", 9))
        self._preview.setStyleSheet(_TEXTEDIT_STYLE)
        lay.addWidget(self._preview)

        # Подключаем обновление превью
        for w in (self._name_edit, self._pattern_edit,
                  self._captures_edit, self._replace_edit):
            w.textChanged.connect(self._update_preview)
        self._match_type.currentTextChanged.connect(self._update_preview)
        self._actions_edit.textChanged.connect(self._update_preview)
        self._remove_cb.toggled.connect(self._update_preview)

        # 5. Кнопки
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _load_spec(self, spec: RuleSpec):
        self._name_edit.setText(spec.name)
        idx = self._match_type.findText(spec.match_type)
        if idx >= 0:
            self._match_type.setCurrentIndex(idx)
        self._pattern_edit.setText(spec.pattern)
        self._captures_edit.setText(", ".join(spec.captures))
        self._actions_edit.setPlainText("\n".join(spec.actions))
        self._remove_cb.setChecked(spec.remove_match)
        self._replace_edit.setText(spec.replace_with)
        self._update_preview()

    def _collect_spec(self) -> RuleSpec:
        caps_raw = self._captures_edit.text().strip()
        captures = [c.strip() for c in caps_raw.split(",") if c.strip()] if caps_raw else []
        actions = [l for l in self._actions_edit.toPlainText().splitlines() if l.strip()]
        return RuleSpec(
            name=self._name_edit.text().strip() or "unnamed",
            match_type=self._match_type.currentText(),
            pattern=self._pattern_edit.text(),
            captures=captures,
            actions=actions,
            remove_match=self._remove_cb.isChecked(),
            replace_with=self._replace_edit.text().strip(),
        )

    def _update_preview(self):
        spec = self._collect_spec()
        self._preview.setPlainText(spec.to_postscript())

    def _on_accept(self):
        if not self._name_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Название правила не может быть пустым.")
            return
        if not self._pattern_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Паттерн не может быть пустым.")
            return
        self.accept()


# --------------------------------------------------------------------------- #
#  Стили                                                                       #
# --------------------------------------------------------------------------- #

_FIELD_STYLE = """
    QLineEdit {
        background: #1f2329; color: #e6edf3;
        border: 1px solid #30363d; border-radius: 4px;
        padding: 4px 8px;
    }
    QLineEdit:focus { border-color: #4a9eff; }
"""

_COMBO_STYLE = """
    QComboBox {
        background: #1f2329; color: #e6edf3;
        border: 1px solid #30363d; border-radius: 4px;
        padding: 3px 8px; min-width: 80px;
    }
    QComboBox::drop-down { border: none; }
    QComboBox QAbstractItemView { background: #1f2329; color: #e6edf3; }
"""

_TEXTEDIT_STYLE = """
    QTextEdit {
        background: #1f2329; color: #e6edf3;
        border: 1px solid #30363d; border-radius: 4px;
    }
"""

_GROUP_STYLE = """
    QGroupBox {
        color: #8b949e; border: 1px solid #30363d;
        border-radius: 6px; margin-top: 8px;
        padding-top: 6px;
    }
    QGroupBox::title { subcontrol-origin: margin; left: 8px; }
"""
