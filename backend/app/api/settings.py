from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import os

from app.core.config import PROMPTS_ROOT_PATH
from app.utils.logger_api import api_logger

router = APIRouter()

class PromptsRootResponse(BaseModel):
    prompts_root_path: str

@router.get("/prompts-root", response_model=PromptsRootResponse)
async def get_prompts_root_path():
    """
    Returns the configured absolute path to the Prompts root directory.
    """
    return {"prompts_root_path": str(PROMPTS_ROOT_PATH)}

# In a real app, setting prompts_root via API might be complex due to
# server needing to re-initialize things or security concerns.
# For now, it's read from config/env.