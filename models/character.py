# character.py
import logging
import os # Добавили os
from app.logic.dsl_engine import DslInterpreter, DslError
import datetime
import sys
import traceback
from typing import Dict, Any

logger = logging.getLogger(__name__)


# ANSI Escape Codes для цветов (простой вариант)
RED_COLOR = "\033[91m"
YELLOW_COLOR = "\033[93m"
RESET_COLOR = "\033[0m"
BLUE_COLOR = "\033[94m" # Для DSL LOG


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
        """Копия базовых дефолтов (без риска изменить оригинал)."""
        return cls.BASE_DEFAULTS.copy()

    def __init__(self, char_id: str, name: str, initial_vars: dict | None = None):
        self.char_id = char_id
        self.name = name
        self.base_data_path = os.path.join("Prompts", self.char_id)
        self.main_template_path_relative = "main_template.txt"

        # ----------------------------------------------------------
        # 1.  ИНИЦИАЛИЗИРУЕМ СРАЗУ, ЧТОБЫ set_variable мог работать
        # ----------------------------------------------------------
        self.variables: Dict[str, Any] = {}

        # 2.  Заполняем дефолтами + оверрайдами + user-vars
        self.variables.update(self._compose_initial_vars(initial_vars))

        logger.info(
            "Character '%s' initial vars: %s",
            self.char_id,
            ", ".join(f"{k}={v}" for k, v in self.variables.items()),
        )

        self.set_variable(
            "SYSTEM_DATETIME",
            datetime.datetime.now().isoformat(" ", "minutes")
        )

    # def initialize_default_variables(self):
    #     """Устанавливает значения по умолчанию для стандартных переменных."""
    #     self.set_variable("attitude", 60)
    #     self.set_variable("boredom", 10)
    #     self.set_variable("stress", 5)
    #     self.set_variable("secretExposed", False)
    #     self.set_variable("current_fsm_state", "Hello") # Начальное состояние FSM
    #     self.set_variable("available_action_level", 1)
        
    #     # Переменные специфичные для CrazyMita (или общие, если другие персонажи их используют)
    #     self.set_variable("PlayingFirst", False)
    #     self.set_variable("secretExposedFirst", False)
    #     self.set_variable("secret_exposed_event_text_shown", False)
    #     self.set_variable("LongMemoryRememberCount", 0)
    #     self.set_variable("player_name", "Игрок") # Дефолтное имя игрока
    #     self.set_variable("player_name_known", False) # Для FSM Hello состояния

    def _compose_initial_vars(self, initial_vars_from_user):
        merged = Character.BASE_DEFAULTS.copy()

        overrides = getattr(self, "DEFAULT_OVERRIDES", {})
        merged.update(overrides)

        if initial_vars_from_user:
            merged.update(initial_vars_from_user)

        # никаких set_variable здесь; просто возвращаем словарь
        return merged

    def get_variable(self, name, default=None):
        return self.variables.get(name, default)

    def set_variable(self, name, value):
        # простая нормализация строковых значений
        if isinstance(value, str):
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            else:
                try:
                    value = int(value) if value.isdigit() else float(value)
                except ValueError:
                    value = value.strip("'\"")
        self.variables[name] = value


    def get_full_prompt(self) -> str:
        """Собирает полный промпт для персонажа, обрабатывая его main_template.txt."""
        self.set_variable("SYSTEM_DATETIME", datetime.datetime.now().strftime("%Y %B %d (%A) %H:%M"))
        try:
            interpreter = DslInterpreter(self)
            return interpreter.process_main_template_file(self.main_template_path_relative)
        except Exception as e: # Общий перехватчик на случай, если что-то пойдет не так на этом уровне
            logger.error(f"Critical error during get_full_prompt for {self.char_id}: {e}", exc_info=True)
            print(f"{RED_COLOR}Critical error in get_full_prompt for {self.char_id}: {e}{RESET_COLOR}\n{traceback.format_exc()}", file=sys.stderr)
            return f"[CRITICAL PYTHON ERROR GETTING PROMPT FOR {self.char_id} - CHECK LOGS]"


    def __str__(self):
        return f"{self.name} ({self.char_id}) - Vars: {self.variables}"