"""
ui/prompt_sets_view.py

Экран выбора набора промтов для конкретного персонажа.
Показывается при клике на папку персонажа в дереве файлов.

Каждая карточка показывает:
 - Название набора
 - Автора из info.json
 - Версию из info.json
 - Количество файлов
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QInputDialog, QMessageBox,
)


_CARD_COLORS = [
    "#2a3a4a", "#3a2a4a", "#2a4a3a",
    "#4a3a2a", "#2a4a4a", "#4a2a3a",
    "#3a4a2a", "#4a2a4a",
]


class _SetCard(QFrame):
    """Карточка одного набора промтов."""

    clicked = Signal(str)  # set_id типа "Crazy/DefaultJson"

    def __init__(self, set_id: str, set_name: str, author: str,
                 version: str, file_count: int, color: str, parent=None):
        super().__init__(parent)
        self._set_id = set_id
        self._active = False
        self._base_color = color
        self.setFixedSize(180, 130)
        self.setCursor(Qt.PointingHandCursor)
        self._update_style(False)
        self._build(set_name, author, version, file_count)

    def _build(self, set_name: str, author: str, version: str, file_count: int):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(3)

        ico = QLabel("📋")
        ico.setStyleSheet("font-size: 20px; background: transparent;")
        ico.setAlignment(Qt.AlignCenter)
        lay.addWidget(ico)

        name_lbl = QLabel(set_name)
        name_lbl.setStyleSheet(
            "font-weight: bold; font-size: 12px; color: #e6edf3; background: transparent;"
        )
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setWordWrap(True)
        lay.addWidget(name_lbl)

        if author:
            auth_lbl = QLabel(author)
            auth_lbl.setStyleSheet(
                "font-size: 10px; color: #8b949e; background: transparent;"
            )
            auth_lbl.setAlignment(Qt.AlignCenter)
            auth_lbl.setWordWrap(True)
            lay.addWidget(auth_lbl)

        lay.addStretch()

        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)
        if version:
            ver_lbl = QLabel(f"v{version}")
            ver_lbl.setStyleSheet("font-size: 9px; color: #6e7681; background: transparent;")
            footer_row.addWidget(ver_lbl)
        footer_row.addStretch()
        if file_count:
            cnt_lbl = QLabel(f"{file_count} файл.")
            cnt_lbl.setStyleSheet("font-size: 9px; color: #6e7681; background: transparent;")
            footer_row.addWidget(cnt_lbl)
        lay.addLayout(footer_row)

    def _update_style(self, hover: bool):
        border_color = "#4a9eff" if self._active else ("#6e7681" if hover else "transparent")
        bg = self._base_color
        if hover and not self._active:
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
            self.clicked.emit(self._set_id)
        super().mousePressEvent(e)


class PromptSetsView(QWidget):
    """
    Экран наборов промтов для одного персонажа.

    Сигналы:
        set_chosen(str)  — пользователь выбрал набор (char_id типа "Crazy/DefaultJson")
    """

    set_chosen = Signal(str)

    def __init__(self, prompts_root: str, char_name: str, parent=None):
        super().__init__(parent)
        self._prompts_root = prompts_root
        self._char_name = char_name
        self._cards: dict[str, _SetCard] = {}
        self._build_ui()
        self._populate()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        header_row = QHBoxLayout()
        back_btn = QPushButton("← Персонажи")
        back_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #4a9eff;
                border: none; font-size: 12px; padding: 2px 6px;
            }
            QPushButton:hover { color: #79b8ff; }
        """)
        back_btn.clicked.connect(self._on_back)
        header_row.addWidget(back_btn)

        title = QLabel(f"Наборы промтов: {self._char_name}")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e6edf3; margin-left: 8px;")
        header_row.addWidget(title)
        header_row.addStretch()
        outer.addLayout(header_row)

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

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #6e7681; font-size: 11px;")
        outer.addWidget(self._status_lbl)

    def _on_back(self):
        """Возврат на страницу выбора персонажа."""
        # Найти родительский MainWindow и переключить его
        w = self.parent()
        while w:
            if hasattr(w, "_stack") and hasattr(w, "char_selector"):
                w._stack.setCurrentIndex(0)
                break
            w = w.parent() if hasattr(w, "parent") and callable(w.parent) else None

    def _populate(self):
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        entries = _scan_sets(self._prompts_root, self._char_name)
        col_count = 4

        for idx, entry in enumerate(entries):
            color = _CARD_COLORS[idx % len(_CARD_COLORS)]
            card = _SetCard(
                set_id=entry["id"],
                set_name=entry["set_name"],
                author=entry.get("author", ""),
                version=entry.get("version", ""),
                file_count=entry.get("file_count", 0),
                color=color,
            )
            card.clicked.connect(self._on_card_clicked)
            self._cards[entry["id"]] = card
            row, col = divmod(idx, col_count)
            self._grid_layout.addWidget(card, row, col)

        # Карточка "Создать новый набор"
        new_card = self._make_new_card()
        total = len(entries)
        row, col = divmod(total, col_count)
        self._grid_layout.addWidget(new_card, row, col)

        n = len(entries)
        self._status_lbl.setText(
            f"{n} набор{'а' if 2 <= n <= 4 else 'ов' if n >= 5 else ''}" if n else "Наборов не найдено"
        )

    def _make_new_card(self) -> QFrame:
        card = QFrame()
        card.setFixedSize(180, 130)
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
        lbl = QLabel("Новый набор")
        lbl.setStyleSheet("font-size: 11px; color: #6e7681; background: transparent;")
        lbl.setAlignment(Qt.AlignCenter)
        inner.addWidget(lbl)
        card.mousePressEvent = lambda e, c=card: self._on_create_set() if e.button() == Qt.LeftButton else None
        return card

    def _on_card_clicked(self, set_id: str):
        for cid, card in self._cards.items():
            card.set_active(cid == set_id)
        self.set_chosen.emit(set_id)

    def _on_create_set(self):
        name, ok = QInputDialog.getText(
            self, "Новый набор промтов",
            f"Название набора для персонажа «{self._char_name}»:"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        new_dir = Path(self._prompts_root) / self._char_name / name
        if new_dir.exists():
            QMessageBox.warning(self, "Уже существует", f"Папка «{name}» уже существует.")
            return
        try:
            new_dir.mkdir(parents=True)
            (new_dir / "main_template.txt").write_text("", encoding="utf-8")
            info = {
                "character": self._char_name,
                "author": "",
                "version": "1.0",
                "description": ""
            }
            (new_dir / "info.json").write_text(
                json.dumps(info, ensure_ascii=False, indent=4), encoding="utf-8"
            )
            self._populate()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать набор:\n{e}")


# ---------------------------------------------------------------------------
# Сканирование наборов для одного персонажа
# ---------------------------------------------------------------------------

def _scan_sets(prompts_root: str, char_name: str) -> list[dict]:
    """
    Возвращает список наборов промтов для персонажа char_name.

    Структуры:
      Prompts/CharName/main_template.txt          → id = "CharName"  (один набор, нет подпапок)
      Prompts/CharName/SetName/main_template.txt  → id = "CharName/SetName"
    """
    results: list[dict] = []
    char_dir = Path(prompts_root) / char_name
    if not char_dir.is_dir():
        return results

    # Прямой шаблон в папке персонажа
    if (char_dir / "main_template.txt").exists():
        results.append(_make_set_entry(char_name, char_name, char_dir))

    # Поддиректории — наборы
    for set_dir in sorted(char_dir.iterdir()):
        if not set_dir.is_dir() or set_dir.name.startswith("."):
            continue
        if (set_dir / "main_template.txt").exists():
            set_id = f"{char_name}/{set_dir.name}"
            results.append(_make_set_entry(set_id, set_dir.name, set_dir))

    return results


def _make_set_entry(set_id: str, set_name: str, folder: Path) -> dict:
    author = ""
    version = ""
    info_path = folder / "info.json"
    if info_path.exists():
        try:
            data = json.loads(info_path.read_text(encoding="utf-8"))
            author = data.get("author", "")
            version = str(data.get("version", ""))
        except Exception:
            pass

    file_count = sum(
        1 for f in folder.rglob("*")
        if f.is_file() and f.suffix in (".txt", ".script", ".postscript")
    )

    return {
        "id": set_id,
        "set_name": set_name,
        "author": author,
        "version": version,
        "file_count": file_count,
    }
