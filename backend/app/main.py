from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from pathlib import Path

from app.core.config import PROMPTS_ROOT_PATH, DEFAULT_CHARACTER_ID
from app.api import files, characters, settings # Assume these modules exist
from app.utils.logger_api import api_logger

# This import is crucial for dsl_engine to find Character
# Ensure backend/app is in PYTHONPATH or accessible.
# Uvicorn run from `backend/` with `app.main:app` should handle this.
try:
    from app.models.character import Character
    from app.logic.dsl_engine import DslInterpreter # To ensure it's loadable
    api_logger.info("DSL Engine and Character model loaded successfully.")
except ImportError as e:
    api_logger.error(f"Failed to import DSL components: {e}")
    # Depending on severity, you might want to exit or run in a limited mode
    # For now, we'll let it proceed and endpoints might fail if they depend on these.


app = FastAPI(title="Prompt Editor API")

# CORS (Cross-Origin Resource Sharing)
# Allows your React frontend (running on a different port) to communicate with the API.
origins = [
    "http://localhost:3000",  # Default React dev server port
    "http://127.0.0.1:3000",
    # Add other origins if needed (e.g., your deployed frontend URL)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers from your api modules
app.include_router(files.router, prefix="/api/files", tags=["Files"])
app.include_router(characters.router, prefix="/api/characters", tags=["Characters"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])


@app.get("/")
async def root():
    api_logger.info("Root endpoint accessed.")
    return {"message": "Welcome to the Prompt Editor API!"}

if __name__ == "__main__":
    import uvicorn
    # Ensure Prompts directory exists
    if not PROMPTS_ROOT_PATH.exists():
        api_logger.warning(f"Prompts root directory {PROMPTS_ROOT_PATH} does not exist. Creating it.")
        try:
            PROMPTS_ROOT_PATH.mkdir(parents=True, exist_ok=True)
            # Create a default character folder and main_template.txt if it's completely new
            default_char_path = PROMPTS_ROOT_PATH / DEFAULT_CHARACTER_ID
            if not default_char_path.exists():
                default_char_path.mkdir(parents=True, exist_ok=True)
                (default_char_path / "main_template.txt").write_text(
                    f"[<./{DEFAULT_CHARACTER_ID}_core.txt>]\n{{{{SYS_INFO}}}}"
                )
                (default_char_path / f"{DEFAULT_CHARACTER_ID}_core.txt").write_text(
                    f"This is the core content for {DEFAULT_CHARACTER_ID}."
                )
                api_logger.info(f"Created default character structure for {DEFAULT_CHARACTER_ID}")

        except Exception as e:
            api_logger.error(f"Could not create Prompts directory {PROMPTS_ROOT_PATH}: {e}")
            
    api_logger.info(f"Serving Prompts from: {PROMPTS_ROOT_PATH}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")