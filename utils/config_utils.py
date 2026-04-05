# prompt_editor/utils/config_utils.py — module-level functions
def get_bounds_defaults() -> dict:
    return {
        "attitude_min": 0.0, "attitude_max": 100.0,
        "boredom_min": 0.0,  "boredom_max": 100.0,
        "stress_min": 0.0,   "stress_max": 100.0,
    }

def _char_path_parts(char_id: str) -> list:
    """Разбивает 'Crazy/DefaultJson' на ['Crazy', 'DefaultJson'] для os.path.join."""
    return [p for p in char_id.replace("\\", "/").split("/") if p]

def get_config_path(prompts_root: str | None, char_id: str | None) -> str:
    import os
    if not (prompts_root and char_id):
        return ""
    return os.path.join(prompts_root, *_char_path_parts(char_id), "config.json")

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

def compute_defaults_for_char(char_id: str | None) -> dict:
    from models.character import Character
    from models.characters import (
        CrazyMita, KindMita, ShortHairMita,
        CappyMita, MilaMita, CreepyMita, SleepyMita
    )
    base = Character.BASE_DEFAULTS.copy()
    if not char_id:
        return base
    # Используем только первую часть ("Crazy" из "Crazy/DefaultJson")
    char_part = _char_path_parts(char_id)[0].lower()
    for cls in (CrazyMita, KindMita, ShortHairMita, CappyMita, MilaMita, CreepyMita, SleepyMita):
        if cls.__name__.lower().startswith(char_part):
            base.update(getattr(cls, "DEFAULT_OVERRIDES", {}))
            break
    return base

def get_info_path(prompts_root: str | None, char_id: str | None) -> str:
    import os
    if not (prompts_root and char_id):
        return ""
    return os.path.join(prompts_root, *_char_path_parts(char_id), "info.json")

def read_info_json(prompts_root: str | None, char_id: str | None) -> dict:
    import os, json
    path = get_info_path(prompts_root, char_id)
    if not path or not os.path.isfile(path):
        return {"character": char_id or "", "author": "", "version": "", "description": ""}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key in ("character", "author", "version", "description"):
        data.setdefault(key, "")
    return data

def write_info_json(prompts_root: str | None, char_id: str | None, data: dict) -> None:
    import os, json
    path = get_info_path(prompts_root, char_id)
    if not path:
        raise RuntimeError("Некорректный путь к info.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

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