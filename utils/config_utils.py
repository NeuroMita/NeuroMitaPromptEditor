# prompt_editor/utils/config_utils.py — module-level functions
def get_bounds_defaults() -> dict:
    return {
        "attitude_min": 0.0, "attitude_max": 100.0,
        "boredom_min": 0.0,  "boredom_max": 100.0,
        "stress_min": 0.0,   "stress_max": 100.0,
    }

def get_config_path(prompts_root: str | None, char_id: str | None) -> str:
    import os
    if not (prompts_root and char_id):
        return ""
    return os.path.join(prompts_root, char_id, "config.json")

def read_config_json(prompts_root: str | None, char_id: str | None, ensure_bounds: bool = True) -> dict | None:
    import os, json
    path = get_config_path(prompts_root, char_id)
    if not path or not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if ensure_bounds:
        for k, v in get_bounds_defaults().items():
            data.setdefault(k, v)
    return data

def write_config_json(prompts_root: str | None, char_id: str | None, cfg: dict) -> None:
    import os, json
    path = get_config_path(prompts_root, char_id)
    if not path:
        raise RuntimeError("Некорректный путь к config.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)

def compute_defaults_for_char(char_id: str) -> dict:
    from models.character import Character
    from models.characters import (
        CrazyMita, KindMita, ShortHairMita,
        CappyMita, MilaMita, CreepyMita, SleepyMita
    )
    base = Character.BASE_DEFAULTS.copy()
    for cls in (CrazyMita, KindMita, ShortHairMita, CappyMita, MilaMita, CreepyMita, SleepyMita):
        if cls.__name__.lower().startswith(char_id.lower()):
            base.update(getattr(cls, "DEFAULT_OVERRIDES", {}))
            break
    return base

def are_configs_equal(a: dict, b: dict) -> bool:
    def norm(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return float(v)
        return v
    keys = set(a.keys()) | set(b.keys())
    for k in keys:
        if norm(a.get(k)) != norm(b.get(k)):
            return False
    return True