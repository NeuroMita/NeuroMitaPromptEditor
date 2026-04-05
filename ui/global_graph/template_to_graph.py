"""
ui/global_graph/template_to_graph.py

Преобразует main_template.txt в список описаний нод для глобального графа.
Использует utils/template_inspector.parse_template_refs() для парсинга.

Возвращает список NodeSpec:
{
    "id":       str,         # уникальный ключ (= raw path)
    "kind":     str,         # "text" | "script" | "postscript" | "system"
    "label":    str,         # отображаемое имя файла
    "raw":      str,         # исходный путь из шаблона
    "resolved": str,         # абсолютный путь (или raw если не разрешён)
    "exists":   bool,        # файл найден
    "is_common": bool,       # ссылка на Common/
    "order":    int,         # порядок включения (0-based)
}
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

from utils.template_inspector import parse_template_refs


def build_graph_from_template(
    prompts_root: str,
    char_id: str,
) -> list[dict]:
    """
    Строит список NodeSpec из main_template.txt персонажа.

    Параметры
    ---------
    prompts_root : str  — путь к папке Prompts
    char_id      : str  — идентификатор персонажа, например "Crazy/DefaultJson"
    """
    parts = char_id.split("/")
    char_base = os.path.join(prompts_root, *parts)
    tmpl_path = os.path.join(char_base, "main_template.txt")

    if not os.path.isfile(tmpl_path):
        return []

    refs = parse_template_refs(
        main_template_path=tmpl_path,
        prompts_root=prompts_root,
        char_base_path=char_base,
    )

    nodes: list[dict] = []
    for i, ref in enumerate(refs):
        raw = ref["raw"]
        ext = Path(raw).suffix.lower()

        if ext == ".script":
            kind = "script"
        elif ext == ".postscript":
            kind = "postscript"
        elif ext == ".system":
            kind = "system"
        else:
            kind = "text"

        label = Path(raw).name  # только имя файла без пути

        nodes.append({
            "id":        raw,
            "kind":      kind,
            "label":     label,
            "raw":       raw,
            "resolved":  ref["resolved"],
            "exists":    ref["exists"],
            "is_common": ref["is_common"],
            "order":     i,
        })

    # Добавляем PostScript-ноду если есть .postscript файлы в папке
    # (которые могут не быть явно включены в main_template)
    _append_postscript_nodes(nodes, char_base, prompts_root)

    return nodes


def _append_postscript_nodes(nodes: list[dict], char_base: str, prompts_root: str):
    """Добавляет .postscript файлы из папки персонажа (если ещё не добавлены)."""
    existing_raws = {n["raw"] for n in nodes}
    if not os.path.isdir(char_base):
        return

    for f in sorted(Path(char_base).rglob("*.postscript")):
        raw = str(f.relative_to(char_base)).replace("\\", "/")
        if raw not in existing_raws:
            nodes.append({
                "id":        raw,
                "kind":      "postscript",
                "label":     f.name,
                "raw":       raw,
                "resolved":  str(f),
                "exists":    True,
                "is_common": False,
                "order":     len(nodes),
            })
