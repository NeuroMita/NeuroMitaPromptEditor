
from app.utils.logger import editor_logger

CharacterClass = None
DSL_ENGINE_AVAILABLE = False

def load_dsl_engine():
    global CharacterClass, DSL_ENGINE_AVAILABLE
    try:
        from app.models.character import Character
        CharacterClass = Character
        
        import app.logic.dsl_engine 
        
        DSL_ENGINE_AVAILABLE = True
        editor_logger.info("Модули 'app.models.character' и 'app.logic.dsl_engine' успешно импортированы/доступны.")
    except ImportError as e:
        DSL_ENGINE_AVAILABLE = False
        editor_logger.error(f"Не удалось импортировать DSL компоненты: {e}. Функциональность DSL будет недоступна.")
    except Exception as e: # Более общий перехватчик на всякий случай
        DSL_ENGINE_AVAILABLE = False
        editor_logger.error(f"Непредвиденная ошибка при импорте DSL движка: {e}", exc_info=True)

load_dsl_engine()