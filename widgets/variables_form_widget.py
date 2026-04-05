"""
widgets/variables_form_widget.py

Визуальный редактор переменных DSL: слайдеры, чекбоксы, поля ввода.
Сохраняет совместимость с API QTextEdit через скрытый синхронизирующийся редактор.

Использование:
    form = VariablesFormWidget()
    form.load_from_text("attitude=60\nsecretExposed=false")
    text = form.to_text()   # "attitude=60\nsecretExposed=false"
"""
from __future__ import annotations

import re
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSlider, QSpinBox, QDoubleSpinBox, QCheckBox, QLineEdit,
    QTextEdit, QLabel, QScrollArea, QFrame, QPushButton,
    QSizePolicy, QTabWidget,
)

from syntax.styles import SyntaxStyleDark

# Тип переменной
_T_BOOL   = "bool"
_T_INT    = "int"
_T_FLOAT  = "float"
_T_STRING = "str"


def _infer_type(value: Any) -> str:
    if isinstance(value, bool): return _T_BOOL
    if isinstance(value, int):  return _T_INT
    if isinstance(value, float): return _T_FLOAT
    return _T_STRING


def _parse_value(raw: str) -> Any:
    """Парсит строку → Python-значение (как в main_window._parse_vars)."""
    s = raw.strip().strip("'\"")
    if s.lower() == "true":  return True
    if s.lower() == "false": return False
    try: return int(s)
    except ValueError: pass
    try: return float(s)
    except ValueError: pass
    return s


def _fmt_value(v: Any) -> str:
    if isinstance(v, bool): return str(v).lower()
    return str(v)


# --------------------------------------------------------------------------- #
#  Одна строка формы                                                           #
# --------------------------------------------------------------------------- #

class _VarRow(QWidget):
    """Одна строка: метка + редактор под тип переменной."""

    changed = Signal()  # emit когда значение изменилось

    def __init__(self, name: str, value: Any,
                 vmin: float | None = None, vmax: float | None = None,
                 parent=None):
        super().__init__(parent)
        self._name = name
        self._type = _infer_type(value)
        self._vmin = vmin
        self._vmax = vmax
        self._building = False
        self._build(value)

    # -- публичный API -------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    def get_value(self) -> Any:
        t = self._type
        if t == _T_BOOL:
            return self._cb.isChecked()
        if t == _T_INT:
            return int(self._spin.value())
        if t == _T_FLOAT:
            return float(self._dspin.value())
        return self._edit.text()

    def set_value(self, value: Any, silent: bool = False):
        self._building = silent
        try:
            t = self._type
            if t == _T_BOOL:
                self._cb.setChecked(bool(value))
            elif t == _T_INT:
                v = int(value)
                self._spin.setValue(v)
                if hasattr(self, "_slider"):
                    self._slider.setValue(v)
            elif t == _T_FLOAT:
                self._dspin.setValue(float(value))
            else:
                self._edit.setText(str(value))
        finally:
            self._building = False

    # -- построение виджета --------------------------------------------------

    def _build(self, value: Any):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 1, 0, 1)
        lay.setSpacing(6)
        t = self._type

        if t == _T_BOOL:
            self._cb = QCheckBox()
            self._cb.setChecked(bool(value))
            self._cb.toggled.connect(self._emit)
            lay.addWidget(self._cb)
            lay.addStretch()

        elif t == _T_INT:
            has_range = (self._vmin is not None and self._vmax is not None)
            lo = int(self._vmin if self._vmin is not None else 0)
            hi = int(self._vmax if self._vmax is not None else max(int(value) * 2 + 1, 200))
            v = int(value)

            self._spin = QSpinBox()
            self._spin.setRange(lo, hi)
            self._spin.setValue(v)
            self._spin.setFixedWidth(58)
            self._spin.setStyleSheet("QSpinBox { background: #1f2329; color: #e6edf3; }")

            if has_range:
                self._slider = QSlider(Qt.Horizontal)
                self._slider.setRange(lo, hi)
                self._slider.setValue(v)
                self._slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                self._slider.valueChanged.connect(self._on_slider)
                self._spin.valueChanged.connect(self._on_spin)
                lay.addWidget(self._slider)
            else:
                self._spin.valueChanged.connect(self._emit)

            lay.addWidget(self._spin)

        elif t == _T_FLOAT:
            lo = self._vmin if self._vmin is not None else 0.0
            hi = self._vmax if self._vmax is not None else 1.0
            self._dspin = QDoubleSpinBox()
            self._dspin.setRange(lo, hi)
            self._dspin.setSingleStep(0.01)
            self._dspin.setDecimals(3)
            self._dspin.setValue(float(value))
            self._dspin.setFixedWidth(80)
            self._dspin.setStyleSheet("QDoubleSpinBox { background: #1f2329; color: #e6edf3; }")
            self._dspin.valueChanged.connect(self._emit)
            lay.addWidget(self._dspin)
            lay.addStretch()

        else:  # str
            self._edit = QLineEdit(str(value))
            self._edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._edit.setStyleSheet("QLineEdit { background: #1f2329; color: #e6edf3; padding: 2px; }")
            self._edit.textChanged.connect(self._emit)
            lay.addWidget(self._edit)

    def _on_slider(self, v: int):
        if self._building: return
        self._building = True
        self._spin.setValue(v)
        self._building = False
        self.changed.emit()

    def _on_spin(self, v: int):
        if self._building: return
        self._building = True
        self._slider.setValue(v)
        self._building = False
        self.changed.emit()

    def _emit(self, *_):
        if not self._building:
            self.changed.emit()


# --------------------------------------------------------------------------- #
#  Основной виджет формы                                                       #
# --------------------------------------------------------------------------- #

class VariablesFormWidget(QWidget):
    """
    Визуальный редактор переменных.

    Совместимость с DslVariablesDock:
      - editor() → синхронный QTextEdit (скрытый)
      - textChanged сигнал — через editor().textChanged
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: dict[str, _VarRow] = {}
        self._bounds: dict[str, tuple[float, float]] = {}
        self._building = False          # защита от рекурсии
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._flush_to_editor)

        self._build_ui()

    # -- публичный API совместимости -----------------------------------------

    def editor(self) -> QTextEdit:
        """Скрытый QTextEdit, синхронный с формой (для обратной совместимости)."""
        return self._text_editor

    # -- загрузка/выгрузка ---------------------------------------------------

    def load_from_text(self, text: str):
        """Парсим key=value текст → заполняем форму."""
        self._building = True
        try:
            vars_dict = _parse_vars_text(text)
            # Обновляем или создаём строки
            for name, value in vars_dict.items():
                if name in self._rows:
                    self._rows[name].set_value(value, silent=True)
                else:
                    lo, hi = self._bounds.get(name, (None, None))
                    row = _VarRow(name, value, lo, hi)
                    row.changed.connect(self._on_any_changed)
                    self._rows[name] = row
            # Обновляем скрытый редактор без генерации сигнала
            self._text_editor.blockSignals(True)
            self._text_editor.setPlainText(text)
            self._text_editor.blockSignals(False)
            self._rebuild_form()
        finally:
            self._building = False

    def to_text(self) -> str:
        """Возвращает текущие переменные как key=value текст."""
        lines = []
        for name, row in self._rows.items():
            lines.append(f"{name}={_fmt_value(row.get_value())}")
        return "\n".join(lines)

    def set_bounds(self, bounds: dict[str, tuple[float, float]]):
        """Устанавливает диапазоны для переменных: {'attitude': (0, 100), ...}."""
        self._bounds = bounds

    def clear(self):
        self._rows.clear()
        self._building = True
        self._text_editor.blockSignals(True)
        self._text_editor.clear()
        self._text_editor.blockSignals(False)
        self._building = False
        self._rebuild_form()

    # -- построение UI -------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Вкладки: Форма / Код
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setStyleSheet("""
            QTabBar::tab { padding: 4px 12px; }
            QTabBar::tab:selected { border-bottom: 2px solid #4a9eff; }
        """)

        # --- Вкладка "Форма" ---
        form_container = QWidget()
        form_outer = QVBoxLayout(form_container)
        form_outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self._form_inner = QWidget()
        self._form_layout = QFormLayout(self._form_inner)
        self._form_layout.setContentsMargins(8, 6, 8, 6)
        self._form_layout.setSpacing(4)
        self._form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._form_inner.setStyleSheet("background: #1a1e24;")

        scroll.setWidget(self._form_inner)
        form_outer.addWidget(scroll)
        self._tabs.addTab(form_container, "⚙ Форма")

        # --- Вкладка "Код" ---
        self._text_editor = QTextEdit()
        self._text_editor.setFont(QFont("Consolas", 10))
        self._text_editor.setPlaceholderText("player_name='Тестер'\nattitude=100\nsecretExposed=false")
        self._text_editor.setStyleSheet(f"""
            QTextEdit {{
                background: {SyntaxStyleDark.TextEditBackground.name()};
                color: {SyntaxStyleDark.DefaultText.name()};
            }}""")
        self._text_editor.textChanged.connect(self._on_code_changed)
        self._tabs.addTab(self._text_editor, "< > Код")

        outer.addWidget(self._tabs)

    def _rebuild_form(self):
        """Перестраивает QFormLayout из self._rows."""
        # Удаляем все виджеты
        while self._form_layout.count():
            item = self._form_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        # Добавляем строки
        for name, row in self._rows.items():
            lbl = QLabel(name)
            lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._form_layout.addRow(lbl, row)

        if not self._rows:
            hint = QLabel("Персонаж не выбран")
            hint.setStyleSheet("color: #555; font-style: italic;")
            hint.setAlignment(Qt.AlignCenter)
            self._form_layout.addRow(hint)

    # -- сигналы / синхронизация ---------------------------------------------

    def _on_any_changed(self):
        """Форма изменилась → запускаем таймер синхронизации с кодовым редактором."""
        if not self._building:
            self._sync_timer.start(150)

    def _flush_to_editor(self):
        """Записываем текущее состояние формы в скрытый QTextEdit."""
        self._building = True
        self._text_editor.blockSignals(True)
        cursor = self._text_editor.textCursor()
        pos = cursor.position()
        self._text_editor.setPlainText(self.to_text())
        # Восстанавливаем позицию курсора
        cursor = self._text_editor.textCursor()
        cursor.setPosition(min(pos, len(self._text_editor.toPlainText())))
        self._text_editor.setTextCursor(cursor)
        self._text_editor.blockSignals(False)
        self._building = False
        # Посылаем сигнал изменения (QTextEdit.textChanged)
        self._text_editor.document().setModified(True)

    def _on_code_changed(self):
        """Код-вкладка изменилась → обновляем форму."""
        if self._building:
            return
        text = self._text_editor.toPlainText()
        self._building = True
        try:
            vars_dict = _parse_vars_text(text)
            changed = False
            for name, value in vars_dict.items():
                if name in self._rows:
                    self._rows[name].set_value(value, silent=True)
                else:
                    lo, hi = self._bounds.get(name, (None, None))
                    row = _VarRow(name, value, lo, hi)
                    row.changed.connect(self._on_any_changed)
                    self._rows[name] = row
                    changed = True
            if changed:
                self._rebuild_form()
        finally:
            self._building = False


# --------------------------------------------------------------------------- #
#  Утилиты                                                                     #
# --------------------------------------------------------------------------- #

def _parse_vars_text(text: str) -> dict[str, Any]:
    """Парсит key=value текст в словарь."""
    out: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = _parse_value(v.strip())
    return out
