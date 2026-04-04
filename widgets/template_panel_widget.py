# widgets/template_panel_widget.py
"""
Dock-панель "Файлы шаблона".
Показывает список файлов из main_template.txt с иконками:
  🔗 — общий файл из Common/ (можно переопределить)
  📄 — файл персонажа
  ⚠️ — файл не найден
При клике на строку — открывает файл в редакторе.
Правый клик на Common-файле → "Скопировать в папку персонажа".
"""
from __future__ import annotations

import os
import shutil
import re
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QHBoxLayout, QMenu, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from utils.logger import editor_logger


class TemplatePanelDock(QDockWidget):
    """Панель файлов main_template.txt с указанием общих и персонажных файлов."""

    file_open_requested = Signal(str)  # абсолютный путь к файлу

    def __init__(self, parent=None):
        super().__init__("Файлы шаблона", parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)

        self._prompts_root: str | None = None
        self._char_id: str | None = None
        self._char_base_path: str | None = None
        self._refs: list[dict] = []

        container = QWidget()
        container.setStyleSheet("""
            QWidget { background: #1A1A1A; color: #E0E0E0; }
            QLabel { color: #E0E0E0; font-size: 9pt; }
            QListWidget {
                background: #1E1E1E; color: #E0E0E0;
                border: 1px solid #333; border-radius: 2px;
            }
            QListWidget::item { padding: 4px 6px; }
            QListWidget::item:selected { background: #2D4A6A; }
            QListWidget::item:hover { background: #2A2A2A; }
            QPushButton {
                background: #2A2A2A; color: #FFFFFF;
                border: 1px solid #444444; border-radius: 2px; padding: 5px 10px;
                font-size: 8.5pt;
            }
            QPushButton:hover { background: #353535; border-color: #666666; }
        """)

        root = QVBoxLayout(container)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # Заголовок с именем персонажа
        self._header_lbl = QLabel("Персонаж не выбран")
        self._header_lbl.setStyleSheet("font-weight: bold; font-size: 10pt; color: #AAAAAA;")
        root.addWidget(self._header_lbl)

        # Легенда
        legend_lbl = QLabel("🔗 Common/  📄 Персонажный  ⚠️ Не найден")
        legend_lbl.setStyleSheet("color: #777777; font-size: 8pt; padding: 2px 0;")
        root.addWidget(legend_lbl)

        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        root.addWidget(self._list)

        # Кнопка обновления
        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton("🔄 Обновить")
        self._refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self.setWidget(container)

    # --- Public API ---

    def load_for_char(self, prompts_root: str | None, char_id: str | None):
        """Загружает и отображает файлы шаблона для выбранного персонажа."""
        self._prompts_root = prompts_root
        self._char_id = char_id
        self._char_base_path = (
            os.path.join(prompts_root, char_id) if prompts_root and char_id else None
        )

        if not prompts_root or not char_id:
            self._header_lbl.setText("Персонаж не выбран")
            self._header_lbl.setStyleSheet("font-weight: bold; font-size: 10pt; color: #AAAAAA;")
            self._list.clear()
            self._refs = []
            return

        self._header_lbl.setText(f"🗂 {char_id} / main_template.txt")
        self._header_lbl.setStyleSheet("font-weight: bold; font-size: 10pt; color: #FFFFFF;")
        self.refresh()

    def refresh(self):
        """Перечитывает main_template.txt и обновляет список."""
        self._list.clear()
        self._refs = []

        if not self._char_base_path:
            return

        tmpl_path = os.path.join(self._char_base_path, "main_template.txt")
        if not os.path.isfile(tmpl_path):
            item = QListWidgetItem("⚠️ main_template.txt не найден")
            item.setForeground(Qt.gray)
            self._list.addItem(item)
            return

        from utils.template_inspector import parse_template_refs
        refs = parse_template_refs(tmpl_path, self._prompts_root, self._char_base_path)
        self._refs = refs

        for ref in refs:
            raw = ref["raw"]
            is_common = ref["is_common"]
            exists = ref["exists"]
            resolved = ref["resolved"]

            if not exists:
                icon = "⚠️"
                color = "#CC6666"
                tooltip = f"Файл не найден: {raw}"
            elif is_common:
                icon = "🔗"
                color = "#7FAADD"
                tooltip = f"Общий файл (Common). Можно скопировать в папку персонажа.\n{resolved}"
            else:
                icon = "📄"
                color = "#CCCCCC"
                tooltip = resolved

            item = QListWidgetItem(f"{icon} {raw}")
            item.setForeground(Qt.GlobalColor.white if not is_common else Qt.GlobalColor.cyan)
            item.setData(Qt.UserRole, ref)
            item.setToolTip(tooltip)
            font = item.font()
            font.setPointSize(9)
            item.setFont(font)
            # Цвет через stylesheet не работает на item, используем foreground
            from PySide6.QtGui import QColor
            item.setForeground(QColor(color))
            self._list.addItem(item)

        editor_logger.debug(f"TemplatePanelDock: загружено {len(refs)} файлов для '{self._char_id}'")

    # --- Slots ---

    def _on_item_double_clicked(self, item: QListWidgetItem):
        ref = item.data(Qt.UserRole)
        if not ref:
            return
        resolved = ref.get("resolved", "")
        if resolved and os.path.isfile(resolved):
            self.file_open_requested.emit(resolved)
        else:
            QMessageBox.warning(self, "Открытие файла", f"Файл не найден:\n{ref.get('raw', '')}")

    def _on_context_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return
        ref = item.data(Qt.UserRole)
        if not ref or not ref.get("is_common"):
            return  # контекстное меню только для Common-файлов

        menu = QMenu(self)
        copy_act = menu.addAction("📋 Скопировать в папку персонажа")
        open_act = menu.addAction("📂 Открыть файл")

        act = menu.exec(self._list.mapToGlobal(pos))
        if act == copy_act:
            self._copy_common_to_char(ref)
        elif act == open_act:
            self._on_item_double_clicked(item)

    def _copy_common_to_char(self, ref: dict):
        """Копирует Common-файл в папку персонажа (рядом с main_template.txt)."""
        if not self._char_base_path:
            return
        raw = ref["raw"]
        resolved = ref.get("resolved", "")
        if not resolved or not os.path.isfile(resolved):
            QMessageBox.warning(self, "Копирование", f"Исходный файл не найден:\n{raw}")
            return

        # Убираем ../ из пути и получаем имя файла для назначения
        # Например: ../../Common/Dialogue.txt → Common/Dialogue.txt (копируем рядом с персонажем)
        clean = re.sub(r"^(\.\./)+", "", raw)
        dest = os.path.normpath(os.path.join(self._char_base_path, clean))

        if os.path.exists(dest):
            ans = QMessageBox.question(
                self, "Файл существует",
                f"Файл уже существует:\n{dest}\n\nПерезаписать?",
                QMessageBox.Yes | QMessageBox.No
            )
            if ans != QMessageBox.Yes:
                return

        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(resolved, dest)
            editor_logger.info(f"TemplatePanelDock: скопирован {resolved} → {dest}")
            QMessageBox.information(
                self, "Скопировано",
                f"Файл скопирован в:\n{dest}\n\n"
                f"Теперь обновите ссылку в main_template.txt:\n"
                f"  [{raw}] → [{clean}]"
            )
        except Exception as e:
            editor_logger.error(f"TemplatePanelDock: ошибка копирования: {e}", exc_info=True)
            QMessageBox.critical(self, "Ошибка", f"Не удалось скопировать:\n{e}")
