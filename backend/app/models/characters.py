# characters.py
import logging
from app.models.character import Character

_log = logging.getLogger(__name__)

# Миксин, чтобы подсветить использование устаревшего класса
class _LegacyWarnMixin:
    def __init__(self, *a, **kw):
        _log.warning("%s is legacy, kept for compatibility.", self.__class__.__name__)
        super().__init__(*a, **kw)


class CrazyMita(_LegacyWarnMixin, Character):
    # --------------- 3. переопределяем нужные поля ---------------
    DEFAULT_OVERRIDES = {
        "attitude": 50,
        "boredom": 20,
        "stress": 8,
    }


class KindMita(_LegacyWarnMixin, Character):
    DEFAULT_OVERRIDES = {
        "attitude": 90,
        "stress": 0,
    }


class ShortHairMita(_LegacyWarnMixin, Character):
    DEFAULT_OVERRIDES = {"attitude": 70, "boredom": 15, "stress": 10}


class CappyMita(_LegacyWarnMixin, Character):
    DEFAULT_OVERRIDES = {"boredom": 25}


class MilaMita(_LegacyWarnMixin, Character):
    DEFAULT_OVERRIDES = {"attitude": 75}


class CreepyMita(_LegacyWarnMixin, Character):
    DEFAULT_OVERRIDES = {"attitude": 40, "stress": 30}


class SleepyMita(_LegacyWarnMixin, Character):
    DEFAULT_OVERRIDES = {"boredom": 40}