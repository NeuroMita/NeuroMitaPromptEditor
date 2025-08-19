import os, logging, shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QTreeView, QFileSystemModel, QMenu, QInputDialog,
    QMessageBox, QAbstractItemView
)
from PySide6.QtCore import QDir, Signal, Qt

from ui.file_tree_delegate import FileTreeDelegate

_log = logging.getLogger(__name__)


class FileTreePanel(QTreeView):
    """
    Левая панель с деревом файлов.

    Сигналы
    -------
    file_open_requested(str)  – двойной клик по текстовому/скриптовому файлу
    character_selected(str)   – id персонажа либо "" (если выбор вне Prompts)
    """
    file_open_requested = Signal(str)
    character_selected  = Signal(str)

    # ------------------------------------------------------------------ #

    def __init__(self, prompts_root: str | None, modified_paths_cb, parent=None):
        super().__init__(parent)
        self._prompts_root = prompts_root

        # ------- модель файловой системы -------
        self._model = QFileSystemModel(self)
        self._model.setReadOnly(False)                    # <— теперь можно писать
        self._model.setRootPath(prompts_root or QDir.homePath())

        self.setModel(self._model)
        self.setRootIndex(self._model.index(prompts_root or QDir.homePath()))

        # ------- делегат для иконок/жирного -------
        self.setItemDelegate(
            FileTreeDelegate(self, modified_paths_cb, lambda: self._prompts_root)
        )

        # прячем лишние колонки
        for i in range(1, self._model.columnCount()):
            self.hideColumn(i)

        # ------- сигналы двойного клика / выбора -------
        self.doubleClicked.connect(self._on_double_click)
        self.selectionModel().currentChanged.connect(self._on_select_changed)

        # ------- контекстное меню ПКМ -------
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_ctx_menu)

        # разрешаем F2-переименование
        self.setEditTriggers(
            QAbstractItemView.EditKeyPressed |
            QAbstractItemView.SelectedClicked
        )

    def update_prompts_root(self, new_prompts_root: str | None):
        _log.info(f"FileTreePanel: Обновление корневой папки Prompts на '{new_prompts_root}'")
        self._prompts_root = new_prompts_root # Обновляем внутренний _prompts_root
        
        actual_root_path_for_model = new_prompts_root if new_prompts_root else QDir.homePath()
        
        # Временно отключаем обработку сигнала изменения выделения, чтобы избежать побочных эффектов
        # во время сброса модели. Это необязательно, но может предотвратить гонки состояний.
        selection_model = self.selectionModel()
        try_disconnect = True
        if selection_model:
            try:
                selection_model.currentChanged.disconnect(self._on_select_changed)
            except RuntimeError: 
                try_disconnect = False
        else:
            try_disconnect = False

        self._model.setRootPath(actual_root_path_for_model)
        new_root_index = self._model.index(actual_root_path_for_model)
        self.setRootIndex(new_root_index)
        
        self.clearSelection() 

        if try_disconnect and selection_model:
            selection_model.currentChanged.connect(self._on_select_changed)

    # ------------------------------------------------------------------ #
    #                             СЛОТЫ
    # ------------------------------------------------------------------ #

    def _on_double_click(self, idx):
        if not idx.isValid():
            return
        path = self._model.filePath(idx)
        if os.path.isfile(path) and path.lower().endswith((".txt", ".script", ".postscript", ".system", ".json")):
            self.file_open_requested.emit(path)

    def _on_select_changed(self, idx, _prev):
        """
        Персонаж = первая подпапка после Prompts/*,
        даже если выбран файл внутри неё.
        """
        char_id = ""
        if idx.isValid() and self._prompts_root:
            try:
                path = Path(self._model.filePath(idx)).resolve()
                top  = path.relative_to(Path(self._prompts_root).resolve()).parts[0]
                if not top.startswith("_"):
                    char_id = top
            except ValueError:
                pass  # выбор вне Prompts
        self.character_selected.emit(char_id)

    # ------------------------------------------------------------------ #
    #                      КОНТЕКСТНОЕ  МЕНЮ  ПКМ
    # ------------------------------------------------------------------ #

    def _show_ctx_menu(self, pos):
        idx       = self.indexAt(pos)
        base_path = self._model.filePath(idx) if idx.isValid() else self._model.rootPath()
        target_dir = base_path if os.path.isdir(base_path) else os.path.dirname(base_path)

        menu = QMenu(self)
        act_new_file   = menu.addAction("Создать файл…")
        act_new_folder = menu.addAction("Создать папку…")

        from pathlib import Path
        char_dir_for_actions = None
        if self._prompts_root and os.path.isdir(target_dir):
            try:
                rp = Path(target_dir).resolve()
                pr = Path(self._prompts_root).resolve()
                if rp.parent == pr and not rp.name.startswith("_"):
                    char_dir_for_actions = str(rp)
            except Exception:
                char_dir_for_actions = None

        act_create_main_template = None
        act_create_cfg = None
        if char_dir_for_actions:
            mt_path = os.path.join(char_dir_for_actions, "main_template.txt")
            cfg_path = os.path.join(char_dir_for_actions, "config.json")
            if not os.path.exists(mt_path):
                act_create_main_template = menu.addAction("Создать main_template.txt")
            if not os.path.exists(cfg_path):
                act_create_cfg = menu.addAction("Создать config.json")

        menu.addSeparator()
        act_rename = menu.addAction("Переименовать…")
        act_delete = menu.addAction("Удалить")

        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen is None:
            return

        if act_create_main_template and chosen == act_create_main_template:
            self._create_main_template_in_char_dir(char_dir_for_actions)
            return
        if act_create_cfg and chosen == act_create_cfg:
            self._create_config_in_char_dir(char_dir_for_actions)
            return
        if chosen == act_new_file:
            self._create_file(target_dir)
        elif chosen == act_new_folder:
            self._create_dir(target_dir)
        elif chosen == act_rename and idx.isValid():
            self.edit(idx)
        elif chosen == act_delete and idx.isValid():
            self._delete_path(self._model.filePath(idx), idx)

    def _create_main_template_in_char_dir(self, char_dir: str):
        import io
        path = os.path.join(char_dir, "main_template.txt")
        if os.path.exists(path):
            return
        try:
            with io.open(path, "w", encoding="utf-8") as f:
                f.write("")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка создания", str(e))

    def _create_config_in_char_dir(self, char_dir: str):
        from utils.config_utils import compute_defaults_for_char, get_bounds_defaults, write_config_json
        try:
            char_id = os.path.basename(char_dir.rstrip("/\\"))
            cfg = compute_defaults_for_char(char_id)
            for k, v in get_bounds_defaults().items():
                cfg.setdefault(k, v)
            write_config_json(self._prompts_root, char_id, cfg)
            QMessageBox.information(self, "config.json", f"Создан:\n{os.path.join(char_dir, 'config.json')}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка создания", str(e))

    # ------------------------------------------------------------------ #
    #                           HELPERS
    # ------------------------------------------------------------------ #

    def _create_file(self, dir_path: str):
        name, ok = QInputDialog.getText(self, "Новый файл", "Имя файла:")
        if not ok or not name:
            return
        file_path = os.path.join(dir_path, name)
        if os.path.exists(file_path):
            QMessageBox.warning(self, "Файл уже существует", f"«{name}» уже есть.")
            return
        try:
            Path(file_path).touch()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка создания", str(e))

    def _create_dir(self, dir_path: str):
        name, ok = QInputDialog.getText(self, "Новая папка", "Имя папки:")
        if not ok or not name:
            return
        new_dir = os.path.join(dir_path, name)
        try:
            os.makedirs(new_dir, exist_ok=False)
        except FileExistsError:
            QMessageBox.warning(self, "Папка уже существует", f"«{name}» уже есть.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка создания папки", str(e))

    def _delete_path(self, path: str, idx):
        if QMessageBox.question(
            self,
            "Удаление",
            f"Удалить «{os.path.basename(path)}»?",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return

        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка удаления", str(e))
        else:
            # модель сама увидит изменения, но на всякий случай:
            self._model.remove(idx)
