from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, Signal

from widgets.variables_form_widget import VariablesFormWidget


class DslVariablesDock(QDockWidget):
    reset_requested = Signal()

    def __init__(self, parent=None):
        super().__init__("Параметры DSL", parent)
        self.setObjectName("DslVariablesDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._build()

    # ---------- API совместимости с main_window.py ----------

    def editor(self) -> QTextEdit:
        """Возвращает скрытый QTextEdit (синхронный с формой)."""
        return self._form.editor()

    # ---------- private ----------

    def _build(self):
        box = QWidget(self)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # Основная форма (Форма / Код)
        self._form = VariablesFormWidget()
        lay.addWidget(self._form, 1)

        # Кнопки управления
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        btn_reset = QPushButton("Сбросить 🔄")
        btn_reset.setToolTip("Загрузить значения из config.json (если есть), иначе — дефолты")
        btn_reset.clicked.connect(self._ask_reset)
        btn_row.addWidget(btn_reset)

        self._btn_save_cfg = QPushButton("Создать config.json 💾")
        self._btn_save_cfg.setEnabled(False)
        btn_row.addWidget(self._btn_save_cfg)

        lay.addLayout(btn_row)
        self.setWidget(box)

    def _ask_reset(self):
        if QMessageBox.question(
            self, "Сброс переменных",
            "Загрузить значения из config.json (если есть)?\nЕсли файла нет — применить стандартные значения.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) == QMessageBox.Yes:
            self.reset_requested.emit()

    def set_on_save_clicked(self, callback):
        try:
            self._btn_save_cfg.clicked.disconnect()
        except Exception:
            pass
        self._btn_save_cfg.clicked.connect(callback)

    def set_save_enabled(self, enabled: bool):
        self._btn_save_cfg.setEnabled(bool(enabled))

    def update_save_button_text(self, exists: bool):
        self._btn_save_cfg.setText("Сохранить config.json 💾" if exists else "Создать config.json 💾")

    def set_bounds(self, bounds: dict):
        """Передаём диапазоны переменных (для слайдеров)."""
        self._form.set_bounds(bounds)

    def load_vars_text(self, text: str):
        """
        Загружает текст переменных в форму и синхронный редактор.
        Используется вместо editor().blockSignals + setPlainText.
        """
        self._form.load_from_text(text)

    def clear_vars(self):
        """Очищает форму и редактор."""
        self._form.clear()
