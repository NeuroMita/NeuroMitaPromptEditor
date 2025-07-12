from PySide6.QtCore import Qt, QFileInfo
from PySide6.QtGui import QFont, QColor, QIcon
from PySide6.QtWidgets import QStyledItemDelegate, QApplication, QStyle
from pathlib import Path

class FileTreeDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, modified_files_resolver=None, prompts_root_resolver=None):
        super().__init__(parent)
        self.modified_files_resolver = modified_files_resolver
        self.prompts_root_resolver   = prompts_root_resolver

        self.script_icon = QIcon.fromTheme("applications-engineering")
        if self.script_icon.isNull():
            self.script_icon = QIcon.fromTheme("preferences-system")
        if self.script_icon.isNull():
            self.script_icon = QIcon.fromTheme("applications-utilities")
        if self.script_icon.isNull():
            self.script_icon = QIcon.fromTheme("configure")
        if self.script_icon.isNull():
            self.script_icon = QIcon.fromTheme("system-settings")
        if self.script_icon.isNull():
            self.script_icon = QIcon.fromTheme("gnome-settings")
        if self.script_icon.isNull():
            self.script_icon = QApplication.style().standardIcon(
                QStyle.StandardPixmap.SP_FileDialogDetailedView
            )

        self.character_folder_icon = QIcon.fromTheme("user-home")
        if self.character_folder_icon.isNull():
            self.character_folder_icon = QIcon.fromTheme("folder-user")
        if self.character_folder_icon.isNull():
            self.character_folder_icon = QIcon.fromTheme("folder-saved-search")
        if self.character_folder_icon.isNull():
            self.character_folder_icon = QApplication.style().standardIcon(
                QStyle.StandardPixmap.SP_DirHomeIcon
            )
        if self.character_folder_icon.isNull():
            self.character_folder_icon = QApplication.style().standardIcon(
                QStyle.StandardPixmap.SP_DirIcon
            )

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)

        file_info = index.model().fileInfo(index)
        file_path = index.model().filePath(index)

        # специальная иконка для *.script
        if file_info.isFile() and file_info.suffix().lower() == "script":
            if not self.script_icon.isNull():
                option.icon = self.script_icon
        elif file_info.isFile() and file_info.suffix().lower() == "postscript":
            if not self.script_icon.isNull():
                option.icon = self.script_icon

        # персонаж-папка Prompts/*
        elif file_info.isDir() and self.prompts_root_resolver:
            prompts_root_str = self.prompts_root_resolver()
            if prompts_root_str:
                try:
                    prompts_root_path = Path(prompts_root_str).resolve()
                    current_dir_path  = Path(file_path).resolve()

                    if ( current_dir_path.parent == prompts_root_path
                         and not current_dir_path.name.startswith("_")
                         and current_dir_path != prompts_root_path ):
                        if not self.character_folder_icon.isNull():
                            option.icon = self.character_folder_icon
                except Exception:
                    pass  # не удалось корректно обработать путь

        # жирный шрифт для изменённых файлов
        if self.modified_files_resolver:
            modified_files    = self.modified_files_resolver()
            current_file_path = index.model().filePath(index)
            option.font.setBold(current_file_path in modified_files)
