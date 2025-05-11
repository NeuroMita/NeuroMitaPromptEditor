from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox,
    QHBoxLayout, QLabel, QComboBox, QSpinBox, QDoubleSpinBox
)
from PySide6.QtGui import QFont
import re
import math

try:
    import tiktoken
except ImportError:
    tiktoken = None

from app.syntax.styles import SyntaxStyleDark


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

    def __init__(self, title_text: str, content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title_text)
        self.setMinimumSize(720, 560)
        self.setModal(False)

        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(6)

        top_panel_layout = QHBoxLayout()

        top_panel_layout.addWidget(QLabel("Модель:"))

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(list(self.MODELS_INFO.keys()) + ["custom…"])
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        top_panel_layout.addWidget(self.model_combo, 2)

        self.token_spin = QSpinBox()
        self.token_spin.setRange(0, 10_000_000) # Можно увеличить диапазон, если нужно
        self.token_spin.setSingleStep(1000)
        self.token_spin.valueChanged.connect(self._update_labels)
        self.token_spin.setVisible(False)
        top_panel_layout.addWidget(self.token_spin)

        self.price_spin = QDoubleSpinBox()
        self.price_spin.setDecimals(3)  # Достаточно для цен типа 0.140 или 0.350
        self.price_spin.setRange(0.0, 100.0) # Диапазон цен за 1М токенов
        self.price_spin.setSingleStep(0.001) # Шаг для цен
        self.price_spin.valueChanged.connect(self._update_labels)
        self.price_spin.setSuffix(" $ / 1M") # Изменено
        self.price_spin.setVisible(False)
        top_panel_layout.addWidget(self.price_spin)

        top_panel_layout.addStretch()

        self.token_label = QLabel()
        self.cost_label = QLabel()
        top_panel_layout.addWidget(self.token_label)
        top_panel_layout.addWidget(self.cost_label)

        root_layout.addLayout(top_panel_layout)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(content)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 10))
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {SyntaxStyleDark.TextEditBackground.name()};
                color: {SyntaxStyleDark.DefaultText.name()};
                border: 1px solid #3C3F41;
            }}""")
        root_layout.addWidget(self.text_edit, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        root_layout.addWidget(button_box)

        self._on_model_changed() # Вызвать для инициализации с первой моделью

    def _on_model_changed(self):
        name = self.model_combo.currentText().strip()
        is_custom = name not in self.MODELS_INFO

        self.token_spin.setVisible(is_custom)
        self.price_spin.setVisible(is_custom)

        if is_custom:
            if not self.token_spin.isVisible(): # Если только что стал кастомным
                approx_tokens = self._rough_token_estimate(self.text_edit.toPlainText())
                self.token_spin.setValue(approx_tokens)
                self.price_spin.setValue(0.1) # Пример цены для кастомной модели, например $0.1/1M
        elif name in self.MODELS_INFO:
            # Сброс кастомных значений, если выбрана предопределенная модель
            # Этого не требуется, т.к. _update_labels возьмет значения из MODELS_INFO
            pass

        self._update_labels()

    def _count_tokens(self, text: str, model_name: str) -> int:
        info = self.MODELS_INFO.get(model_name)
        if tiktoken and info and info.get("encoding_name"):
            try:
                enc = tiktoken.get_encoding(info["encoding_name"])
                return len(enc.encode(text))
            except Exception:
                pass # fallback to rough estimate
        return self._rough_token_estimate(text)

    @staticmethod
    def _rough_token_estimate(text: str) -> int:
        # Этот метод можно улучшить, но для примера оставим как есть
        # Примерная оценка: 1 токен ~ 4 символа в английском тексте
        # или ~0.75 слова. Для русского может быть иначе.
        # Для простоты, оставим ваш вариант.
        words = re.findall(r"\w+", text, flags=re.UNICODE)
        if not words:
            return 0
        avg_word_len = sum(map(len, words)) / len(words)
        # Грубая эвристика: делим на 4 символа на токен, но для слов.
        # Можно также считать примерно 1.5-2 символа на токен для русского.
        # Или использовать len(text) / X, где X ~ 2-3 для русского.
        # Ваша эвристика была: math.ceil(len(words) * avg_word_len / 4)
        # Это примерно len(text_without_spaces) / 4
        # Более простой вариант: math.ceil(len(text) / 2.5) для русского текста
        return math.ceil(len(text) / 2.5) # Простая эвристика, можно настроить

    def _update_labels(self):
        name = self.model_combo.currentText().strip()
        tokens = 0
        price_per_1M_tokens = 0.0 # Цена за 1 миллион токенов

        if name in self.MODELS_INFO:
            tokens = self._count_tokens(self.text_edit.toPlainText(), name)
            price_per_1M_tokens = self.MODELS_INFO[name]["price"]
        elif name == "custom…" or (name not in self.MODELS_INFO and self.token_spin.isVisible()): # Учитываем кастомную модель
            tokens = self.token_spin.value()
            price_per_1M_tokens = self.price_spin.value()
        else: # Если введено что-то кастомное, но виджеты еще не показаны
            tokens = self._rough_token_estimate(self.text_edit.toPlainText())
            price_per_1M_tokens = 0.0 # По умолчанию 0, пока пользователь не введет

        cost = (tokens / 1_000_000) * price_per_1M_tokens # Изменена формула
        self.token_label.setText(f"≈ {tokens:,} токенов".replace(",", " "))
        self.cost_label.setText(f"~ {cost:.4f} $")


if __name__ == '__main__':
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    sample_content = """Это пример текста для подсчета токенов.
    Он содержит несколько строк и различные слова, включая русские и английские,
    а также цифры 12345 и знаки препинания!?.
    Попробуем оценить его стоимость для разных моделей.
    This is a sample text for token counting.
    It contains several lines and various words, including Russian and English,
    as well as numbers 12345 and punctuation marks!?.
    Let's try to estimate its cost for different models.
    """ * 50 # Увеличим текст для наглядности

    dialog = DslResultDialog("Результат DSL и стоимость", sample_content)
    dialog.exec()