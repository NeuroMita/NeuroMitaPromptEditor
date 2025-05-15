from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import shutil
from pathlib import Path

from app.core.config import PROMPTS_ROOT_PATH
from app.utils.logger_api import api_logger

router = APIRouter()

def secure_path(base_path: Path, user_path_str: str) -> Path:
    """Helper to resolve and validate user-provided paths."""
    try:
        # Normalize and resolve the combined path
        combined_path = (base_path / user_path_str).resolve()
        # Check if the resolved path is within the base_path
        if base_path not in combined_path.parents and combined_path != base_path:
             # Allow if combined_path is a direct child of base_path
            if combined_path.parent != base_path:
                raise HTTPException(status_code=403, detail=f"Path traversal attempt: {user_path_str} is outside the allowed directory.")
        return combined_path
    except Exception as e: # Broad exception for path resolution issues
        api_logger.error(f"Path security check failed for '{user_path_str}' against base '{base_path}': {e}")
        raise HTTPException(status_code=400, detail=f"Invalid path: {user_path_str}. {e}")


class FileNode(BaseModel):
    name: str
    path: str  # Relative to PROMPTS_ROOT_PATH
    is_dir: bool
    is_character_dir: bool = False # True if it's a direct child of Prompts and not starting with '_'
    children: Optional[List['FileNode']] = None

class FileContent(BaseModel):
    path: str # Relative to PROMPTS_ROOT_PATH
    content: str

@router.get("/tree", response_model=List[FileNode])
async def get_file_tree(path: str = Query(".")):
    """
    Lists files and folders. 'path' is relative to PROMPTS_ROOT_PATH.
    """
    api_logger.info(f"Requesting file tree for relative path: '{path}'")
    current_path = secure_path(PROMPTS_ROOT_PATH, path)
    if not current_path.exists() or not current_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {path}")

    items = []
    for item in sorted(list(current_path.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower())):
        relative_item_path = str(item.relative_to(PROMPTS_ROOT_PATH))
        is_char_dir = False
        if item.is_dir() and item.parent == PROMPTS_ROOT_PATH and not item.name.startswith("_"):
            is_char_dir = True
            
        node = FileNode(name=item.name, path=relative_item_path, is_dir=item.is_dir(), is_character_dir=is_char_dir)
        if item.is_dir():
            # Optionally, you can make this recursive by calling a helper or limiting depth
            # For a simple flat list of the current directory, children would be None or fetched on demand
            pass # node.children = await get_file_tree(relative_item_path) # Example for recursion
        items.append(node)
    return items

@router.get("/content", response_model=FileContent)
async def get_file_content(file_path: str = Query(...)):
    """
    Gets the content of a specific file. 'file_path' is relative to PROMPTS_ROOT_PATH.
    """
    api_logger.info(f"Requesting content for relative file path: '{file_path}'")
    target_file = secure_path(PROMPTS_ROOT_PATH, file_path)
    if not target_file.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
    try:
        content = target_file.read_text(encoding="utf-8")
        return FileContent(path=file_path, content=content)
    except Exception as e:
        api_logger.error(f"Error reading file '{target_file}': {e}")
        raise HTTPException(status_code=500, detail=f"Could not read file: {e}")

class SaveFilePayload(BaseModel):
    content: str

@router.post("/content")
async def save_file_content(file_path: str = Query(...), payload: SaveFilePayload = Body(...)):
    """
    Saves content to a specific file. 'file_path' is relative to PROMPTS_ROOT_PATH.
    Creates the file if it doesn't exist.
    """
    api_logger.info(f"Saving content for relative file path: '{file_path}'")
    target_file = secure_path(PROMPTS_ROOT_PATH, file_path)
    
    # Ensure parent directory exists
    target_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        target_file.write_text(payload.content, encoding="utf-8")
        return {"message": "File saved successfully", "path": file_path}
    except Exception as e:
        api_logger.error(f"Error writing file '{target_file}': {e}")
        raise HTTPException(status_code=500, detail=f"Could not save file: {e}")

class CreateItemPayload(BaseModel):
    name: str
    type: str # "file" or "folder"

@router.post("/create")
async def create_file_or_folder(parent_dir_path: str = Query("."), payload: CreateItemPayload = Body(...)):
    """
    Creates a new file or folder. 'parent_dir_path' is relative to PROMPTS_ROOT_PATH.
    """
    api_logger.info(f"Creating '{payload.type}' named '{payload.name}' in '{parent_dir_path}'")
    parent_dir = secure_path(PROMPTS_ROOT_PATH, parent_dir_path)
    if not parent_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Parent directory not found: {parent_dir_path}")

    new_item_path = parent_dir / payload.name
    if new_item_path.exists():
        raise HTTPException(status_code=409, detail=f"'{payload.name}' already exists in '{parent_dir_path}'")

    try:
        if payload.type == "file":
            new_item_path.touch()
            msg = "File created"
        elif payload.type == "folder":
            new_item_path.mkdir()
            msg = "Folder created"
        else:
            raise HTTPException(status_code=400, detail="Invalid type. Must be 'file' or 'folder'.")
        return {"message": msg, "path": str(new_item_path.relative_to(PROMPTS_ROOT_PATH))}
    except Exception as e:
        api_logger.error(f"Error creating '{payload.name}': {e}")
        raise HTTPException(status_code=500, detail=f"Could not create item: {e}")


class RenameItemPayload(BaseModel):
    new_name: str

@router.put("/rename")
async def rename_item(item_path: str = Query(...), payload: RenameItemPayload = Body(...)):
    """
    Renames a file or folder. 'item_path' is relative to PROMPTS_ROOT_PATH.
    """
    api_logger.info(f"Renaming '{item_path}' to '{payload.new_name}'")
    old_path_abs = secure_path(PROMPTS_ROOT_PATH, item_path)
    if not old_path_abs.exists():
        raise HTTPException(status_code=404, detail=f"Item not found: {item_path}")

    new_path_abs = old_path_abs.parent / payload.new_name
    if new_path_abs.exists():
        raise HTTPException(status_code=409, detail=f"An item named '{payload.new_name}' already exists.")

    try:
        old_path_abs.rename(new_path_abs)
        return {"message": "Item renamed successfully", "new_path": str(new_path_abs.relative_to(PROMPTS_ROOT_PATH))}
    except Exception as e:
        api_logger.error(f"Error renaming '{item_path}': {e}")
        raise HTTPException(status_code=500, detail=f"Could not rename item: {e}")


@router.delete("/delete")
async def delete_item(item_path: str = Query(...)):
    """
    Deletes a file or folder. 'item_path' is relative to PROMPTS_ROOT_PATH.
    """
    api_logger.info(f"Deleting '{item_path}'")
    abs_path_to_delete = secure_path(PROMPTS_ROOT_PATH, item_path)
    if not abs_path_to_delete.exists():
        raise HTTPException(status_code=404, detail=f"Item not found: {item_path}")
    
    if abs_path_to_delete == PROMPTS_ROOT_PATH: # Safety check
        raise HTTPException(status_code=403, detail="Cannot delete the root Prompts directory.")

    try:
        if abs_path_to_delete.is_dir():
            shutil.rmtree(abs_path_to_delete)
        else:
            abs_path_to_delete.unlink()
        return {"message": "Item deleted successfully", "path": item_path}
    except Exception as e:
        api_logger.error(f"Error deleting '{item_path}': {e}")
        raise HTTPException(status_code=500, detail=f"Could not delete item: {e}")