from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QLabel,
    QTextEdit, QPushButton, QMessageBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, Signal
from syntax.styles import SyntaxStyleDark


class DslVariablesDock(QDockWidget):
    reset_requested = Signal()          # 🔄 сигнал наружу

    def __init__(self, parent=None):
        super().__init__("Параметры DSL", parent)
        self.setObjectName("DslVariablesDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._build()

    # ---------- helpers ----------
    def editor(self) -> QTextEdit:
        return self._editor

    # ---------- private ----------
    def _build(self):
        box = QWidget(self)
        lay = QVBoxLayout(box)

        lay.addWidget(QLabel("Начальные переменные (var=value …):"))

        self._editor = QTextEdit()
        self._editor.setFont(QFont("Consolas", 10))
        self._editor.setPlaceholderText("player_name='Тестер'\nattitude=100\nsecretExposed=false")
        self._editor.setStyleSheet(f"""
            QTextEdit {{
                background: {SyntaxStyleDark.TextEditBackground.name()};
                color: {SyntaxStyleDark.DefaultText.name()};
            }}""")
        lay.addWidget(self._editor)

        btn_reset = QPushButton("Сбросить 🔄")
        btn_reset.setToolTip("Загрузить значения из config.json (если есть), иначе — дефолты")
        btn_reset.clicked.connect(self._ask_reset)
        lay.addWidget(btn_reset)

        self._btn_save_cfg = QPushButton("Создать config.json 💾")
        self._btn_save_cfg.setEnabled(False)
        lay.addWidget(self._btn_save_cfg)

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