# logic/post_dsl_engine.py
"""
Адаптированный PostDSL движок для редактора промптов.
Принимает текст .postscript и словарь переменных напрямую.
Не зависит от игровых компонентов (Character, memory_system).
"""
from __future__ import annotations

import re
from typing import List, Dict, Any, Tuple, Optional
from utils.logger import editor_logger


class PostDslError(Exception):
    pass


class PostDslRule:
    def __init__(
        self,
        name: str,
        match_type: str,       # "TEXT" | "REGEX"
        pattern_str: str,
        capture_names: List[str],
        action_lines: List[str],
    ):
        self.name = name
        self.match_type = match_type
        self.pattern_str = pattern_str
        try:
            self.compiled_pattern = re.compile(pattern_str) if match_type == "REGEX" else None
        except re.error as e:
            editor_logger.warning(f"PostDSL Rule '{name}': invalid REGEX '{pattern_str}': {e}")
            self.compiled_pattern = None
        self.capture_names = capture_names
        self.remove_match_flag = False
        self.replace_with_expr: Optional[str] = None

        final_actions: List[str] = []
        for line in action_lines:
            stripped = line.strip()
            if stripped.upper() == "REMOVE_MATCH":
                self.remove_match_flag = True
            elif stripped.upper().startswith("REPLACE_MATCH WITH "):
                self.replace_with_expr = stripped[len("REPLACE_MATCH WITH "):].strip()
            else:
                final_actions.append(line)
        self.action_lines = final_actions


def parse_postscript(script_text: str) -> Tuple[List[PostDslRule], Dict[str, str]]:
    """
    Парсит текст .postscript → список PostDslRule + debug_display конфиг.
    Возвращает (rules, debug_display_config).
    """
    rules: List[PostDslRule] = []
    debug_config: Dict[str, str] = {}

    current_rule_name: Optional[str] = None
    current_match_type: Optional[str] = None
    current_pattern_str: Optional[str] = None
    current_captures: List[str] = []
    current_actions: List[str] = []
    in_actions = False
    in_debug = False

    for line_content in script_text.splitlines():
        line = line_content.strip()
        if not line or line.startswith("//"):
            continue
        line = line.split("//", 1)[0].strip()
        if not line:
            continue

        upper = line.upper()

        # --- DEBUG_DISPLAY block ---
        if upper == "DEBUG_DISPLAY":
            # Завершаем текущее правило если есть
            if current_rule_name and current_match_type and current_pattern_str:
                rules.append(PostDslRule(current_rule_name, current_match_type, current_pattern_str,
                                         current_captures, current_actions))
                current_rule_name = None
            in_debug = True
            continue

        if upper == "END_DEBUG_DISPLAY":
            in_debug = False
            continue

        if in_debug:
            if ":" in line:
                label, var = line.split(":", 1)
                debug_config[label.strip().strip('"')] = var.strip()
            continue

        # --- RULE block ---
        if upper.startswith("RULE "):
            if current_rule_name and current_match_type and current_pattern_str:
                rules.append(PostDslRule(current_rule_name, current_match_type, current_pattern_str,
                                         current_captures, current_actions))
            current_rule_name = line.split(maxsplit=1)[1] if len(line.split(maxsplit=1)) > 1 else "unnamed"
            current_match_type = None
            current_pattern_str = None
            current_captures = []
            current_actions = []
            in_actions = False
            continue

        if upper.startswith("MATCH ") and current_rule_name:
            parts = line.split(maxsplit=2)
            if len(parts) >= 3:
                current_match_type = parts[1].upper()
                pattern_part = parts[2]
                # CAPTURE (var1, var2)
                cap_m = re.search(r"CAPTURE\s*\((.*?)\)", pattern_part, re.IGNORECASE)
                if cap_m:
                    current_captures = [n.strip() for n in cap_m.group(1).split(",")]
                    pattern_part = pattern_part[:cap_m.start()].strip()
                current_pattern_str = pattern_part.strip('"').strip("'")
            continue

        if upper == "ACTIONS" and current_rule_name:
            in_actions = True
            continue

        if upper == "END_ACTIONS" and current_rule_name:
            in_actions = False
            continue

        if upper == "END_RULE":
            if current_rule_name and current_match_type and current_pattern_str:
                rules.append(PostDslRule(current_rule_name, current_match_type, current_pattern_str,
                                         current_captures, current_actions))
            current_rule_name = None
            in_actions = False
            continue

        if in_actions and current_rule_name:
            current_actions.append(line)

    # Незакрытое правило
    if current_rule_name and current_match_type and current_pattern_str:
        rules.append(PostDslRule(current_rule_name, current_match_type, current_pattern_str,
                                 current_captures, current_actions))

    return rules, debug_config


class PostDslRunner:
    """
    Самодостаточный раннер PostDSL для тестирования в редакторе.
    Принимает словарь переменных и возвращает модифицированный текст + лог.
    """

    def __init__(self, script_text: str, variables: Dict[str, Any]):
        self.rules, self.debug_display = parse_postscript(script_text)
        self._variables: Dict[str, Any] = dict(variables)
        self._local_vars: Dict[str, Any] = {}
        self._declared_locals: set[str] = set()
        self.rule_log: List[str] = []   # лог срабатываний правил

    @property
    def variables(self) -> Dict[str, Any]:
        return self._variables

    def _eval_expr(self, expr: str, ctx: Dict[str, Any]) -> Any:
        safe_builtins = {
            "str": str, "int": int, "float": float, "len": len,
            "True": True, "False": False, "None": None,
            "round": round, "abs": abs, "max": max, "min": min,
        }
        scope = {**self._variables, **self._local_vars, **ctx}
        try:
            return eval(expr, {"__builtins__": safe_builtins}, scope)
        except NameError as e:
            # Авто-инициализация неизвестной переменной как None
            missing = str(e).split("'")[1] if "'" in str(e) else ""
            if missing:
                scope[missing] = None
                try:
                    return eval(expr, {"__builtins__": safe_builtins}, scope)
                except Exception:
                    pass
            raise PostDslError(f"Ошибка вычисления: {expr}  →  {e}")
        except Exception as e:
            raise PostDslError(f"Ошибка вычисления: {expr}  →  {e}")

    def _execute_actions(
        self,
        rule: PostDslRule,
        match_obj: re.Match | None,
        segment: str,
    ) -> Tuple[str, bool]:
        ctx: Dict[str, Any] = {}
        if rule.match_type == "REGEX" and match_obj:
            groups = match_obj.groups()
            for i, name in enumerate(rule.capture_names):
                if i < len(groups):
                    ctx[name] = groups[i]

        for line in rule.action_lines:
            parts = line.split(maxsplit=1)
            if not parts:
                continue
            cmd = parts[0].upper()
            args = parts[1] if len(parts) > 1 else ""

            if cmd == "SET":
                is_local = False
                rest = args
                ap = rest.split(maxsplit=1)
                if len(ap) > 1 and ap[0].upper() == "LOCAL":
                    is_local = True
                    rest = ap[1]
                if "=" not in rest:
                    continue
                var_name, expr = [s.strip() for s in rest.split("=", 1)]
                try:
                    value = self._eval_expr(expr, ctx)
                    if is_local:
                        if var_name not in self._declared_locals:
                            self._declared_locals.add(var_name)
                            self._local_vars[var_name] = value
                        ctx[var_name] = value
                    else:
                        if var_name in self._declared_locals:
                            self._local_vars[var_name] = value
                        else:
                            self._variables[var_name] = value
                        ctx[var_name] = value
                except PostDslError as e:
                    editor_logger.warning(f"PostDSL Rule '{rule.name}': SET {var_name}: {e}")

            elif cmd == "LOG":
                try:
                    val = self._eval_expr(args, ctx)
                    self.rule_log.append(f"  [LOG] {val}")
                    editor_logger.info(f"PostDSL Rule '{rule.name}' LOG: {val}")
                except PostDslError as e:
                    self.rule_log.append(f"  [LOG ERROR] {e}")

        result = segment
        if rule.remove_match_flag:
            result = ""
        elif rule.replace_with_expr:
            try:
                result = str(self._eval_expr(rule.replace_with_expr, ctx))
            except PostDslError as e:
                editor_logger.warning(f"PostDSL Rule '{rule.name}': REPLACE_MATCH: {e}")
                return segment, False

        return result, True

    def process(self, response_text: str) -> str:
        self._local_vars.clear()
        self._declared_locals.clear()
        self.rule_log.clear()

        modified = response_text

        for rule in self.rules:
            if rule.match_type == "REGEX":
                if not rule.compiled_pattern:
                    self.rule_log.append(f"Rule '{rule.name}': пропущено (невалидный REGEX)")
                    continue
                parts: List[str] = []
                last_end = 0
                hit = False
                for m in rule.compiled_pattern.finditer(modified):
                    parts.append(modified[last_end:m.start()])
                    replacement, ok = self._execute_actions(rule, m, m.group(0))
                    parts.append(replacement if ok else m.group(0))
                    last_end = m.end()
                    if ok:
                        hit = True
                parts.append(modified[last_end:])
                if hit:
                    self.rule_log.append(f"✅ Rule '{rule.name}' (REGEX) сработало")
                    modified = "".join(parts)
                else:
                    self.rule_log.append(f"○ Rule '{rule.name}' (REGEX) — совпадений нет")

            elif rule.match_type == "TEXT":
                pos = 0
                parts = []
                hit = False
                while pos < len(modified):
                    idx = modified.find(rule.pattern_str, pos)
                    if idx == -1:
                        parts.append(modified[pos:])
                        break
                    parts.append(modified[pos:idx])
                    replacement, ok = self._execute_actions(rule, None, rule.pattern_str)
                    parts.append(replacement if ok else rule.pattern_str)
                    pos = idx + len(rule.pattern_str)
                    if ok:
                        hit = True
                if hit:
                    self.rule_log.append(f"✅ Rule '{rule.name}' (TEXT) сработало")
                    modified = "".join(parts)
                else:
                    self.rule_log.append(f"○ Rule '{rule.name}' (TEXT) — совпадений нет")

        return modified
