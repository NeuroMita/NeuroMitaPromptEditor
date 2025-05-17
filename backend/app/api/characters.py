# File: backend\app\api\characters.py
from fastapi import APIRouter, HTTPException, Body, Depends, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List
from pathlib import Path

from app.core.config import USER_PROMPTS_ROOT_PATH
from app.auth import User, get_current_active_user
from app.models.character import Character
from app.models.characters import (
    CrazyMita, KindMita, ShortHairMita, CappyMita, MilaMita, CreepyMita, SleepyMita
)
from app.utils.logger_api import api_logger, get_dsl_logs_for_request, remove_list_log_handler

router = APIRouter()

_LEGACY_CLASSES_MAP = {
    "crazymita": CrazyMita, "kindmita": KindMita, "shorthairmita": ShortHairMita,
    "cappymita": CappyMita, "milamita": MilaMita, "creepymita": CreepyMita,
    "sleepymita": SleepyMita
}

class CharacterVariablesResponse(BaseModel):
    character_id: str # Может быть именем или путем, в зависимости от эндпоинта
    variables: Dict[str, Any]

# НОВЫЙ ЭНДПОИНТ для статических дефолтов по имени
@router.get("/{char_name}/static-defaults", response_model=CharacterVariablesResponse)
async def get_character_static_default_variables(
    char_name: str,
    # current_user: User = Depends(get_current_active_user) # Аутентификация здесь может быть опциональной
                                                            # если это действительно "статические" данные,
                                                            # не зависящие от пользователя.
                                                            # Пока оставим для консистентности.
    current_user: User = Depends(get_current_active_user)
):
    api_logger.info(f"User '{current_user.username}' requesting STATIC default variables for character name: '{char_name}'")

    if not char_name or '/' in char_name or '\\' in char_name or '..' in char_name:
        api_logger.warning(f"Invalid char_name format for static defaults: '{char_name}' by user '{current_user.username}'.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid character name format for static defaults. Cannot contain path characters or be empty.")

    base_defaults = Character.base_defaults()
    
    legacy_class = _LEGACY_CLASSES_MAP.get(char_name.lower())
    if legacy_class:
        overrides = getattr(legacy_class, "DEFAULT_OVERRIDES", {})
        base_defaults.update(overrides)
        api_logger.info(f"Applied legacy overrides for {char_name} using class {legacy_class.__name__}")
    else:
        api_logger.info(f"No specific legacy overrides found for character name '{char_name}'. Using base defaults.")

    return CharacterVariablesResponse(character_id=char_name, variables=base_defaults)


# СТАРЫЙ ЭНДПОИНТ (оставляем, но можно переименовать для ясности, если нужно)
# Он проверяет файловую систему и может быть полезен, если дефолты будут грузиться из файлов персонажа
@router.get("/{char_id_path:path}/filesystem-defaults", response_model=CharacterVariablesResponse, deprecated=True, summary="DEPRECATED: Use /static-defaults or specific file-based logic if needed.")
async def get_character_filesystem_default_variables( # Переименовал для ясности
    char_id_path: str, # char_id_path может быть путем
    current_user: User = Depends(get_current_active_user)
):
    user_prompts_path = USER_PROMPTS_ROOT_PATH / current_user.prompts_dir_relative
    api_logger.info(f"User '{current_user.username}' requesting FILESYSTEM default variables for character path: '{char_id_path}' from '{user_prompts_path}'")
    
    if not char_id_path or '..' in char_id_path:
        api_logger.warning(f"Invalid char_id_path format (contains '..' or empty): '{char_id_path}' by user '{current_user.username}'.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid character ID format. Cannot be empty or contain '..'.")

    normalized_char_path_segment = Path(char_id_path)
    char_dir_abs = (user_prompts_path / normalized_char_path_segment).resolve()

    if not str(char_dir_abs).startswith(str(user_prompts_path.resolve())):
        api_logger.error(f"Security alert: Character path '{char_dir_abs}' for char_id_path '{char_id_path}' is outside user's prompt root '{user_prompts_path.resolve()}' for user '{current_user.username}'.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to character path denied.")

    if not char_dir_abs.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character directory '{char_id_path}' not found in user's Prompts ('{user_prompts_path / char_id_path}').")

    main_template_file = char_dir_abs / Character.main_template_path_relative 
    if not main_template_file.is_file():
        api_logger.warning(f"Directory '{char_id_path}' for user '{current_user.username}' is not a valid character project (missing '{Character.main_template_path_relative}'). Path checked: {main_template_file}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Directory '{char_id_path}' is not a valid character project (missing '{Character.main_template_path_relative}').")

    base_defaults = Character.base_defaults()
    
    # Для этого эндпоинта, имя для legacy lookup берется из имени директории
    char_name_for_legacy_lookup = normalized_char_path_segment.name 
    legacy_class = _LEGACY_CLASSES_MAP.get(char_name_for_legacy_lookup.lower())
    if legacy_class:
        overrides = getattr(legacy_class, "DEFAULT_OVERRIDES", {})
        base_defaults.update(overrides)
        api_logger.info(f"Applied legacy overrides for {char_name_for_legacy_lookup} (from path {char_id_path}) using class {legacy_class.__name__}")

    # Здесь можно было бы добавить логику загрузки дефолтов из файла типа `char_dir_abs / "defaults.json"`
    # if (char_dir_abs / "defaults.json").is_file(): ...

    return CharacterVariablesResponse(character_id=char_id_path, variables=base_defaults)


class GeneratePromptPayload(BaseModel):
    initial_variables: Dict[str, Any] = Field(default_factory=dict)
    tags: Dict[str, Any] = Field(default_factory=lambda: {"SYS_INFO": "[SYS_INFO PLACEHOLDER]"})

class GeneratePromptResponse(BaseModel):
    character_id: str
    generated_prompt: str
    logs: List[Dict[str, Any]] = Field(default_factory=list)

@router.post("/{char_id:path}/generate-prompt", response_model=GeneratePromptResponse)
async def generate_character_prompt(
    char_id: str, # char_id can now be a path
    payload: GeneratePromptPayload = Body(...),
    current_user: User = Depends(get_current_active_user)
):
    user_prompts_path = USER_PROMPTS_ROOT_PATH / current_user.prompts_dir_relative
    api_logger.info(f"User '{current_user.username}' generating prompt for character path: '{char_id}' from '{user_prompts_path}' with variables: {payload.initial_variables} and tags: {payload.tags}")

    if not char_id or '..' in char_id:
        api_logger.warning(f"Invalid char_id format (contains '..' or empty): '{char_id}' by user '{current_user.username}'.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid character ID format. Cannot be empty or contain '..'.")

    normalized_char_path_segment = Path(char_id)
    char_dir_abs = (user_prompts_path / normalized_char_path_segment).resolve()

    if not str(char_dir_abs).startswith(str(user_prompts_path.resolve())):
        api_logger.error(f"Security alert: Character path '{char_dir_abs}' for char_id '{char_id}' is outside user's prompt root '{user_prompts_path.resolve()}' for user '{current_user.username}'.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to character path denied.")

    if not char_dir_abs.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character directory '{char_id}' not found in user's Prompts ('{user_prompts_path / char_id}').")
    
    captured_logs, log_handler = get_dsl_logs_for_request()

    try:
        character_instance = Character(
            char_id=str(normalized_char_path_segment), 
            name=normalized_char_path_segment.name,    
            prompts_root_path=str(user_prompts_path), 
            initial_vars=payload.initial_variables
        )
        
        api_logger.debug(f"Character '{normalized_char_path_segment.name}' (path: {char_id}) for user '{current_user.username}' instantiated. Effective prompts_root: {character_instance.prompts_root}, Base data path: {character_instance.base_data_path}")
        
        prompt_text = character_instance.get_full_prompt(tags=payload.tags)
        
        if f"[DSL ERROR IN MAIN TEMPLATE {Path(character_instance.main_template_path_relative).name}" in prompt_text or \
           f"[PY ERROR IN MAIN TEMPLATE {Path(character_instance.main_template_path_relative).name}" in prompt_text:
            if not (Path(character_instance.base_data_path) / character_instance.main_template_path_relative).is_file():
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Main template file '{character_instance.main_template_path_relative}' not found for character '{char_id}'. This directory may not be a valid character project.")

        return GeneratePromptResponse(
            character_id=char_id,
            generated_prompt=prompt_text,
            logs=captured_logs
        )
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"Error generating prompt for '{char_id}' for user '{current_user.username}': {e}", exc_info=True)
        return GeneratePromptResponse(
            character_id=char_id,
            generated_prompt=f"[DSL ENGINE ERROR FOR {char_id}: {str(e)} - Check server logs and API response logs]",
            logs=captured_logs
        )
    finally:
        remove_list_log_handler(log_handler)