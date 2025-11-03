# ui/node_graph_window.py
from __future__ import annotations
from typing import Optional, Callable

from PySide6.QtWidgets import QMainWindow, QToolBar, QMessageBox, QFileDialog
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt

from ui.node_graph.editor_widget import NodeGraphEditor


class NodeGraphWindow(QMainWindow):
    """
    Полноценное окно (не диалог) для нодового редактора.
    Позволяет:
      - загружать текст;
      - редактировать граф;
      - применить изменения в вызывающий редактор (callback);
      - сохранить в файл (по желанию).
    """
    def __init__(self, initial_text: str, file_path: Optional[str], prompts_root: Optional[str],
                 apply_callback: Optional[Callable[[str], None]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Нодовый редактор .script")
        self.resize(1280, 860)

        self._file_path = file_path
        self._apply_cb = apply_callback

        base_dir = None
        if file_path:
            import os
            base_dir = os.path.dirname(file_path)

        self.editor = NodeGraphEditor(base_dir=base_dir, prompts_root=prompts_root, parent=self)
        self.setCentralWidget(self.editor)
        self.editor.load_text(initial_text or "")

        tb = QToolBar("Действия", self)
        self.addToolBar(Qt.TopToolBarArea, tb)

        act_apply = QAction("Применить в редактор", self)
        act_apply.triggered.connect(self._apply_to_editor)
        tb.addAction(act_apply)

        act_save = QAction("Сохранить в файл", self)
        act_save.triggered.connect(self._save_as_file)
        tb.addAction(act_save)

        act_refresh = QAction("Пересобрать граф из текста", self)
        act_refresh.triggered.connect(self.editor._rebuild_from_preview_text)
        tb.addAction(act_refresh)

    def _apply_to_editor(self):
        txt = self.editor.export_text()
        if self._apply_cb:
            try:
                self._apply_cb(txt)
            except Exception as e:
                QMessageBox.critical(self, "Применение", str(e))

    def _save_as_file(self):
        start = self._file_path or ""
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить .script", start, "Файлы скриптов (*.script);;Все файлы (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.export_text())
            QMessageBox.information(self, "Сохранено", path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))