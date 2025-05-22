import os, logging
from pathlib import Path
from PySide6.QtCore import Qt, QFile, QTextStream, QStringConverter, QFileInfo, Signal
from PySide6.QtWidgets import (
    QTabWidget, QMessageBox, QFileDialog
)
from PySide6.QtGui import QFont, QTextCursor
from widgets.custom_text_edit import CustomTextEdit
from syntax.styles import SyntaxStyleDark
from syntax.highlighter import PromptSyntaxHighlighter
from utils.path_helpers import static_resolve_editor_hyperlink

_log = logging.getLogger(__name__)


class TabManager(QTabWidget):
    modified_set_changed = Signal()     # когда self._modified_paths меняется

    def __init__(self, prompts_root_cb, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.tabCloseRequested.connect(self._on_close_tab)

        self._prompts_root_cb = prompts_root_cb
        self._modified_paths: set[str] = set()

    # ------------------------------------------------ public
    def modified_paths(self): return self._modified_paths

    def open_file(self, file_path: str):
        for i in range(self.count()):
            ed = self._editor(i)
            if ed and os.path.normpath(ed.get_tab_file_path()) == os.path.normpath(file_path):
                self.setCurrentIndex(i)
                return
        try:
            qf = QFile(file_path)
            if not qf.open(QFile.ReadOnly | QFile.Text):
                QMessageBox.warning(self, "Открытие", f"Не удалось открыть:\n{file_path}")
                return
            stream = QTextStream(qf)
            stream.setEncoding(QStringConverter.Encoding.Utf8)
            content = stream.readAll()
            qf.close()
            content = content.replace('\x00', '').rstrip()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
            return

        ed = CustomTextEdit()
        ed.setFont(QFont("Consolas", 11))
        ed.set_tab_file_path(file_path)
        ed.setLineWrapMode(CustomTextEdit.LineWrapMode.NoWrap)
        ed.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        ed.setStyleSheet(f"""
            CustomTextEdit {{
                background: {SyntaxStyleDark.TextEditBackground.name()};
                color: {SyntaxStyleDark.DefaultText.name()};
            }}""")
        hl = PromptSyntaxHighlighter(
            ed.document(),
            current_doc_path_resolver=lambda p=file_path: p,
            prompts_root_resolver=self._prompts_root_cb,
            hyperlink_resolver=static_resolve_editor_hyperlink
        )
        ed.set_highlighter(hl)
        ed.open_file_requested.connect(self.open_file)
        ed.save_requested.connect(lambda _: self._save_editor(ed, False))

        idx = self.addTab(ed, QFileInfo(file_path).fileName())
        self.setCurrentIndex(idx)
        ed.document().modificationChanged.connect(lambda m, e=ed: self._on_mod(e, m))
        ed.setPlainText(content)

        cursor = ed.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        ed.setTextCursor(cursor)

        ed.verticalScrollBar().setValue(ed.verticalScrollBar().minimum())
        ed.horizontalScrollBar().setValue(ed.horizontalScrollBar().minimum())

        ed.document().setModified(False)

    def save_current(self):    self._save_idx(self.currentIndex(), False)
    def save_current_as(self): self._save_idx(self.currentIndex(), True)
    def save_all(self):
        for i in range(self.count()):
            ed = self._editor(i)
            if ed and ed.document().isModified():
                if not self._save_editor(ed, False):
                    break

    # ------------------------------------------------ private utils
    def _editor(self, idx): return self.widget(idx) if isinstance(self.widget(idx), CustomTextEdit) else None

    def _on_mod(self, ed, mod):
        path = ed.get_tab_file_path()
        if path:
            (self._modified_paths.add if mod else self._modified_paths.discard)(path)
            self.modified_set_changed.emit()

        for i in range(self.count()):
            if self.widget(i) == ed:
                base = QFileInfo(path).fileName() if path else "Новый файл"
                self.setTabText(i, f"{base}{'*' if mod else ''}")

    def _on_close_tab(self, idx):
        ed = self._editor(idx)
        if ed and ed.document().isModified():
            r = QMessageBox.question(self, "Сохранить?",
                "Файл изменён. Сохранить?", QMessageBox.Yes|QMessageBox.No|QMessageBox.Cancel, QMessageBox.Yes)
            if r == QMessageBox.Cancel:
                return
            if r == QMessageBox.Yes and not self._save_editor(ed, False):
                return
        self.removeTab(idx)

    # --- save helpers
    def _save_idx(self, idx, as_mode): self._save_editor(self._editor(idx), as_mode)

    def _save_editor(self, ed: CustomTextEdit | None, save_as) -> bool:
        if not ed:
            return False
        path = ed.get_tab_file_path()
        if save_as or not path:
            new_path, _ = QFileDialog.getSaveFileName(
                self, "Сохранить как", path or "",
                "Текстовые файлы (*.txt);;Файлы скриптов (*.script);;Все файлы (*)"
            )
            if not new_path:
                return False
            path = new_path
            ed.set_tab_file_path(path)
            for i in range(self.count()):
                if self.widget(i) == ed:
                    self.setTabText(i, QFileInfo(path).fileName())
                    break
        try:
            qf = QFile(path)
            if not qf.open(QFile.WriteOnly | QFile.Text | QFile.Truncate):
                raise RuntimeError(qf.errorString())
            s = QTextStream(qf)
            s.setEncoding(QStringConverter.Encoding.Utf8)
            clean_text = ed.toPlainText().replace('\x00', '')
            s << clean_text
            qf.close()
            ed.document().setModified(False)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n{e}")
            return False