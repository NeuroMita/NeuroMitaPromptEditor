import os
from pathlib import Path
from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import QDir
from utils.logger import editor_logger # Используем наш настроенный логгер

def static_resolve_editor_hyperlink(prompts_root_abs_path_str: str, current_file_abs_path: str, link_target_in_placeholder: str) -> str | None:
    if not prompts_root_abs_path_str:
        editor_logger.error("Prompts root path not provided for hyperlink resolution.")
        return None

    prompts_root_path = Path(prompts_root_abs_path_str).resolve()
    current_file_path = Path(current_file_abs_path).resolve()
    resolved_path: Path
    
    link_target_cleaned = link_target_in_placeholder.strip()

    if link_target_cleaned.startswith(("_CommonPrompts/", "_CommonScripts/")):
        common_part = link_target_cleaned.lstrip('/')
        resolved_path = prompts_root_path / common_part
    else:
        try:
            relative_to_prompts = current_file_path.relative_to(prompts_root_path)
            if len(relative_to_prompts.parts) > 1 and not relative_to_prompts.parts[0].startswith("_"):
                char_id_folder_name = relative_to_prompts.parts[0]
                char_base_path = prompts_root_path / char_id_folder_name
                resolved_path = char_base_path / link_target_cleaned
            else:
                resolved_path = current_file_path.parent / link_target_cleaned
        except ValueError:
             editor_logger.warning(f"Current file '{current_file_path}' is not relative to prompts_root '{prompts_root_path}'. "
                                   f"Resolving '{link_target_cleaned}' relative to current file's directory.")
             resolved_path = current_file_path.parent / link_target_cleaned
    
    norm_resolved_path = str(resolved_path.resolve())
    editor_logger.debug(f"Static resolved path for link '{link_target_cleaned}' from '{current_file_abs_path}': '{norm_resolved_path}'")
    return norm_resolved_path

def select_prompts_directory_dialog(parent_widget, settings, prompts_dir_name, title_msg="Выберите корневую папку Prompts"):
    last_prompts_dir = settings.value("lastPromptsDir", QDir.homePath())
    directory = QFileDialog.getExistingDirectory(
        parent_widget, title_msg, last_prompts_dir
    )
    if directory:
        settings.setValue("lastPromptsDir", directory)
        editor_logger.info(f"Пользователь выбрал папку {prompts_dir_name}: {directory}")
        return str(Path(directory).resolve())
    return None

def find_or_ask_prompts_root(parent_widget, settings, prompts_dir_name, app_config_module_path):
    app_dir = Path(app_config_module_path).parent
    project_root_candidate = app_dir.parent      
    
    prompts_in_project_root = project_root_candidate / prompts_dir_name
    if prompts_in_project_root.is_dir():
        found_path = str(prompts_in_project_root.resolve())
        editor_logger.info(f"Папка '{prompts_dir_name}' найдена автоматически в корне проекта: {found_path}")
        settings.setValue("lastPromptsDir", found_path)
        return found_path

    current_dir_cwd = Path.cwd()
    prompts_in_cwd = current_dir_cwd / prompts_dir_name
    if prompts_in_cwd.is_dir():
        found_path = str(prompts_in_cwd.resolve())
        editor_logger.info(f"Папка '{prompts_dir_name}' найдена автоматически в текущей рабочей директории: {found_path}")
        settings.setValue("lastPromptsDir", found_path)
        return found_path
    
    editor_logger.warning(f"Папка '{prompts_dir_name}' не найдена автоматически.")
    chosen_dir = select_prompts_directory_dialog(parent_widget, settings, prompts_dir_name,
                                                 title_msg=f"Папка {prompts_dir_name} не найдена. Пожалуйста, выберите ее:")
    # select_prompts_directory_dialog уже сохраняет в настройки, если пользователь выбрал
    if chosen_dir:
        return chosen_dir
    return None