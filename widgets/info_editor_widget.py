# widgets/info_editor_widget.py
"""
Dock-виджет для редактирования info.json персонажа.
Поля: character, author, version, description.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QPushButton, QLabel, QMessageBox
)
from PySide6.QtCore import Qt

from utils.logger import editor_logger


class InfoEditorDock(QDockWidget):
    """Панель редактирования info.json текущего персонажа."""

    def __init__(self, parent=None):
        super().__init__("Информация о промпте", parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)

        self._prompts_root: str | None = None
        self._char_id: str | None = None

        container = QWidget()
        container.setStyleSheet("""
            QWidget { background: #1A1A1A; color: #E0E0E0; }
            QLabel { color: #E0E0E0; font-size: 9pt; }
            QLineEdit {
                background: #2A2A2A; color: #FFFFFF;
                border: 1px solid #444444; border-radius: 2px; padding: 4px;
            }
            QTextEdit {
                background: #2A2A2A; color: #FFFFFF;
                border: 1px solid #444444; border-radius: 2px; padding: 4px;
            }
            QPushButton {
                background: #2A2A2A; color: #FFFFFF;
                border: 1px solid #444444; border-radius: 2px; padding: 6px 12px;
            }
            QPushButton:hover { background: #353535; border-color: #666666; }
            QPushButton:pressed { background: #1A1A1A; }
        """)

        root = QVBoxLayout(container)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Заголовок
        self._title_lbl = QLabel("Персонаж не выбран")
        self._title_lbl.setStyleSheet("font-weight: bold; font-size: 10pt; color: #AAAAAA;")
        root.addWidget(self._title_lbl)

        # Форма
        form = QFormLayout()
        form.setSpacing(6)

        self._char_edit = QLineEdit()
        self._char_edit.setPlaceholderText("Имя персонажа")

        self._author_edit = QLineEdit()
        self._author_edit.setPlaceholderText("Автор промпта")

        self._version_edit = QLineEdit()
        self._version_edit.setPlaceholderText("1.0")

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Описание промпта...")
        self._desc_edit.setMaximumHeight(120)
        self._desc_edit.setMinimumHeight(60)

        form.addRow(QLabel("Персонаж:"), self._char_edit)
        form.addRow(QLabel("Автор:"), self._author_edit)
        form.addRow(QLabel("Версия:"), self._version_edit)
        form.addRow(QLabel("Описание:"), self._desc_edit)

        root.addLayout(form)

        # Кнопка сохранения
        self._save_btn = QPushButton("Сохранить info.json 💾")
        self._save_btn.clicked.connect(self._save)
        self._save_btn.setEnabled(False)
        root.addWidget(self._save_btn)
        root.addStretch(1)

        self.setWidget(container)

    # --- Public API ---

    def load_for_char(self, prompts_root: str | None, char_id: str | None):
        """Загружает info.json для выбранного персонажа."""
        self._prompts_root = prompts_root
        self._char_id = char_id

        if not prompts_root or not char_id:
            self._title_lbl.setText("Персонаж не выбран")
            self._title_lbl.setStyleSheet("font-weight: bold; font-size: 10pt; color: #AAAAAA;")
            self._clear_fields()
            self._save_btn.setEnabled(False)
            return

        from utils.config_utils import read_info_json
        data = read_info_json(prompts_root, char_id)

        self._title_lbl.setText(f"📄 {char_id}")
        self._title_lbl.setStyleSheet("font-weight: bold; font-size: 10pt; color: #FFFFFF;")

        self._char_edit.setText(data.get("character", ""))
        self._author_edit.setText(data.get("author", ""))
        self._version_edit.setText(data.get("version", ""))
        self._desc_edit.setPlainText(data.get("description", ""))

        self._save_btn.setEnabled(True)
        editor_logger.debug(f"InfoEditorDock: загружен info.json для '{char_id}'")

    # --- Slots ---

    def _clear_fields(self):
        self._char_edit.clear()
        self._author_edit.clear()
        self._version_edit.clear()
        self._desc_edit.clear()

    def _save(self):
        if not self._prompts_root or not self._char_id:
            QMessageBox.warning(self, "info.json", "Персонаж не выбран.")
            return

        data = {
            "character": self._char_edit.text().strip(),
            "author": self._author_edit.text().strip(),
            "version": self._version_edit.text().strip(),
            "description": self._desc_edit.toPlainText().strip(),
        }
        try:
            from utils.config_utils import write_info_json
            write_info_json(self._prompts_root, self._char_id, data)
            editor_logger.info(f"InfoEditorDock: info.json сохранён для '{self._char_id}'")
            QMessageBox.information(self, "info.json", "Сохранено успешно.")
        except Exception as e:
            editor_logger.error(f"InfoEditorDock: ошибка сохранения: {e}", exc_info=True)
            QMessageBox.critical(self, "info.json", f"Ошибка сохранения:\n{e}")
