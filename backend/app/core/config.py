import os
from pathlib import Path

# Determine the project root dynamically (assuming config.py is in backend/app/core)
# backend_root / app / core / config.py
# So, project_root is three levels up from this file's directory.
# More robust: backend_root = Path(__file__).resolve().parent.parent.parent
# prompts_root should ideally be outside the app code, but for simplicity:
APP_DIR = Path(__file__).resolve().parent.parent # backend/app/
BACKEND_ROOT_DIR = APP_DIR.parent # backend/
PROMPTS_ROOT_PATH_STR = os.getenv("PROMPTS_ROOT_PATH", str(BACKEND_ROOT_DIR / "Prompts"))

# Ensure PROMPTS_ROOT_PATH is an absolute path
PROMPTS_ROOT_PATH = Path(PROMPTS_ROOT_PATH_STR).resolve()

# Create the Prompts directory if it doesn't exist
PROMPTS_ROOT_PATH.mkdir(parents=True, exist_ok=True)

# DSL Engine specific configs (can be moved from dsl_engine.py if preferred)
LOG_DIR_NAME = "Logs_DSL" # Renamed to avoid conflict if backend has its own 'Logs'
DSL_LOG_DIR = BACKEND_ROOT_DIR / LOG_DIR_NAME
MAX_LOG_BYTES = 2_000_000
BACKUP_COUNT = 3

# Ensure DSL_LOG_DIR exists
DSL_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Update dsl_engine.py to use these constants:
# Replace:
# LOG_DIR = "Logs"
# With:
# from app.core.config import DSL_LOG_DIR
# LOG_DIR = DSL_LOG_DIR
#
# And ensure paths like LOG_FILE are constructed with Path objects or os.path.join
# LOG_FILE = DSL_LOG_DIR / "dsl_execution.log" # In dsl_engine.py

# Character model related
DEFAULT_CHARACTER_ID = "Hero" # Example