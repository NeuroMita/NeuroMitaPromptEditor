# File: backend\app\api\settings.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import User, get_current_active_user
from app.utils.logger_api import api_logger

router = APIRouter()

class UserPromptsInfoResponse(BaseModel):
    user_prompts_message: str
    user_prompts_relative_path: str # e.g., "admin" or "testuser"

@router.get("/prompts-root", response_model=UserPromptsInfoResponse)
async def get_user_prompts_info_endpoint(current_user: User = Depends(get_current_active_user)):
    """
    Returns information about the authenticated user's Prompts root.
    Client operations (like file tree listing) should use relative paths from ".".
    """
    api_logger.info(f"User '{current_user.username}' requested prompts root info.")
    return UserPromptsInfoResponse(
        user_prompts_message=f"File operations are relative to prompts for user '{current_user.username}'.",
        user_prompts_relative_path=current_user.prompts_dir_relative
    )