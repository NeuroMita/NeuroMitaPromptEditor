import logging
import sys
from app.core.config import DSL_LOG_DIR # Import for consistency if needed

# General API logger
api_logger = logging.getLogger("PromptEditorAPI")
api_logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
console_handler.setFormatter(formatter)
if not api_logger.hasHandlers():
    api_logger.addHandler(console_handler)

# You might want to configure dsl_execution_logger and dsl_script_logger
# from dsl_engine.py here as well, or ensure dsl_engine.py's setup is robust.
# For now, dsl_engine.py handles its own logging setup.
# If you want to capture DSL logs for API responses, you'll need a custom handler.

class ListLogHandler(logging.Handler):
    def __init__(self, log_list):
        super().__init__()
        self.log_list = log_list

    def emit(self, record):
        # For dsl_script, we often want the raw message
        if record.name == "dsl_script":
            msg = record.getMessage()
        else:
            msg = self.format(record)
        self.log_list.append({"level": record.levelname, "message": msg, "name": record.name, "timestamp": record.asctime})

def get_dsl_logs_for_request():
    """
    Call this before processing a DSL request to capture logs for that specific request.
    Returns a list and the handler. Remember to remove the handler afterwards.
    """
    log_list = []
    list_handler = ListLogHandler(log_list)
    
    # Configure formatter for list_handler if different from default
    # Example: Only message for dsl_script, full format for dsl_execution
    list_handler.setFormatter(logging.Formatter('%(asctime)s |%(character_id)s| %(name)s - %(levelname)s - %(message)s'))
    
    dsl_exec_logger = logging.getLogger('dsl_execution')
    dsl_script_logger = logging.getLogger('dsl_script')

    dsl_exec_logger.addHandler(list_handler)
    dsl_script_logger.addHandler(list_handler)
    
    return log_list, list_handler

def remove_list_log_handler(handler):
    dsl_exec_logger = logging.getLogger('dsl_execution')
    dsl_script_logger = logging.getLogger('dsl_script')
    dsl_exec_logger.removeHandler(handler)
    dsl_script_logger.removeHandler(handler)