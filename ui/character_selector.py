"""
ui/character_selector.py

Стартовый экран редактора: сетка карточек персонажей.
Заменяет пустой экран при запуске приложения.

Каждая карточка показывает:
 - Имя персонажа
 - Набор (Set), если есть
 - Версию из info.json (если доступна)
 - Количество файлов в папке
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QColor, QPalette, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QScrollArea, QFrame,
    QSizePolicy, QSpacerItem,
)


# Цвета карточек персонажей (циклически)
_CARD_COLORS = [
    "#2a3a4a", "#3a2a4a", "#2a4a3a",
    "#4a3a2a", "#2a4a4a", "#4a2a3a",
    "#3a4a2a", "#4a2a4a",
]


class _CharacterCard(QFrame):
    """Карточка одного персонажа/набора."""

    clicked = Signal(str)   # char_id (e.g. "Crazy/DefaultJson")

    def __init__(self, char_id: str, name: str, set_name: str | None,
                 version: str, file_count: int, color: str, parent=None):
        super().__init__(parent)
        self._char_id = char_id
        self._name = name
        self._set_name = set_name
        self._active = False

        self.setFixedSize(160, 120)
        self.setCursor(Qt.PointingHandCursor)
        self._base_color = color
        self._update_style(False)

        self._build(name, set_name, version, file_count)

    def _build(self, name: str, set_name: str | None, version: str, file_count: int):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(3)

        # Иконка + имя
        ico = QLabel("🎭")
        ico.setStyleSheet("font-size: 22px; background: transparent;")
        ico.setAlignment(Qt.AlignCenter)
        lay.addWidget(ico)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #e6edf3; background: transparent;"
        )
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setWordWrap(True)
        lay.addWidget(name_lbl)

        if set_name and set_name != name:
            set_lbl = QLabel(set_name)
            set_lbl.setStyleSheet(
                "font-size: 10px; color: #8b949e; background: transparent;"
            )
            set_lbl.setAlignment(Qt.AlignCenter)
            lay.addWidget(set_lbl)

        lay.addStretch()

        # Подвал: версия + кол-во файлов
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)
        if version:
            ver_lbl = QLabel(f"v{version}")
            ver_lbl.setStyleSheet("font-size: 9px; color: #6e7681; background: transparent;")
            footer_row.addWidget(ver_lbl)
        footer_row.addStretch()
        cnt_lbl = QLabel(f"{file_count} файл." if file_count else "")
        cnt_lbl.setStyleSheet("font-size: 9px; color: #6e7681; background: transparent;")
        footer_row.addWidget(cnt_lbl)
        lay.addLayout(footer_row)

    def _update_style(self, hover: bool):
        border_color = "#4a9eff" if self._active else ("#6e7681" if hover else "transparent")
        bg = self._base_color
        if hover and not self._active:
            # Немного светлее при наведении
            r, g, b = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
            r = min(r + 20, 255); g = min(g + 20, 255); b = min(b + 20, 255)
            bg = f"#{r:02x}{g:02x}{b:02x}"
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 2px solid {border_color};
                border-radius: 8px;
            }}
        """)

    def set_active(self, active: bool):
        self._active = active
        self._update_style(False)

    def enterEvent(self, e):
        self._update_style(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._update_style(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self._char_id)
        super().mousePressEvent(e)


class CharacterSelector(QWidget):
    """
    Стартовый экран редактора.

    Сигналы:
        character_chosen(str)  — пользователь нажал на карточку персонажа
        open_folder_requested  — кнопка «Открыть другую папку»
    """

    character_chosen     = Signal(str)   # char_id
    open_folder_requested = Signal()

    def __init__(self, prompts_root: str | None = None, parent=None):
        super().__init__(parent)
        self._prompts_root = prompts_root
        self._cards: dict[str, _CharacterCard] = {}
        self._selected: str | None = None

        self._build_ui()
        if prompts_root:
            self.reload(prompts_root)

    # -- публичный API -------------------------------------------------------

    def reload(self, prompts_root: str | None):
        """Перезагружает список персонажей из папки prompts_root."""
        self._prompts_root = prompts_root
        self._cards.clear()
        self._selected = None
        self._populate()

    def set_active_char(self, char_id: str | None):
        """Подсвечивает активную карточку."""
        for cid, card in self._cards.items():
            card.set_active(cid == char_id)
        self._selected = char_id

    # -- построение UI -------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        # Заголовок
        header_row = QHBoxLayout()
        title = QLabel("Мои персонажи")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #e6edf3;")
        header_row.addWidget(title)
        header_row.addStretch()

        self._btn_open_folder = QPushButton("📂 Открыть папку Prompts…")
        self._btn_open_folder.setStyleSheet("""
            QPushButton {
                background: #21262d; color: #8b949e;
                border: 1px solid #30363d; border-radius: 6px;
                padding: 5px 14px;
            }
            QPushButton:hover { background: #30363d; color: #e6edf3; }
        """)
        self._btn_open_folder.clicked.connect(self.open_folder_requested)
        header_row.addWidget(self._btn_open_folder)
        outer.addLayout(header_row)

        # Прокручиваемая область карточек
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(12)
        self._grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self._grid_widget)
        outer.addWidget(scroll, 1)

        # Статусная строка снизу
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #6e7681; font-size: 11px;")
        outer.addWidget(self._status_lbl)

    def _populate(self):
        """Очищает и заполняет сетку карточками."""
        # Удаляем старые карточки
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._prompts_root or not os.path.isdir(self._prompts_root):
            hint = QLabel("Папка Prompts не найдена.\nВыберите папку через кнопку выше.")
            hint.setStyleSheet("color: #6e7681; font-size: 13px; font-style: italic;")
            hint.setAlignment(Qt.AlignCenter)
            self._grid_layout.addWidget(hint, 0, 0)
            self._status_lbl.setText("")
            return

        entries = _scan_prompts(self._prompts_root)
        col_count = 5
        color_idx = 0

        for idx, entry in enumerate(entries):
            color = _CARD_COLORS[color_idx % len(_CARD_COLORS)]
            color_idx += 1
            card = _CharacterCard(
                char_id=entry["id"],
                name=entry["name"],
                set_name=entry.get("set"),
                version=entry.get("version", ""),
                file_count=entry.get("file_count", 0),
                color=color,
            )
            card.clicked.connect(self._on_card_clicked)
            self._cards[entry["id"]] = card
            row, col = divmod(idx, col_count)
            self._grid_layout.addWidget(card, row, col)

        # Кнопка «Создать нового персонажа»
        new_btn = self._make_new_card()
        total = len(entries)
        row, col = divmod(total, col_count)
        self._grid_layout.addWidget(new_btn, row, col)

        count = len(entries)
        self._status_lbl.setText(f"{count} персонаж{'а' if 2 <= count <= 4 else 'ей' if count >= 5 else ''}" if count else "Персонажей не найдено")

    def _make_new_card(self) -> QFrame:
        card = QFrame()
        card.setFixedSize(160, 120)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet("""
            QFrame {
                background: transparent;
                border: 2px dashed #30363d;
                border-radius: 8px;
            }
            QFrame:hover { border-color: #4a9eff; }
        """)
        inner = QVBoxLayout(card)
        inner.setAlignment(Qt.AlignCenter)
        plus = QLabel("+")
        plus.setStyleSheet("font-size: 28px; color: #6e7681; background: transparent;")
        plus.setAlignment(Qt.AlignCenter)
        inner.addWidget(plus)
        lbl = QLabel("Новый персонаж")
        lbl.setStyleSheet("font-size: 11px; color: #6e7681; background: transparent;")
        lbl.setAlignment(Qt.AlignCenter)
        inner.addWidget(lbl)
        # TODO: подключить создание нового персонажа
        return card

    def _on_card_clicked(self, char_id: str):
        self.set_active_char(char_id)
        self.character_chosen.emit(char_id)


# --------------------------------------------------------------------------- #
#  Сканирование папки Prompts                                                  #
# --------------------------------------------------------------------------- #

def _scan_prompts(root: str) -> list[dict]:
    """
    Сканирует папку Prompts и возвращает список персонажей.
    Поддерживает структуры:
      Prompts/CharName/main_template.txt           → {"id": "CharName", ...}
      Prompts/CharName/SetName/main_template.txt   → {"id": "CharName/SetName", ...}
    """
    results: list[dict] = []
    root_path = Path(root)

    if not root_path.is_dir():
        return results

    skip = {"Common", "_CommonPrompts", "_CommonScripts", "Archive", "Cartridges", "__pycache__"}

    for char_dir in sorted(root_path.iterdir()):
        if not char_dir.is_dir() or char_dir.name.startswith(".") or char_dir.name in skip:
            continue

        char_name = char_dir.name

        # Прямой main_template.txt в папке персонажа
        if (char_dir / "main_template.txt").exists():
            entry = _make_entry(char_name, char_name, None, char_dir)
            results.append(entry)

        # Поддиректории (наборы)
        for set_dir in sorted(char_dir.iterdir()):
            if not set_dir.is_dir() or set_dir.name.startswith("."):
                continue
            if (set_dir / "main_template.txt").exists():
                char_id = f"{char_name}/{set_dir.name}"
                entry = _make_entry(char_id, char_name, set_dir.name, set_dir)
                results.append(entry)

    return results


def _make_entry(char_id: str, name: str, set_name: str | None, folder: Path) -> dict:
    version = ""
    info_path = folder / "info.json"
    if info_path.exists():
        try:
            import json
            data = json.loads(info_path.read_text(encoding="utf-8"))
            version = data.get("version", "")
        except Exception:
            pass

    file_count = sum(1 for f in folder.rglob("*") if f.is_file() and f.suffix in (".txt", ".script", ".postscript"))

    return {
        "id": char_id,
        "name": name,
        "set": set_name,
        "version": str(version),
        "file_count": file_count,
    }
