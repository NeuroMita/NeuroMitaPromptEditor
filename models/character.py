# character.py
import logging
import os
import datetime
import sys
import traceback
from typing import Dict, Any, List, Tuple

from logic.path_resolver import LocalPathResolver
from logic.dsl_engine import DslInterpreter

logger = logging.getLogger(__name__)

RED_COLOR = "\033[91m"
RESET_COLOR = "\033[0m"

class Character:
    BASE_DEFAULTS: Dict[str, Any] = {
        "attitude": 60,
        "boredom": 10,
        "stress": 5,
        "secretExposed": False,
        "current_fsm_state": "Hello",
        "available_action_level": 1,
        "PlayingFirst": False,
        "secretExposedFirst": False,
        "secret_exposed_event_text_shown": False,
        "LongMemoryRememberCount": 0,
        "player_name": "Игрок",
        "player_name_known": False,
    }

    @classmethod
    def base_defaults(cls) -> Dict[str, Any]:
        return cls.BASE_DEFAULTS.copy()

    def __init__(self, char_id: str, name: str, prompts_root_path: str = "Prompts", initial_vars: dict | None = None):
        self.char_id = char_id
        self.name = name
        self.prompts_root = os.path.abspath(prompts_root_path)
        self.base_data_path = os.path.join(self.prompts_root, self.char_id)
        self.main_template_path_relative = "main_template.txt"

        self.variables: Dict[str, Any] = {}
        self.variables.update(self._compose_initial_vars(initial_vars))

        logger.info("Character '%s' initial vars: %s", self.char_id, ", ".join(f"{k}={v}" for k, v in self.variables.items()))

        self.set_variable("SYSTEM_DATETIME", datetime.datetime.now().isoformat(" ", "minutes"))

    def _compose_initial_vars(self, initial_vars_from_user):
        merged = Character.BASE_DEFAULTS.copy()
        overrides = getattr(self, "DEFAULT_OVERRIDES", {})
        merged.update(overrides)
        if initial_vars_from_user:
            merged.update(initial_vars_from_user)
        return merged

    def get_variable(self, name, default=None):
        return self.variables.get(name, default)

    def set_variable(self, name, value):
        if isinstance(value, str):
            low = value.lower()
            if low == "true":
                value = True
            elif low == "false":
                value = False
            else:
                try:
                    value = int(value) if value.isdigit() else float(value)
                except ValueError:
                    value = value.strip("'\"")
        self.variables[name] = value

    def run_dsl(self, tags: dict[str, object] | None = None) -> Tuple[List[str], List[str], Dict[str, Any], Dict[str, Any]]:
        self.set_variable("SYSTEM_DATETIME", datetime.datetime.now().strftime("%Y %B %d (%A) %H:%M"))
        try:
            path_resolver_instance = LocalPathResolver(
                global_prompts_root=self.prompts_root,
                character_base_data_path=self.base_data_path
            )
            interpreter = DslInterpreter(self, path_resolver_instance)
            if tags:
                for tag_name, value in tags.items():
                    interpreter.set_insert(tag_name, value)
            vars_before = dict(self.variables)
            content_blocks, system_infos = interpreter.process_main_template(self.main_template_path_relative)
            vars_after = dict(self.variables)
            return content_blocks or [], system_infos or [], vars_before, vars_after
        except Exception as e:
            print(f"{RED_COLOR}Critical error in run_dsl for {self.char_id}: {e}{RESET_COLOR}\n{traceback.format_exc()}", file=sys.stderr)
            return [f"[CRITICAL ERROR GETTING BLOCKS FOR {self.char_id}]"], [], dict(self.variables), dict(self.variables)

    def get_full_prompt(self, tags: dict[str, object] | None = None) -> str:
        blocks, _sys_infos, _before, _after = self.run_dsl(tags)
        return "\n".join(blocks)

    def __str__(self):
        return f"{self.name} ({self.char_id}) - Vars: {self.variables}"