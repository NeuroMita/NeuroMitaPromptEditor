# File: backend\app\core\config.py
import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv # <--- Добавлено

# Загружаем переменные из .env файла (если он существует)
# Это должно быть сделано до первого обращения к os.getenv для этих переменных
load_dotenv() # <--- Добавлено

# Determine the project root dynamically
APP_DIR = Path(__file__).resolve().parent.parent # backend/app/
BACKEND_ROOT_DIR = APP_DIR.parent # backend/

# --- User and Auth Configuration ---
USER_DATA_FILE = BACKEND_ROOT_DIR / "data" / "users.json"
USER_PROMPTS_BASE_DIR_NAME = "user_prompts_storage" # Directory name for all user prompts
USER_PROMPTS_ROOT_PATH = BACKEND_ROOT_DIR / USER_PROMPTS_BASE_DIR_NAME
USER_QUOTA_MB = 200

# JWT Settings
SECRET_KEY = os.getenv("SECRET_KEY", "a_very_secret_key_that_should_be_changed_in_production_and_kept_safe") # CHANGE THIS!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7)) # 7 days

# Invite code (for potential future registration endpoint)
# Сначала пытается загрузить из переменной окружения INVITE_CODE,
# если ее нет, используется значение по умолчанию.
INVITE_CODE = os.getenv("INVITE_CODE", "PUT_HERE_YOUR_INVITE_CODE") # <--- Изменено

# Ensure base directories exist
USER_PROMPTS_ROOT_PATH.mkdir(parents=True, exist_ok=True)
USER_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)


# --- DSL Engine specific configs ---
LOG_DIR_NAME = "Logs_DSL"
DSL_LOG_DIR = BACKEND_ROOT_DIR / LOG_DIR_NAME
MAX_LOG_BYTES = 2_000_000
BACKUP_COUNT = 3
DSL_LOG_DIR.mkdir(parents=True, exist_ok=True)

# --- Character model related (legacy, might be removed or adapted) ---
DEFAULT_CHARACTER_ID = "Hero"