from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Dict, Any, List
from pathlib import Path

from app.core.config import PROMPTS_ROOT_PATH
from app.models.character import Character
# If you use legacy characters for defaults:
from app.models.characters import (
    CrazyMita, KindMita, ShortHairMita, CappyMita, MilaMita, CreepyMita, SleepyMita
)
from app.utils.logger_api import api_logger, get_dsl_logs_for_request, remove_list_log_handler

router = APIRouter()

# Store legacy classes in a dictionary for easy lookup
_LEGACY_CLASSES_MAP = {
    "crazymita": CrazyMita, "kindmita": KindMita, "shorthairmita": ShortHairMita,
    "cappymita": CappyMita, "milamita": MilaMita, "creepymita": CreepyMita,
    "sleepymita": SleepyMita
}


class CharacterVariablesResponse(BaseModel):
    character_id: str
    variables: Dict[str, Any]

@router.get("/{char_id}/default-variables", response_model=CharacterVariablesResponse)
async def get_character_default_variables(char_id: str):
    """
    Gets default variables for a character.
    Combines Character.BASE_DEFAULTS with legacy overrides if applicable.
    """
    api_logger.info(f"Requesting default variables for character: '{char_id}'")
    
    # Check if character directory exists
    char_dir = PROMPTS_ROOT_PATH / char_id
    if not char_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Character directory '{char_id}' not found in Prompts.")

    base_defaults = Character.base_defaults() # Use classmethod for a fresh copy
    
    # Apply overrides from legacy classes if char_id matches
    legacy_class = _LEGACY_CLASSES_MAP.get(char_id.lower())
    if legacy_class:
        overrides = getattr(legacy_class, "DEFAULT_OVERRIDES", {})
        base_defaults.update(overrides)
        api_logger.info(f"Applied legacy overrides for {char_id} from class {legacy_class.__name__}")

    return CharacterVariablesResponse(character_id=char_id, variables=base_defaults)


class GeneratePromptPayload(BaseModel):
    initial_variables: Dict[str, Any] = Field(default_factory=dict)
    # For {{SYS_INFO}} and other dynamic tags
    tags: Dict[str, Any] = Field(default_factory=lambda: {"SYS_INFO": "[SYS_INFO PLACEHOLDER]"})

class GeneratePromptResponse(BaseModel):
    character_id: str
    generated_prompt: str
    logs: List[Dict[str, Any]] = Field(default_factory=list) # To send back DSL execution logs

@router.post("/{char_id}/generate-prompt", response_model=GeneratePromptResponse)
async def generate_character_prompt(char_id: str, payload: GeneratePromptPayload = Body(...)):
    """
    Generates a full prompt for the specified character using the DSL engine.
    """
    api_logger.info(f"Generating prompt for character: '{char_id}' with variables: {payload.initial_variables} and tags: {payload.tags}")

    char_dir = PROMPTS_ROOT_PATH / char_id
    if not char_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Character directory '{char_id}' not found in Prompts.")
    
    # Check for main_template.txt
    # The Character class constructor expects prompts_root_path to be the global Prompts root,
    # and it will construct base_data_path as PROMPTS_ROOT_PATH / char_id.
    # main_template_path_relative is relative to this base_data_path.
    
    # Capture DSL logs for this request
    captured_logs, log_handler = get_dsl_logs_for_request()

    try:
        # Instantiate the character
        # The Character class will use its own `DEFAULT_OVERRIDES` if the class itself has them,
        # or just `BASE_DEFAULTS`. The `initial_vars` from payload will further override these.
        character_instance = Character(
            char_id=char_id,
            name=char_id, # Name can be same as ID or fetched from a config
            prompts_root_path=str(PROMPTS_ROOT_PATH), # Pass the global Prompts root
            initial_vars=payload.initial_variables
        )
        
        # The main_template_path_relative is already set in Character class, e.g., "main_template.txt"
        # It will be resolved against character_instance.base_data_path

        api_logger.debug(f"Character '{char_id}' instantiated. Base data path: {character_instance.base_data_path}")
        api_logger.debug(f"Main template path relative: {character_instance.main_template_path_relative}")
        
        full_main_template_path = Path(character_instance.base_data_path) / character_instance.main_template_path_relative
        if not full_main_template_path.is_file():
            api_logger.error(f"Main template file '{full_main_template_path}' not found for character '{char_id}'.")
            raise HTTPException(status_code=404, detail=f"Main template file '{character_instance.main_template_path_relative}' not found for character '{char_id}'.")

        prompt_text = character_instance.get_full_prompt(tags=payload.tags)
        
        return GeneratePromptResponse(
            character_id=char_id,
            generated_prompt=prompt_text,
            logs=captured_logs
        )
    except HTTPException: # Re-raise HTTPExceptions
        raise
    except Exception as e:
        api_logger.error(f"Error generating prompt for '{char_id}': {e}", exc_info=True)
        # Include captured logs even on error, if any
        return GeneratePromptResponse(
            character_id=char_id,
            generated_prompt=f"[DSL ENGINE ERROR FOR {char_id}: {str(e)} - Check server logs and API response logs]",
            logs=captured_logs # Send back what was captured before the error
        )
    finally:
        # Important: Remove the handler to prevent log duplication on subsequent requests
        remove_list_log_handler(log_handler)