# File: app/utils/logger.py
import logging
import sys

editor_logger = logging.getLogger("PromptEditorPySideTabsWithDSL")
_pending_handlers = []

def setup_editor_logger():
    global editor_logger, _pending_handlers
    if not editor_logger.hasHandlers():
        editor_logger.setLevel(logging.INFO)
        
        console_handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
        console_handler.setFormatter(formatter)
        editor_logger.addHandler(console_handler)
        
        for handler in _pending_handlers:
            if not any(isinstance(h, type(handler)) for h in editor_logger.handlers):
                 editor_logger.addHandler(handler)
        _pending_handlers.clear()

    return editor_logger

def add_editor_log_handler(handler: logging.Handler):
    global editor_logger, _pending_handlers
    # 1) если это dsl_script и у него уже есть handler с name == "dsl_script_simple"
    if isinstance(handler, logging.StreamHandler) and \
       getattr(handler, "name", "") == "dsl_script_simple":
        # ничего не добавляем – он лаконичный и уже висит
        return

    # остальная логика прежняя
    if editor_logger.hasHandlers():
        if not any(isinstance(h, type(handler)) for h in editor_logger.handlers):
            editor_logger.addHandler(handler)
    else:
        if not any(isinstance(h, type(handler)) for h in _pending_handlers):
            _pending_handlers.append(handler)

editor_logger = setup_editor_logger()

def get_dsl_execution_logger():
    return logging.getLogger('dsl_execution')

def get_dsl_script_logger():
    return logging.getLogger('dsl_script')