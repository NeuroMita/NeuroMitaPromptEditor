from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QDoubleSpinBox,
    QTextEdit, QDialogButtonBox, QCheckBox, QListWidget, QListWidgetItem, QPushButton,
    QWidget, QScrollArea, QPlainTextEdit
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

import re
import math
from typing import List, Dict, Any, Optional

try:
    import tiktoken
except ImportError:
    tiktoken = None

from syntax.styles import SyntaxStyleDark


class PopupViewer(QDialog):
    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(600, 400)
        layout = QVBoxLayout(self)
        txt = QPlainTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(content or "")
        txt.setFont(QFont("Consolas", 10))
        layout.addWidget(txt)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)


class DslResultDialog(QDialog):
    MODELS_INFO = {
        "gemini-1.5-flash":                     dict(encoding_name="cl100k_base", price=0.075),
        "gemini-2.0-flash":                     dict(encoding_name="cl100k_base", price=0.1),
        "gpt-4o":                               dict(encoding_name="cl100k_base", price=5.0),
        "gpt-4o-mini":                          dict(encoding_name="cl100k_base", price=0.15),
        "deepseek-chat":                        dict(encoding_name="cl100k_base", price=0.5),
        "google/gemini-2.0-pro-exp-02-05:free": dict(encoding_name="cl100k_base", price=0.0),
        "deepseek/deepseek-chat:free":          dict(encoding_name="cl100k_base", price=0.0),
        "deepseek/deepseek-chat-v3-0324:free":  dict(encoding_name="cl100k_base", price=0.0),
        "google/gemini-2.5-pro-exp-03-25":      dict(encoding_name="cl100k_base", price=1.25),
    }

    def __init__(self,
                 title_text: str,
                 content_blocks: Optional[List[str]] = None,
                 system_infos: Optional[List[str]] = None,
                 vars_before: Optional[Dict[str, Any]] = None,
                 vars_after: Optional[Dict[str, Any]] = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(title_text)
        self.setMinimumSize(980, 640)
        self.setModal(False)

        self.content_blocks = [b for b in (content_blocks or []) if isinstance(b, str)]
        self.system_infos = [s for s in (system_infos or []) if isinstance(s, str)]
        self.vars_before = vars_before or {}
        self.vars_after = vars_after or {}

        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(6)

        # Top controls
        top_panel_layout = QHBoxLayout()
        top_panel_layout.addWidget(QLabel("Модель:"))
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(list(self.MODELS_INFO.keys()) + ["custom…"])
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        top_panel_layout.addWidget(self.model_combo, 2)

        self.token_spin = QSpinBox()
        self.token_spin.setRange(0, 10_000_000)
        self.token_spin.setSingleStep(1000)
        self.token_spin.valueChanged.connect(self._update_labels)
        self.token_spin.setVisible(False)
        top_panel_layout.addWidget(self.token_spin)

        self.price_spin = QDoubleSpinBox()
        self.price_spin.setDecimals(3)
        self.price_spin.setRange(0.0, 100.0)
        self.price_spin.setSingleStep(0.001)
        self.price_spin.valueChanged.connect(self._update_labels)
        self.price_spin.setSuffix(" $ / 1M")
        self.price_spin.setVisible(False)
        top_panel_layout.addWidget(self.price_spin)

        top_panel_layout.addStretch()

        self.separate_check = QCheckBox("Separate messages")
        self.separate_check.toggled.connect(self._render_center_text)
        top_panel_layout.addWidget(self.separate_check)

        self.token_label = QLabel()
        self.cost_label = QLabel()
        top_panel_layout.addWidget(self.token_label)
        top_panel_layout.addWidget(self.cost_label)
        root_layout.addLayout(top_panel_layout)

        # Middle layout: left vars, center content, right system infos
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(8)

        # Left: variable deltas
        self.left_panel = self._build_left_panel()
        middle_layout.addWidget(self.left_panel, 3)

        # Center: text (QTextEdit)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 10))
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {SyntaxStyleDark.TextEditBackground.name()};
                color: {SyntaxStyleDark.DefaultText.name()};
                border: 1px solid #3C3F41;
            }}""")
        middle_layout.addWidget(self.text_edit, 6)

        # Right: system infos
        self.right_panel = self._build_right_panel()
        middle_layout.addWidget(self.right_panel, 3)

        root_layout.addLayout(middle_layout, 1)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        root_layout.addWidget(button_box)

        # Initial renders
        self._render_center_text()
        self._on_model_changed()

    # Left panel with variable changes
    def _build_left_panel(self) -> QWidget:
        container = QScrollArea()
        container.setWidgetResizable(True)
        inner = QWidget()
        container.setWidget(inner)
        self.left_layout = QVBoxLayout(inner)
        self.left_layout.setAlignment(Qt.AlignTop)
        title = QLabel("Изменения переменных")
        title.setStyleSheet("color:#FFFFFF; font-weight: bold;")
        self.left_layout.addWidget(title)

        deltas = self._compute_var_deltas()
        if not deltas:
            self.left_layout.addWidget(QLabel("Нет изменений."))
        else:
            for item in deltas:
                self.left_layout.addWidget(self._build_var_delta_row(item))

        self.left_layout.addStretch()
        return container

    def _truncate(self, s: str, limit: int = 120) -> str:
        if s is None:
            return "None"
        s = str(s)
        return s if len(s) <= limit else s[:limit] + "…"

    def _open_overlay(self, title: str, content: str):
        dlg = PopupViewer(title, content, parent=self)
        dlg.exec()

    def _build_var_delta_row(self, item: Dict[str, Any]) -> QWidget:
        # item: {"name": str, "type": "changed"|"new", "old": Any, "new": Any}
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 2, 4, 2)
        key_lbl = QLabel(item["name"])
        key_lbl.setStyleSheet("color:#FFFFFF; font-weight:bold;")
        lay.addWidget(key_lbl)

        if item["type"] == "new":
            new_lbl = QLabel(f" = {self._truncate(repr(item['new']))}")
            new_lbl.setStyleSheet("color:#98C379;")  # green for new
            lay.addWidget(new_lbl, 1)
            if len(str(item["new"])) > 120:
                btn = QPushButton("показать полностью")
                btn.clicked.connect(lambda _=False, v=str(item['new']): self._open_overlay(item["name"], v))
                lay.addWidget(btn)
        else:
            old_s = self._truncate(repr(item["old"]))
            new_s = self._truncate(repr(item["new"]))
            old_lbl = QLabel(old_s)
            old_lbl.setStyleSheet("color:#ABB2BF;")  # white/gray
            arrow = QLabel(" → ")
            arrow.setStyleSheet("color:#ABB2BF;")
            new_lbl = QLabel(new_s)
            new_lbl.setStyleSheet("color:#61AFEF;")  # blue
            lay.addWidget(QLabel(":"))
            lay.addWidget(old_lbl, 1)
            lay.addWidget(arrow)
            lay.addWidget(new_lbl, 1)
            if len(str(item["old"])) > 120 or len(str(item["new"])) > 120:
                btn = QPushButton("показать полностью")
                btn.clicked.connect(lambda _=False, v=f"OLD:\n{item['old']}\n\nNEW:\n{item['new']}": self._open_overlay(item["name"], v))
                lay.addWidget(btn)
        return w

    def _compute_var_deltas(self) -> List[Dict[str, Any]]:
        b = self.vars_before or {}
        a = self.vars_after or {}
        deltas: List[Dict[str, Any]] = []
        all_keys = set(b.keys()) | set(a.keys())
        for k in sorted(all_keys):
            if k in b and k in a:
                if b[k] != a[k]:
                    deltas.append({"name": k, "type": "changed", "old": b[k], "new": a[k]})
            elif k not in b and k in a:
                deltas.append({"name": k, "type": "new", "old": None, "new": a[k]})
        return deltas

    # Right panel with system infos
    def _build_right_panel(self) -> QWidget:
        container = QVBoxLayoutWidget()
        title = QLabel("Системные сообщения (ADD_SYSTEM_INFO)")
        title.setStyleSheet("color:#FFFFFF; font-weight: bold;")
        container.layout.addWidget(title)

        self.sys_list = QListWidget()
        self.sys_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {SyntaxStyleDark.TextEditBackground.name()};
                color: {SyntaxStyleDark.DefaultText.name()};
                border: 1px solid #3C3F41;
            }}""")
        for s in (self.system_infos or []):
            text = s if len(s) <= 160 else s[:160] + "…"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, s)
            self.sys_list.addItem(item)
        self.sys_list.itemDoubleClicked.connect(self._on_sys_item_open)
        container.layout.addWidget(self.sys_list, 1)
        return container

    def _on_sys_item_open(self, item: QListWidgetItem):
        full = item.data(Qt.UserRole) or ""
        self._open_overlay("System Message", full)

    # Center text rendering
    def _render_center_text(self):
        if self.separate_check.isChecked():
            html_parts = []
            for i, block in enumerate(self.content_blocks or []):
                safe = self._escape_html(block)
                html_parts.append(f"<pre style='white-space:pre-wrap; font-family:Consolas; font-size:10pt; color:{SyntaxStyleDark.DefaultText.name()};'>{safe}</pre>")
                if i < len(self.content_blocks) - 1:
                    html_parts.append("<hr style='border:0; height:2px; background:#61AFEF; margin:8px 0;'>")
            html = "".join(html_parts) if html_parts else "<i>Нет данных</i>"
            self.text_edit.setHtml(html)
        else:
            joined = "\n".join(self.content_blocks or [])
            self.text_edit.setPlainText(joined)
        self._update_labels()

    def _on_model_changed(self):
        name = self.model_combo.currentText().strip()
        is_custom = name not in self.MODELS_INFO

        self.token_spin.setVisible(is_custom)
        self.price_spin.setVisible(is_custom)

        if is_custom:
            if not self.token_spin.isVisible():
                approx_tokens = self._rough_token_estimate(self._current_plain_text())
                self.token_spin.setValue(approx_tokens)
                self.price_spin.setValue(0.1)
        self._update_labels()

    def _current_plain_text(self) -> str:
        return self.text_edit.toPlainText() or ""

    def _count_tokens(self, text: str, model_name: str) -> int:
        info = self.MODELS_INFO.get(model_name)
        if tiktoken and info and info.get("encoding_name"):
            try:
                enc = tiktoken.get_encoding(info["encoding_name"])
                return len(enc.encode(text))
            except Exception:
                pass
        return self._rough_token_estimate(text)

    @staticmethod
    def _rough_token_estimate(text: str) -> int:
        words = re.findall(r"\w+", text, flags=re.UNICODE)
        if not words:
            return 0
        return math.ceil(len(text) / 2.5)

    def _update_labels(self):
        name = self.model_combo.currentText().strip()
        tokens = 0
        price_per_1M_tokens = 0.0

        content_text = self._current_plain_text()
        if name in self.MODELS_INFO:
            tokens = self._count_tokens(content_text, name)
            price_per_1M_tokens = self.MODELS_INFO[name]["price"]
        elif name == "custom…" or (name not in self.MODELS_INFO and self.token_spin.isVisible()):
            tokens = self.token_spin.value()
            price_per_1M_tokens = self.price_spin.value()
        else:
            tokens = self._rough_token_estimate(content_text)
            price_per_1M_tokens = 0.0

        cost = (tokens / 1_000_000) * price_per_1M_tokens
        self.token_label.setText(f"≈ {tokens:,} токенов".replace(",", " "))
        self.cost_label.setText(f"~ {cost:.4f} $")

    def _escape_html(self, s: str) -> str:
        return (s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

class QVBoxLayoutWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)