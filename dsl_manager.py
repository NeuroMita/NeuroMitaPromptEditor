from utils.logger import editor_logger

CharacterClass = None
DSL_ENGINE_AVAILABLE = False

# Экспортируем фабрику для интерпретатора и удобный раннер
def create_dsl_interpreter(character):
    try:
        from logic.dsl_engine import DslInterpreter  # движок (вы подменяете файл)
        from logic.path_resolver import LocalPathResolver
        resolver = LocalPathResolver(
            global_prompts_root=character.prompts_root,
            character_base_data_path=character.base_data_path
        )
        return DslInterpreter(character, resolver)
    except Exception as e:
        editor_logger.error(f"create_dsl_interpreter: ошибка инициализации: {e}", exc_info=True)
        raise

def run_dsl(character, tags: dict | None = None):
    """
    Возвращает кортеж:
      (content_blocks: list[str], system_infos: list[str], vars_before: dict, vars_after: dict)
    """
    interpreter = create_dsl_interpreter(character)
    if tags:
        for tag_name, value in tags.items():
            interpreter.set_insert(tag_name, value)
    vars_before = dict(character.variables)
    content_blocks, system_infos = interpreter.process_main_template(character.main_template_path_relative)
    vars_after = dict(character.variables)
    return content_blocks, system_infos, vars_before, vars_after

def load_dsl_engine():
    global CharacterClass, DSL_ENGINE_AVAILABLE
    try:
        from models.character import Character
        CharacterClass = Character

        # Импорт движка (вы подменяете файл logic/dsl_engine.py на новый)
        import logic.dsl_engine  # noqa: F401

        DSL_ENGINE_AVAILABLE = True
        editor_logger.info("DSL движок (logic.dsl_engine) и модель персонажа загружены.")
    except ImportError as e:
        DSL_ENGINE_AVAILABLE = False
        editor_logger.error(f"Не удалось импортировать DSL компоненты: {e}. Функциональность DSL будет недоступна.")
    except Exception as e:
        DSL_ENGINE_AVAILABLE = False
        editor_logger.error(f"Непредвиденная ошибка при импорте DSL движка: {e}", exc_info=True)

load_dsl_engine()