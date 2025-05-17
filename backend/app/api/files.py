# File: backend\app\api\files.py
from fastapi import APIRouter, HTTPException, Query, Body, Depends, status
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import shutil
from pathlib import Path

from app.core.config import USER_PROMPTS_ROOT_PATH
from app.auth import User, get_current_active_user
from app.utils.logger_api import api_logger
from app.utils.file_utils import check_user_quota # Import the quota checker

router = APIRouter()

def secure_user_path(user_specific_prompts_root: Path, user_path_str: str) -> Path:
    """Helper to resolve and validate user-provided paths within the user's prompt directory."""
    try:
        if os.path.isabs(user_path_str):
            raise HTTPException(status_code=400, detail="Absolute paths are not allowed.")

        normalized_user_path_str = os.path.normpath(user_path_str)
        
        if normalized_user_path_str.startswith("..") and \
           os.path.abspath(os.path.join(user_specific_prompts_root, normalized_user_path_str)).startswith(os.path.abspath(user_specific_prompts_root)):
             pass 

        combined_path = (user_specific_prompts_root / normalized_user_path_str).resolve()
        
        resolved_user_root = user_specific_prompts_root.resolve()

        if resolved_user_root != combined_path and resolved_user_root not in combined_path.parents:
            api_logger.warning(f"Path traversal attempt: User path '{user_path_str}' (normalized: '{normalized_user_path_str}') resolved to '{combined_path}' which is outside of user root '{resolved_user_root}'.")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Path traversal attempt: '{user_path_str}' is outside the allowed directory.")
        
        return combined_path
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"Path security check failed for '{user_path_str}' against base '{user_specific_prompts_root}': {e}")
        raise HTTPException(status_code=400, detail=f"Invalid path: {user_path_str}. Error: {e}")


class FileNode(BaseModel):
    name: str
    path: str  # Relative to the user's specific prompts root
    is_dir: bool
    is_character_dir: bool = False 
    children: Optional[List['FileNode']] = None

class FileContent(BaseModel):
    path: str 
    content: str

@router.get("/tree", response_model=List[FileNode])
async def get_file_tree(
    path: str = Query("."), 
    current_user: User = Depends(get_current_active_user)
):
    user_prompts_path = USER_PROMPTS_ROOT_PATH / current_user.prompts_dir_relative
    api_logger.info(f"User '{current_user.username}' requesting file tree for relative path: '{path}' in '{user_prompts_path}'")
    
    current_path_abs = secure_user_path(user_prompts_path, path)
    if not current_path_abs.exists() or not current_path_abs.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Directory not found: {path}")

    items = []
    for item_abs in sorted(list(current_path_abs.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower())):
        relative_item_path = str(item_abs.relative_to(user_prompts_path))
        is_char_dir = False

        # A directory is a character directory if it's a directory,
        # doesn't start with an underscore, and contains "main_template.txt".
        # This removes the constraint that it must be an immediate child of user_prompts_path.
        if item_abs.is_dir() and \
           not item_abs.name.startswith("_") and \
           (item_abs / "main_template.txt").is_file():
            is_char_dir = True
            
        node = FileNode(name=item_abs.name, path=relative_item_path, is_dir=item_abs.is_dir(), is_character_dir=is_char_dir)
        items.append(node)
    return items

@router.get("/content", response_model=FileContent)
async def get_file_content(
    file_path: str = Query(...),
    current_user: User = Depends(get_current_active_user)
):
    user_prompts_path = USER_PROMPTS_ROOT_PATH / current_user.prompts_dir_relative
    api_logger.info(f"User '{current_user.username}' requesting content for relative file path: '{file_path}' in '{user_prompts_path}'")
    
    target_file_abs = secure_user_path(user_prompts_path, file_path)
    if not target_file_abs.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found: {file_path}")
    try:
        content = target_file_abs.read_text(encoding="utf-8")
        return FileContent(path=str(target_file_abs.relative_to(user_prompts_path)), content=content)
    except Exception as e:
        api_logger.error(f"Error reading file '{target_file_abs}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not read file: {e}")

class SaveFilePayload(BaseModel):
    content: str

@router.post("/content")
async def save_file_content(
    file_path: str = Query(...), 
    payload: SaveFilePayload = Body(...),
    current_user: User = Depends(get_current_active_user)
):
    user_prompts_path = USER_PROMPTS_ROOT_PATH / current_user.prompts_dir_relative
    api_logger.info(f"User '{current_user.username}' saving content for relative file path: '{file_path}' in '{user_prompts_path}'")
    
    target_file_abs = secure_user_path(user_prompts_path, file_path)
    
    try:
        new_content_size_bytes = len(payload.content.encode('utf-8'))
        existing_file_size_bytes = 0
        if target_file_abs.is_file(): 
            existing_file_size_bytes = target_file_abs.stat().st_size
        
        size_delta_bytes = new_content_size_bytes - existing_file_size_bytes
        check_user_quota(user_prompts_path, current_user.username, additional_size_bytes=size_delta_bytes)
    except HTTPException as e: 
        raise e 
    except Exception as e: 
        api_logger.error(f"Error during quota check for save_file_content by '{current_user.username}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error during pre-save checks: {e}")

    target_file_abs.parent.mkdir(parents=True, exist_ok=True)

    try:
        target_file_abs.write_text(payload.content, encoding="utf-8")
        return {"message": "File saved successfully", "path": str(target_file_abs.relative_to(user_prompts_path))}
    except Exception as e:
        api_logger.error(f"Error writing file '{target_file_abs}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not save file: {e}")

class CreateItemPayload(BaseModel):
    name: str
    type: str 

@router.post("/create")
async def create_file_or_folder(
    parent_dir_path: str = Query("."), 
    payload: CreateItemPayload = Body(...),
    current_user: User = Depends(get_current_active_user)
):
    user_prompts_path = USER_PROMPTS_ROOT_PATH / current_user.prompts_dir_relative
    api_logger.info(f"User '{current_user.username}' creating '{payload.type}' named '{payload.name}' in '{parent_dir_path}' within '{user_prompts_path}'")
    
    if not payload.name or '/' in payload.name or '\\' in payload.name or '..' in payload.name or not payload.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item name. Name cannot be empty or contain path characters.")

    parent_dir_abs = secure_user_path(user_prompts_path, parent_dir_path)
    if not parent_dir_abs.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Parent directory not found: {parent_dir_path}")

    try:
        check_user_quota(user_prompts_path, current_user.username, additional_size_bytes=0) 
    except HTTPException as e:
        raise e
    except Exception as e:
        api_logger.error(f"Error during quota check for create_file_or_folder by '{current_user.username}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error during pre-create checks: {e}")

    new_item_abs_path = parent_dir_abs / payload.name
    if new_item_abs_path.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"'{payload.name}' already exists in '{parent_dir_path}'")

    try:
        if payload.type == "file":
            new_item_abs_path.touch()
            msg = "File created"
        elif payload.type == "folder":
            new_item_abs_path.mkdir()
            msg = "Folder created"
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid type. Must be 'file' or 'folder'.")
        
        return {"message": msg, "path": str(new_item_abs_path.relative_to(user_prompts_path))}
    except Exception as e:
        api_logger.error(f"Error creating '{payload.name}': {e}")
        if new_item_abs_path.exists():
            try:
                if new_item_abs_path.is_dir(): shutil.rmtree(new_item_abs_path)
                else: new_item_abs_path.unlink()
            except Exception as cleanup_e:
                api_logger.error(f"Error cleaning up partially created item '{new_item_abs_path}': {cleanup_e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not create item: {e}")

class RenameItemPayload(BaseModel):
    new_name: str

@router.put("/rename")
async def rename_item(
    item_path: str = Query(...), 
    payload: RenameItemPayload = Body(...),
    current_user: User = Depends(get_current_active_user)
):
    user_prompts_path = USER_PROMPTS_ROOT_PATH / current_user.prompts_dir_relative
    api_logger.info(f"User '{current_user.username}' renaming '{item_path}' to '{payload.new_name}' in '{user_prompts_path}'")

    if not payload.new_name or '/' in payload.new_name or '\\' in payload.new_name or '..' in payload.new_name or not payload.new_name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid new name. Name cannot be empty or contain path characters.")
        
    old_path_abs = secure_user_path(user_prompts_path, item_path)
    if not old_path_abs.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item not found: {item_path}")

    if old_path_abs == user_prompts_path.resolve():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot rename the root user Prompts directory.")

    new_path_abs = old_path_abs.parent / payload.new_name
    if new_path_abs.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"An item named '{payload.new_name}' already exists in the same location.")

    try:
        old_path_abs.rename(new_path_abs)
        return {"message": "Item renamed successfully", "new_path": str(new_path_abs.relative_to(user_prompts_path))}
    except Exception as e:
        api_logger.error(f"Error renaming '{item_path}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not rename item: {e}")

@router.delete("/delete")
async def delete_item(
    item_path: str = Query(...),
    current_user: User = Depends(get_current_active_user)
):
    user_prompts_path = USER_PROMPTS_ROOT_PATH / current_user.prompts_dir_relative
    api_logger.info(f"User '{current_user.username}' deleting '{item_path}' in '{user_prompts_path}'")
    
    abs_path_to_delete = secure_user_path(user_prompts_path, item_path)
    if not abs_path_to_delete.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Item not found: {item_path}")
    
    if abs_path_to_delete == user_prompts_path.resolve():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete the root user Prompts directory via this endpoint.")

    try:
        if abs_path_to_delete.is_dir():
            shutil.rmtree(abs_path_to_delete)
        else:
            abs_path_to_delete.unlink()
        return {"message": "Item deleted successfully", "path": item_path}
    except Exception as e:
        api_logger.error(f"Error deleting '{item_path}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not delete item: {e}")