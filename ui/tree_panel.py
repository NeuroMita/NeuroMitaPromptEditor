import os, logging
from pathlib import Path
from PySide6.QtWidgets import QTreeView, QFileSystemModel
from PySide6.QtCore    import QDir, Signal
from app.ui.file_tree_delegate import FileTreeDelegate

_log = logging.getLogger(__name__)


class FileTreePanel(QTreeView):
    """
    Левая панель с деревом файлов. Излучает:
      • file_open_requested(str)  – двойной клик по открытому файлу
      • character_selected(str)   – id персонажа или "" (если вне Prompts)
    """
    file_open_requested = Signal(str)
    character_selected  = Signal(str)

    def __init__(self, prompts_root: str | None, modified_paths_cb, parent=None):
        super().__init__(parent)
        self._prompts_root = prompts_root

        self._model = QFileSystemModel(self)
        self._model.setRootPath(prompts_root or QDir.homePath())
        self.setModel(self._model)
        self.setRootIndex(self._model.index(prompts_root or QDir.homePath()))

        # окраска изменённых файлов
        self.setItemDelegate(
            FileTreeDelegate(self, modified_paths_cb, lambda: self._prompts_root)
        )
        for i in range(1, self._model.columnCount()):
            self.hideColumn(i)

        # сигналы
        self.doubleClicked.connect(self._on_double_click)
        self.selectionModel().currentChanged.connect(self._on_select_changed)

    # ---------- slots ----------
    def _on_double_click(self, idx):
        if not idx.isValid():
            return
        path = self._model.filePath(idx)
        if os.path.isfile(path) and path.lower().endswith((".txt", ".script")):
            self.file_open_requested.emit(path)

    def _on_select_changed(self, idx, _prev):
        """
        Определяем персонажа как первую подпапку после Prompts/*,
        даже если пользователь кликает файл внутри неё.
        """
        char_id = ""
        if idx.isValid() and self._prompts_root:
            try:
                path = Path(self._model.filePath(idx)).resolve()
                top  = path.relative_to(Path(self._prompts_root).resolve()).parts[0]
                if not top.startswith("_"):                # пропускаем служебные
                    char_id = top
            except ValueError:
                pass  # выбор вне Prompts
        self.character_selected.emit(char_id)