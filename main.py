import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

current_dir = os.path.dirname(os.path.abspath(__file__)) 
project_root = os.path.dirname(current_dir)             


current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ui.main_window import PromptEditorWindow
from utils.logger import editor_logger 

def run_application():
    editor_logger.info("Запуск приложения Prompt Editor...")

    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
      QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
      QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    main_editor_window = PromptEditorWindow()
    main_editor_window.show()
    
    exit_code = app.exec()
    editor_logger.info(f"Приложение завершено с кодом: {exit_code}")
    sys.exit(exit_code)

if __name__ == "__main__":
    run_application()
