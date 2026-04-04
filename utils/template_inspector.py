# utils/template_inspector.py
"""
Парсинг main_template.txt и определение типа файлов:
- Общие (из Common/ или via ../Common/) — могут быть переопределены
- Персонажные (из папки персонажа)
- Отсутствующие (файл не найден на диске)
"""
from __future__ import annotations

import os
import re
from typing import List

# Паттерн плейсхолдера в main_template.txt:  [<path/to/file.ext>]
_PLACEHOLDER_RE = re.compile(r"\[<([^>]+\.(?:script|txt|system))>\]")


def _is_common_path(raw_path: str) -> bool:
    """Определяет, является ли путь ссылкой на Common/."""
    p = raw_path.replace("\\", "/")
    # ../Common/..., ../../Common/..., _CommonPrompts/..., _CommonScripts/...
    return bool(
        re.search(r"(^|/)Common/", p, re.IGNORECASE)
        or p.startswith("_CommonPrompts/")
        or p.startswith("_CommonScripts/")
    )


def parse_template_refs(
    main_template_path: str,
    prompts_root: str | None = None,
    char_base_path: str | None = None,
) -> List[dict]:
    """
    Парсит main_template.txt, возвращает список записей:
    {
        "raw":        str,   # исходная строка пути из шаблона
        "is_common":  bool,  # True если путь ведёт в Common/
        "resolved":   str,   # абсолютный путь (попытка разрешить)
        "exists":     bool,  # файл найден на диске
    }

    Для разрешения пути используется char_base_path.
    Если char_base_path не указан, resolved = raw (неразрешённый).
    """
    if not main_template_path or not os.path.isfile(main_template_path):
        return []

    try:
        with open(main_template_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []

    results: List[dict] = []
    tmpl_dir = os.path.dirname(os.path.abspath(main_template_path))

    for match in _PLACEHOLDER_RE.finditer(content):
        raw = match.group(1)
        is_common = _is_common_path(raw)

        # Попытка разрешить путь
        resolved = raw
        if char_base_path:
            candidate = os.path.normpath(os.path.join(char_base_path, raw))
            if os.path.isfile(candidate):
                resolved = candidate
            else:
                # Попробуем от директории шаблона
                candidate2 = os.path.normpath(os.path.join(tmpl_dir, raw))
                if os.path.isfile(candidate2):
                    resolved = candidate2
                elif prompts_root:
                    # _CommonPrompts/... → от prompts_root
                    clean = raw.lstrip("_")
                    candidate3 = os.path.normpath(os.path.join(prompts_root, raw))
                    if os.path.isfile(candidate3):
                        resolved = candidate3

        exists = os.path.isfile(resolved) if resolved != raw else False

        results.append({
            "raw": raw,
            "is_common": is_common,
            "resolved": resolved,
            "exists": exists,
        })

    return results
