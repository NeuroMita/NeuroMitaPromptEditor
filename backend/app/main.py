# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os # Keep for now, might be used by other modules

from app.core.config import (
    # PROMPTS_ROOT_PATH, # This will become user-specific
    DEFAULT_CHARACTER_ID,
    USER_PROMPTS_ROOT_PATH, # New base for all user prompts
    USER_DATA_FILE
)
from app.api import files, characters, settings
from app.api import auth_router # New auth router
from app.api import user_actions_router # New user actions router
from app.utils.logger_api import api_logger
from app.auth import add_user_to_db, load_users_from_file # For initial setup

# Ensure DSL Engine and Character model are loadable
try:
    from app.models.character import Character
    from app.logic.dsl_engine import DslInterpreter
    api_logger.info("DSL Engine and Character model loaded successfully.")
except ImportError as e:
    api_logger.error(f"Failed to import DSL components: {e}")


app = FastAPI(title="Prompt Editor API")

# CORS
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(files.router, prefix="/api/files", tags=["Files"]) # Will need auth
app.include_router(characters.router, prefix="/api/characters", tags=["Characters"]) # Will need auth
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"]) # Some parts might need auth
app.include_router(user_actions_router.router, prefix="/api/user", tags=["User Actions"]) # Added user actions router

@app.on_event("startup")
async def startup_event():
    api_logger.info("Application startup...")
    # Ensure user data file and base prompts directory exist
    USER_PROMPTS_ROOT_PATH.mkdir(parents=True, exist_ok=True)
    USER_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Load users from file. This is already called when auth.py is imported,
    # but calling it here again ensures it's done at startup if auth.py wasn't hit yet.
    load_users_from_file()

    # Create a default admin/test user if users.json is empty or doesn't exist
    # This is for easy first-time setup.
    # In a real scenario, you might have a separate script or admin interface for user management.
    if not USER_DATA_FILE.exists() or os.path.getsize(USER_DATA_FILE) <= 2: # Check for empty JSON {}
        api_logger.info("User data file is empty or does not exist. Creating default user 'admin'.")
        try:
            # IMPORTANT: Change this default password in a real deployment!
            add_user_to_db("admin", "password123") 
            add_user_to_db("testuser", "testpass")
            api_logger.info("Default users 'admin' and 'testuser' created. Please change their passwords.")
        except Exception as e:
            api_logger.error(f"Could not create default user: {e}")
    
    api_logger.info(f"User prompts will be stored under: {USER_PROMPTS_ROOT_PATH}")
    # The old PROMPTS_ROOT_PATH is no longer globally configured this way.
    # Each user will have their own prompts root derived from USER_PROMPTS_ROOT_PATH.


@app.get("/")
async def root():
    api_logger.info("Root endpoint accessed.")
    return {"message": "Welcome to the Prompt Editor API! Please login via /api/auth/token"}
