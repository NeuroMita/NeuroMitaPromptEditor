# File: logic/dsl_runner.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from logic.dsl_ast import Script, AstNode, Set, Log, AddSystemInfo, Return, If

_INLINE_LOAD_RE = re.compile(
    r"""\bLOAD
         (?:\s+([A-Z0-9_]+))?
         \s+FROM\s+
         (['"])(.+?)\2
    """,
    re.IGNORECASE | re.VERBOSE,
)
_LOAD_REL_RE = re.compile(r"""\bLOAD(?:_REL|REL)\s+(['"])(.+?)\1""", re.IGNORECASE)
_SECTION_MARKER_RE = re.compile(
    r"^[ \t]*\[(?:#|/)\s*[A-Z0-9_]+\s*\][ \t]*\r?\n?",
    re.IGNORECASE | re.MULTILINE
)
_TAG_SECTION_RE_TMPL = r"\[#\s*{tag}\s*\](.*?)\s*\[/\s*{tag}\s*\]"


@dataclass
class NodeRunInfo:
    node_id: str
    node_type: str = ""
    expr: Optional[str] = None
    line_num: Optional[int] = None

    preview: str = ""
    error: Optional[str] = None
    vars_delta: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)  # k -> (old, new)
    sys_info_added: Optional[str] = None
    log_value: Optional[str] = None
    chosen_branch_key: Optional[str] = None  # branch_0/branch_1/.../else


@dataclass
class RunnerReport:
    final_text: str
    sys_infos: List[str]
    logs: List[str]
    vars_before: Dict[str, Any]
    vars_after: Dict[str, Any]
    node_results: Dict[str, NodeRunInfo]
    exec_trace: List[str]  # последовательность id нод, которые реально исполнялись


class DslAstRunner:
    """
    Мини-раннер для AST (.script) из node-редактора.
    - Обрабатывает: SET/LOG/ADD_SYSTEM_INFO/IF/RETURN.
    - eval выражений с безопасным builtins.
    - inline LOAD/LOAD_REL, LOAD TAG FROM "path" -> подстановка как строкового литерала перед eval.
    - Переменные: globals (variables) и locals (declared_local_vars + _locals).
    - Собирает NodeRunInfo по каждой ноде + exec_trace для подсветки пути.
    """
    def __init__(self, base_dir: Optional[str] = None, prompts_root: Optional[str] = None):
        self.base_dir = base_dir
        self.prompts_root = prompts_root

        # состояние
        self.variables: Dict[str, Any] = {}
        self._locals: Dict[str, Any] = {}
        self._declared_locals: set[str] = set()
        self.sys_msgs: List[str] = []
        self.logs: List[str] = []
        self.node_results: Dict[str, NodeRunInfo] = {}
        self.exec_trace: List[str] = []

        self.safe_globals = {
            "__builtins__": {
                "str": str,
                "int": int,
                "float": float,
                "len": len,
                "round": round,
                "abs": abs,
                "max": max,
                "min": min,
                "True": True,
                "False": False,
                "None": None,
            }
        }

    # -------------------- public API --------------------
    def run(self, script: Script, initial_vars: Optional[Dict[str, Any]] = None) -> RunnerReport:
        self.variables = dict(initial_vars or {})
        self._locals.clear()
        self._declared_locals.clear()
        self.sys_msgs.clear()
        self.logs.clear()
        self.node_results.clear()
        self.exec_trace.clear()

        vars_before = dict(self._merged_vars())
        final_text = ""
        try:
            returned = self._exec_block(script.body)
            if isinstance(returned, str):
                final_text = returned
        except Exception as e:
            final_text = f"[RUNNER ERROR: {e}]"

        vars_after = dict(self._merged_vars())
        return RunnerReport(
            final_text=final_text,
            sys_infos=list(self.sys_msgs),
            logs=list(self.logs),
            vars_before=vars_before,
            vars_after=vars_after,
            node_results=self.node_results,
            exec_trace=list(self.exec_trace)
        )

    # -------------------- execution core --------------------
    def _exec_block(self, body: List[AstNode]) -> Optional[str]:
        i = 0
        while i < len(body):
            n = body[i]

            # SET
            if isinstance(n, Set):
                info = NodeRunInfo(node_id=n.id, node_type="SET", expr=n.expr, line_num=(n.line or None))
                before = dict(self._merged_vars())
                try:
                    self.exec_trace.append(n.id)
                    val = self._eval_expr(n.expr)
                    if n.local:
                        self._declared_locals.add(n.var)
                        old = self._locals.get(n.var)
                        self._locals[n.var] = val
                    else:
                        if n.var in self._declared_locals:
                            old = self._locals.get(n.var)
                            self._locals[n.var] = val
                        else:
                            old = self.variables.get(n.var)
                            self.variables[n.var] = val
                    after = dict(self._merged_vars())
                    delta = self._compute_delta(before, after, keys_hint=[n.var])
                    info.vars_delta.update(delta)
                    info.preview = f"{'LOCAL ' if n.local else ''}{n.var} = {self._repr_short(val)}"
                except Exception as e:
                    info.error = self._humanize_exception(e, n.expr)
                    info.preview = info.error
                self.node_results[n.id] = info

            # LOG
            elif isinstance(n, Log):
                info = NodeRunInfo(node_id=n.id, node_type="LOG", expr=n.expr, line_num=(n.line or None))
                try:
                    self.exec_trace.append(n.id)
                    val = self._eval_expr(n.expr)
                    s = str(val)
                    self.logs.append(s)
                    info.log_value = s
                    info.preview = f"LOG: {self._repr_short(s)}"
                except Exception as e:
                    info.error = self._humanize_exception(e, n.expr)
                    info.preview = info.error
                self.node_results[n.id] = info

            # ADD_SYSTEM_INFO
            elif isinstance(n, AddSystemInfo):
                info = NodeRunInfo(node_id=n.id, node_type="ADD_SYSTEM_INFO", expr=n.expr, line_num=(n.line or None))
                try:
                    self.exec_trace.append(n.id)
                    content = self._evaluate_sysinfo_expr(n.expr)
                    if content and content.strip():
                        self.sys_msgs.append(content)
                    info.sys_info_added = content
                    info.preview = f"ADD_SYSTEM_INFO (+{len(content)} ch)"
                except Exception as e:
                    info.error = self._humanize_exception(e, n.expr)
                    info.preview = info.error
                self.node_results[n.id] = info

            # IF
            elif isinstance(n, If):
                info = NodeRunInfo(node_id=n.id, node_type="IF", expr=None, line_num=(n.line or None))
                chosen_key: Optional[str] = None
                try:
                    self.exec_trace.append(n.id)
                    taken = False
                    for idx, br in enumerate(n.branches or []):
                        cond = br.cond or ""
                        try:
                            if self._eval_condition(cond):
                                chosen_key = f"branch_{idx}"
                                ret = self._exec_block(br.body)
                                taken = True
                                info.chosen_branch_key = chosen_key
                                info.preview = f"IF -> {chosen_key}"
                                self.node_results[n.id] = info
                                if ret is not None:
                                    return ret
                                break
                        except Exception as e:
                            info.error = f"Ошибка в условии '{cond}': " + self._humanize_exception(e, cond)
                            info.preview = info.error
                            self.node_results[n.id] = info
                            # продолжаем поиск других веток? Лучше остановить, чтобы не путать
                            return None
                    if not taken:
                        if n.else_body is not None:
                            chosen_key = "else"
                            info.chosen_branch_key = chosen_key
                            info.preview = f"IF -> else"
                            self.node_results[n.id] = info
                            ret = self._exec_block(n.else_body)
                            if ret is not None:
                                return ret
                        else:
                            info.chosen_branch_key = None
                            info.preview = "IF -> no-branch"
                            self.node_results[n.id] = info
                except Exception as e:
                    info.error = self._humanize_exception(e, "")
                    info.preview = info.error
                    self.node_results[n.id] = info

            # RETURN
            elif isinstance(n, Return):
                info = NodeRunInfo(node_id=n.id, node_type="RETURN", expr=n.expr, line_num=(n.line or None))
                try:
                    self.exec_trace.append(n.id)
                    txt = self._evaluate_return_expr(n.expr)
                    info.preview = f"RETURN ({len(txt)} ch)"
                    self.node_results[n.id] = info
                    return txt
                except Exception as e:
                    info.error = self._humanize_exception(e, n.expr)
                    info.preview = info.error
                    self.node_results[n.id] = info
                    return f"[RETURN ERROR: {info.error}]"

            i += 1
        return None

    # -------------------- expression helpers --------------------
    def _merged_vars(self) -> Dict[str, Any]:
        merged = {}
        merged.update(self.variables)
        merged.update(self._locals)
        return merged

    def _eval_condition(self, cond: str) -> bool:
        py = (cond or "").replace(" AND ", " and ").replace(" OR ", " or ")
        res = self._eval_expr(py)
        return bool(res)

    def _eval_expr(self, expr: str) -> Any:
        expr = expr or ""
        combined = self._merged_vars()
        max_missing_fills = 10
        fills = 0
        while True:
            try:
                expr_to_eval = self._expand_inline_loads(expr)
                if expr_to_eval.lstrip().startswith(("f'", 'f"', 'f"""')):
                    return eval(expr_to_eval, self.safe_globals, combined)
                return eval(expr_to_eval, self.safe_globals, combined)
            except NameError as ne:
                m = re.search(r"name '([^']+)' is not defined", str(ne))
                if not m or fills >= max_missing_fills:
                    raise
                var_name = m.group(1)
                self._locals[var_name] = None
                combined[var_name] = None
                fills += 1
                continue
            except TypeError as e:
                msg = str(e).lower()
                is_concat = "can only concatenate str" in msg or ("unsupported operand type(s) for +" in msg and "str" in msg)
                if not is_concat:
                    raise
                fixed = {k: (str(v) if isinstance(v, (int, float, bool, type(None))) else v) for k, v in combined.items()}
                if expr_to_eval.lstrip().startswith(("f'", 'f"', 'f"""')):
                    return eval(expr_to_eval, self.safe_globals, fixed)
                return eval(expr_to_eval, self.safe_globals, fixed)

    def _expand_inline_loads(self, expr: str) -> str:
        def handle_load(m: re.Match) -> str:
            tag = m.group(1)
            rel = m.group(3)
            content = self._load_and_process(rel, tag)
            return repr(content)

        expr2 = _INLINE_LOAD_RE.sub(handle_load, expr)

        def handle_rel(m: re.Match) -> str:
            rel = m.group(2)
            content = self._load_and_process(rel, None)
            return repr(content)

        expr2 = _LOAD_REL_RE.sub(handle_rel, expr2)
        return expr2

    # -------------------- sysinfo/return loaders --------------------
    def _evaluate_sysinfo_expr(self, raw_arg: str) -> str:
        a = (raw_arg or "").strip()
        m_rel = _LOAD_REL_RE.match(a)
        if m_rel:
            rel = m_rel.group(2)
            return self._load_and_process(rel, None)

        if a.upper().startswith("LOAD "):
            after = a[5:].strip()
            m_tag = re.match(r"([A-Z0-9_]+)\s+FROM\s+(.+)", after, re.IGNORECASE)
            if m_tag:
                tag = m_tag.group(1).upper()
                path_quoted = m_tag.group(2).strip().strip('"').strip("'")
                return self._load_and_process(path_quoted, tag)
            path_quoted = after.strip().strip('"').strip("'")
            return self._load_and_process(path_quoted, None)

        return str(self._eval_expr(a))

    def _evaluate_return_expr(self, raw_arg: str) -> str:
        return self._evaluate_sysinfo_expr(raw_arg)

    # -------------------- file helpers --------------------
    def _resolve_path(self, rel_path: str) -> Optional[str]:
        if not rel_path:
            return None
        if os.path.isabs(rel_path) and os.path.exists(rel_path):
            return rel_path
        if self.base_dir:
            p = os.path.normpath(os.path.join(self.base_dir, rel_path))
            if os.path.exists(p):
                return p
        if self.prompts_root:
            p = os.path.normpath(os.path.join(self.prompts_root, rel_path))
            if os.path.exists(p):
                return p
        return None

    def _read_file(self, path: str) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _remove_tag_markers(self, text: str) -> str:
        return _SECTION_MARKER_RE.sub("", text or "")

    def _extract_tag_section(self, raw: str, tag_name: Optional[str]) -> str:
        if not tag_name:
            return self._remove_tag_markers(raw)
        tag_up = tag_name.upper()
        pat = re.compile(_TAG_SECTION_RE_TMPL.format(tag=re.escape(tag_up)), re.IGNORECASE | re.DOTALL)
        m = pat.search(raw or "")
        if not m:
            return f"[Тег [#{tag_name}] не найден]"
        content = m.group(1)
        if content.startswith("\n"):
            content = content[1:]
        return content

    def _load_and_process(self, rel: str, tag: Optional[str]) -> str:
        path = self._resolve_path(rel) or rel
        if not (os.path.isabs(path) and os.path.exists(path)):
            return f"[файл не найден: {rel}]"
        raw = self._read_file(path)
        return self._extract_tag_section(raw, tag)

    # -------------------- utils --------------------
    def _compute_delta(self, before: Dict[str, Any], after: Dict[str, Any], keys_hint: Optional[List[str]] = None) -> Dict[str, Tuple[Any, Any]]:
        out: Dict[str, Tuple[Any, Any]] = {}
        if keys_hint:
            for k in keys_hint:
                b = before.get(k, None)
                a = after.get(k, None)
                if b != a:
                    out[k] = (b, a)
            return out
        keys = set(before.keys()) | set(after.keys())
        for k in keys:
            if before.get(k) != after.get(k):
                out[k] = (before.get(k), after.get(k))
        return out

    def _repr_short(self, v: Any, limit: int = 160) -> str:
        s = repr(v)
        return s if len(s) <= limit else s[:limit] + "…"

    def _humanize_exception(self, e: Exception, expr: str) -> str:
        msg = str(e)
        low = msg.lower()
        # NameError
        m = re.search(r"name '([^']+)' is not defined", msg)
        if m:
            var = m.group(1)
            return f"Переменная '{var}' не определена. Раннер пытался инициализировать её как None, но выражение всё ещё не вычисляется. Задайте начальное значение (SET {var} = ...) или скорректируйте выражение."
        # NoneType сравнения
        if "not supported between instances of 'nonetype'" in low or "noneType" in msg:
            # попытаемся подсказать, какие переменные равны None
            vars_in_expr = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", expr or ""))
            none_vars = [v for v in vars_in_expr if self._merged_vars().get(v, "___MISS___") is None]
            hint = ""
            if none_vars:
                hint = f" (возможно, не инициализированы: {', '.join(none_vars)})"
            return f"Операция невозможна: в выражении есть None (не инициализированные значения){hint}. Установите начальные значения или используйте, например, ({'x'} or 0)."
        # конкатенация строк и чисел
        if "can only concatenate str" in low or ("unsupported operand type(s) for +" in low and "str" in low):
            return "Склейка строк и чисел без приведения типов. Оберните число в str(...), например: 'Score: ' + str(score)."
        # атрибуты у None
        if "object has no attribute" in low and "'nonetype'" in low:
            return "Обращение к полю/методу у None. Проверьте, что переменная инициализирована перед использованием."
        # дефолт
        return msg