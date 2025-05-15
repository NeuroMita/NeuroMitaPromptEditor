# File: logic/dsl_engine.py
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import sys
import traceback
from typing import List
from contextlib import contextmanager
from typing import Any, TYPE_CHECKING

RED = "\033[91m"
YEL = "\033[93m"
RST = "\033[0m"


from app.core.config import DSL_LOG_DIR as LOG_DIR
LOG_FILE = os.path.join(LOG_DIR, "dsl_execution.log")
MAX_RECURSION = 10
MULTILINE_DELIM = '"""'
MAX_LOG_BYTES = 2_000_000
BACKUP_COUNT = 3

# ------------- TAG system -------------------------------------------------
INSERT_PATTERN    = re.compile(r"\{\{([A-Z0-9_]+)\}\}")   # {{PLACEHOLDER}}
MANDATORY_INSERTS: set[str] = {"SYS_INFO"}               # обязательные вставки
# --------------------------------------------------------------------------

dsl_execution_logger = logging.getLogger("dsl_execution")
dsl_script_logger = logging.getLogger("dsl_script")

import sys, logging

if not any(getattr(h, "name", "") == "dsl_script_simple"
           for h in dsl_script_logger.handlers):
    sh = logging.StreamHandler(sys.stdout)
    sh.name = "dsl_script_simple"
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("%(message)s"))
    dsl_script_logger.addHandler(sh)

dsl_script_logger.propagate = False

if not dsl_execution_logger.handlers:
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE, mode="a", encoding="utf-8",
            maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT
        )
        
        fmt = '%(asctime)s |%(character_id)s| %(name)s - %(levelname)s [%(filename)s:%(lineno)d] - %(message)s'
        formatter = logging.Formatter(fmt)
        file_handler.setFormatter(formatter)
        
        if not any(getattr(h, "name", "") == "dsl_script_simple" for h in dsl_script_logger.handlers):
            simple_handler = logging.StreamHandler(sys.stdout)
            simple_handler.name = "dsl_script_simple"
            simple_handler.setLevel(logging.INFO)          # только INFO и выше
            simple_handler.setFormatter(logging.Formatter("%(message)s"))
            dsl_script_logger.addHandler(simple_handler)
        
        dsl_execution_logger.addHandler(file_handler)
        dsl_execution_logger.setLevel(logging.DEBUG)
        dsl_execution_logger.propagate = False

        dsl_script_logger.addHandler(file_handler)
        dsl_script_logger.setLevel(logging.DEBUG)
        dsl_script_logger.propagate = False
        
    except Exception as e:
        print(f"{RED}CRITICAL: cannot init DSL loggers: {e}{RST}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

class CharacterContextFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self._char_id = "NO_CHAR"

    def set_character_id(self, char_id: str | None):
        self._char_id = char_id or "NO_CHAR"

    def filter(self, record):
        record.character_id = self._char_id
        return True

char_ctx_filter = CharacterContextFilter()
dsl_execution_logger.addFilter(char_ctx_filter)
dsl_script_logger.addFilter(char_ctx_filter)

class DslError(Exception):
    def __init__(
        self,
        message: str,
        script_path: str | None = None,
        line_num: int | None = None,
        line_content: str | None = None,
        original_exception: Exception | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.script_path = script_path
        self.line_num = line_num
        self.line_content = line_content
        self.original_exception = original_exception

        if isinstance(original_exception, TypeError):
            msg = str(original_exception).lower()
            if ("can only concatenate str" in msg) or \
               (("unsupported operand type(s) for +" in msg) and ("str" in msg)):
                self.message += (
                    "  Hint: используйте str(var) при конкатенации строк и чисел. "
                    'Пример: "Score: " + str(score)'
                )

    def __str__(self):
        loc = ""
        if self.script_path:
            loc += f'File "{os.path.basename(self.script_path)}"'
            if self.line_num:
                loc += f", line {self.line_num}"
        if self.line_content:
            loc += f'\n  Line: "{self.line_content.strip()}"'
        caused = f"\n  Caused by: {type(self.original_exception).__name__}: {self.original_exception}" \
                 if self.original_exception else ""
        return f"DSLError: {self.message}{caused}\n  Location: {loc}"


def secure_join(base: str, *paths: str) -> str:

    normalized_base = os.path.normpath(os.path.abspath(base))
    full = os.path.normpath(os.path.join(normalized_base, *paths))
    if os.path.commonpath([base, full]) != base:
        raise DslError(f"SecurityError: '{full}' is outside '{base}'", script_path=full)
    
    if not (full.startswith(normalized_base + os.sep) or full == normalized_base):
        raise DslError(f"SecurityError: Path '{full}' is outside the allowed base directory '{normalized_base}'.", script_path=full)
    return full


def _split_into_logical_lines(script_text: str) -> list[str]:
    logical_lines: list[str] = []
    buff: list[str] = []
    inside_triple = False
    i = 0
    text = script_text
    n = len(text)
    triple = '"""'

    while i < n:
        if text.startswith(triple, i):
            buff.append(triple)
            inside_triple = not inside_triple
            i += 3
            continue

        ch = text[i]

        if ch == '\n' and not inside_triple:
            logical_lines.append(''.join(buff))
            buff.clear()
            i += 1
            continue

        buff.append(ch)
        i += 1

    if buff:
        logical_lines.append(''.join(buff))

    if inside_triple:
        raise DslError('Unterminated multiline block (""" not closed)')

    return logical_lines

class DslInterpreter:
    placeholder_pattern = re.compile(r"\[<([^\]]+\.(?:script|txt))>]")

    def __init__(self, character: "Character"):
        self.character = character
        char_ctx_filter.set_character_id(getattr(character, "char_id", "NO_CHAR_INIT"))

        if not hasattr(character, 'prompts_root') or not character.prompts_root:
            raise ValueError("DslInterpreter: Character object must have a valid 'prompts_root' attribute.")
        self.actual_prompts_root = os.path.abspath(character.prompts_root)

        self._context_dir_stack: list[str] = []

        # ----------  В С Т А В К И  ------------------------------------
        # set_insert("SYS_INFO", "...") запоминает данные, подставляемые
        # затем вместо {{SYS_INFO}}
        self._insert_values: dict[str, str] = {}

    @contextmanager
    def _use_base(self, base_dir: str):
        self._context_dir_stack.append(os.path.abspath(base_dir))
        try:
            yield
        finally:
            self._context_dir_stack.pop()

    def _resolve_path(self, rel_path: str) -> str:
        # --- 0. Всегда пользуемся абсолютным PROMPTS_ROOT
        prompts_root_abs = self.actual_prompts_root  # он уже os.path.abspath()

        # --- 1. Общие расшаренные каталоги ----------------------------------
        if rel_path.startswith(("_CommonPrompts/", "_CommonScripts/")):
            return secure_join(prompts_root_abs, rel_path)

        # Текущий «рабочий» каталог (директория файла, в котором мы сейчас)
        current_dir_candidate = (
            self._context_dir_stack[-1]
            if self._context_dir_stack
            else self.character.base_data_path 
        )
        current_dir = os.path.abspath(current_dir_candidate)  # гарантируем абсолютный

        # --- 2. Пути вида ./something.txt -----------------------------------
        if rel_path.startswith("./"):
            # убираем './' и склеиваем
            return secure_join(current_dir, rel_path[2:])

        # --- 3. Пути вида ../something.txt ----------------------------------
        if rel_path.startswith("../"):
            tentative = os.path.abspath(os.path.normpath(os.path.join(current_dir, rel_path)))
            
            # Безопасность: не выходим за пределы prompts_root_abs
            # Используем нормализованные пути для проверки startswith
            norm_prompts_root_abs = os.path.normpath(prompts_root_abs)
            norm_tentative = os.path.normpath(tentative)

            if not (norm_tentative.startswith(norm_prompts_root_abs + os.sep) or norm_tentative == norm_prompts_root_abs):
                 # Проверка через commonpath как дополнительная мера, если startswith не сработал как ожидалось
                try:
                    if os.path.commonpath([prompts_root_abs, tentative]) != prompts_root_abs:
                        raise DslError(
                            f"SecurityError: Path '{tentative}' attempts to go outside the designated Prompts root '{prompts_root_abs}'.",
                            script_path=tentative,
                        )
                except ValueError: # Обработка случая разных дисков
                    raise DslError(
                        f"SecurityError: Path '{tentative}' cannot be safely combined with Prompts root '{prompts_root_abs}' (e.g., different drives or invalid path structure).",
                        script_path=tentative,
                    )
            return tentative

        # --- 4. Пути по умолчанию (относительно base_data_path персонажа) ---
        # self.character.base_data_path уже абсолютный (actual_prompts_root/char_id)
        # secure_join использует его как базу.
        return secure_join(self.character.base_data_path, rel_path)

    def _load_text(self, abs_path: str, ctx="") -> str:
        try:
            with open(abs_path, encoding="utf-8") as f:
                return f.read().rstrip()
        except FileNotFoundError:
            dsl_execution_logger.error(f"File not found '{abs_path}' (in {ctx})")
            raise DslError(f"File not found '{abs_path}' (in {ctx})", script_path=ctx)
        except Exception as e:
            dsl_execution_logger.error(f"Error reading '{abs_path}': {e}", exc_info=True)
            raise DslError(f"Error reading '{abs_path}': {e}", script_path=ctx, original_exception=e)

    def _eval_expr(self, expr: str,
                   script_path: str,
                   line_num: int,
                   line_content: str):
        safe_globals = {
            "__builtins__": {
                "str": str, "int": int, "float": float,
                "len": len, "round": round, "abs": abs,
                "max": max, "min": min, "True": True,
                "False": False, "None": None,
            }
        }
        local_vars = self.character.variables.copy()

        def _raise_dsl_error(e: Exception, custom_msg: str = ""):
            err_msg = custom_msg or f"Error evaluating '{expr}': {type(e).__name__} - {e}"
            dsl_script_logger.error(
                f"{err_msg} in script '{os.path.basename(script_path)}' line {line_num}: \"{line_content.strip()}\"",
                exc_info=True
            )
            raise DslError(
                err_msg,
                script_path=script_path,
                line_num=line_num,
                line_content=line_content,
                original_exception=e
            ) from e

        try:
            if expr.lstrip().startswith(("f'", 'f"', 'f"""')):
                return eval(expr, safe_globals, local_vars)
            return eval(expr, safe_globals, local_vars)
        except TypeError as e:
            msg_lower = str(e).lower()
            is_concat_problem = (
                "can only concatenate str" in msg_lower
                or (
                    "unsupported operand type(s) for +" in msg_lower
                    and "str" in msg_lower
                )
            )
            if not is_concat_problem:
                _raise_dsl_error(e)

            dsl_script_logger.debug(
                "Attempting auto-str cast for TypeError in expression '%s' (%s:%d)",
                expr, os.path.basename(script_path), line_num
            )
            fixed_locals = {
                k: (str(v) if isinstance(v, (int, float, bool)) else v)
                for k, v in local_vars.items()
            }
            try:
                return eval(expr, safe_globals, fixed_locals)
            except Exception as retry_exc:
                _raise_dsl_error(e, f"Error evaluating '{expr}' (even after auto-str cast attempt for TypeError): {type(e).__name__} - {e}")
        except (NameError, Exception) as e:
            _raise_dsl_error(e)


    def _eval_condition(self, cond: str, script_path: str, line_num: int, line_content: str):
        py_cond = cond.replace(" AND ", " and ").replace(" OR ", " or ")
        try:
            res = self._eval_expr(py_cond, script_path, line_num, line_content)
            return bool(res)
        except DslError: # Already logged by _eval_expr
            raise
        except Exception as e:
            dsl_script_logger.error(
                f"Cannot convert condition '{cond}' result to bool in script '{os.path.basename(script_path)}' line {line_num}: \"{line_content.strip()}\"",
                exc_info=True
            )
            raise DslError(
                f"Cannot convert condition '{cond}' result to bool",
                script_path=script_path, line_num=line_num, line_content=line_content, original_exception=e
            )

    _INLINE_LOAD_RE = re.compile(
        r"""\bLOAD                      # ключевое слово
             (?:\s+([A-Z0-9_]+))?       # ①  TAG   (опц.)
             \s+FROM\s+                 #   FROM
             (['"])(.+?)\2              # ② "path/to/file"
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    def _expand_inline_loads(
        self,
        expr: str,
        *,
        script_path: str,
        line_num: int,
        line_content: str,
    ) -> str:
        """
        Находит в expr все вхождения
            LOAD  TAG?  FROM  "file"
        и заменяет их на Python-литералы с уже загруженным текстом.
        Возвращает ИЗМЕНЁННУЮ строку-выражение, готовую к eval().
        """

        def _handle_single(match: re.Match) -> str:
            tag_name = match.group(1)          # может быть None
            path     = match.group(3)

            abs_path = self._resolve_path(path)

            # --- целиком файл -----------------------------------------
            if tag_name is None:
                raw = self._load_text(abs_path, f"inline LOAD in {script_path}:{line_num}")

            # --- секция [#TAG]/[/TAG] ---------------------------------
            else:
                raw = self._extract_tag_section(abs_path, tag_name)

            processed = self.process_template_content(
                raw,
                f"inline LOAD ({tag_name or 'FULL'}) FROM {path} in {os.path.basename(script_path)}:{line_num}",
            )

            # превращаем в валидный python-литерал
            return repr(processed)

        # заменяем ВСЕ inline-LOAD’ы на готовые строковые литералы
        try:
            return self._INLINE_LOAD_RE.sub(_handle_single, expr)
        except DslError:
            raise                                 # уже залогировано
        except Exception as e:
            raise DslError(
                f"Cannot expand inline LOADs inside expression '{expr}': {e}",
                script_path=script_path,
                line_num=line_num,
                line_content=line_content,
                original_exception=e,
            ) from e

    def execute_dsl_script(self, rel_script: str) -> str:
        """
        Выполняет .script-файл и возвращает строку результата.
        Поддерживает:
            • RETURN <expr>
            • RETURN LOAD_REL "path"
            • RETURN LOAD     "path"
            • RETURN LOAD <TAG_NAME> FROM "path"
        """
        full_script_path = ""
        returned_value_for_log: bool | None = None
        try:
            # --- абсолютный путь скрипта --------------------------------
            full_script_path = self._resolve_path(rel_script)

            # --- локальный «рабочий» каталог для вложенных путей ---------
            with self._use_base(os.path.dirname(full_script_path)):
                dsl_execution_logger.info(
                    f"Executing DSL script: {rel_script} (resolved: {full_script_path})"
                )

                # --- читаем файл и режем на логические строки -------------
                content = self._load_text(full_script_path, f"script {rel_script}")
                logical_lines = _split_into_logical_lines(content)

                if_stack: list[dict[str, Any]] = []   # стек IF-блоков
                returned: str | None = None

                # =========================================================
                #             ГЛАВНЫЙ ЦИКЛ ПО СТРОКАМ СКРИПТА
                # =========================================================
                for num, raw in enumerate(logical_lines, 1):
                    stripped = raw.strip()

                    # --- пустые строки / комментарии ---------------------
                    if not stripped or stripped.startswith("//"):
                        continue

                    skipping = any(level["skip"] for level in if_stack)
                    cmd_for_log = stripped.split(maxsplit=1)[0].upper()

                    # -----------------------------------------------------
                    #                 IF / ELSEIF / ELSE / ENDIF
                    # -----------------------------------------------------
                    if cmd_for_log == "IF":
                        cond_str = stripped[3:].rstrip()
                        if cond_str.upper().endswith(" THEN"):
                            cond_str = cond_str[:-5].rstrip()

                        parent_skip  = skipping
                        cond_met     = False
                        if not parent_skip:
                            cond_met = self._eval_condition(
                                cond_str, full_script_path, num, raw
                            )
                        dsl_execution_logger.debug(
                            f"IF '{cond_str}' → {cond_met}  "
                            f"({os.path.basename(full_script_path)}:{num}), skip={parent_skip}"
                        )
                        if_stack.append(
                            {"branch_taken": cond_met, "skip": parent_skip or not cond_met}
                        )
                        continue

                    if cmd_for_log == "ELSEIF":
                        if not if_stack:
                            raise DslError("ELSEIF without IF", full_script_path, num, raw)

                        lvl          = if_stack[-1]
                        parent_skip  = any(l["skip"] for l in if_stack[:-1])
                        cond_met_els = False
                        if not parent_skip and not lvl["branch_taken"]:
                            cond_str = stripped[7:].rstrip()
                            if cond_str.upper().endswith(" THEN"):
                                cond_str = cond_str[:-5].rstrip()
                            cond_met_els      = self._eval_condition(
                                cond_str, full_script_path, num, raw
                            )
                            lvl["branch_taken"] = cond_met_els
                            lvl["skip"]         = not cond_met_els
                        else:
                            lvl["skip"] = True
                        dsl_execution_logger.debug(
                            f"ELSEIF, branch_taken={lvl['branch_taken']} "
                            f"skip={lvl['skip']} ({os.path.basename(full_script_path)}:{num})"
                        )
                        continue

                    if cmd_for_log == "ELSE":
                        if not if_stack:
                            raise DslError("ELSE without IF", full_script_path, num, raw)

                        lvl         = if_stack[-1]
                        parent_skip = any(l["skip"] for l in if_stack[:-1])
                        lvl["skip"] = parent_skip or lvl["branch_taken"]
                        if not lvl["skip"]:
                            lvl["branch_taken"] = True
                        dsl_execution_logger.debug(
                            f"ELSE skip={lvl['skip']} ({os.path.basename(full_script_path)}:{num})"
                        )
                        continue

                    if cmd_for_log == "ENDIF":
                        if not if_stack:
                            raise DslError("ENDIF without IF", full_script_path, num, raw)
                        if_stack.pop()
                        dsl_execution_logger.debug(
                            f"ENDIF ({os.path.basename(full_script_path)}:{num})"
                        )
                        continue
                    # -----------------------------------------------------

                    if skipping:
                        # Находимся в «пропускаемом» IF-блоке
                        continue

                    # -----------------------------------------------------
                    #                  ОБЫЧНЫЕ КОМАНДЫ
                    # -----------------------------------------------------
                    parts   = stripped.split(maxsplit=1)
                    command = parts[0].upper()
                    args    = parts[1] if len(parts) > 1 else ""

                    # ---------- SET --------------------------------------
                    if command == "SET":
                        if "=" not in args:
                            raise DslError("SET requires '='", full_script_path, num, raw)
                        var, expr = [s.strip() for s in args.split("=", 1)]
                        expr = self._expand_inline_loads(
                                    expr,
                                    script_path=full_script_path,
                                    line_num=num,
                                    line_content=raw,
                        )
                        value = self._eval_expr(expr, full_script_path, num, raw)
                        self.character.variables[var] = value
                        dsl_execution_logger.debug(
                            f"SET {var} = {value} "
                            f"({os.path.basename(full_script_path)}:{num})"
                        )
                        continue

                    # ---------- LOG --------------------------------------
                    if command == "LOG":
                        val     = self._eval_expr(args, full_script_path, num, raw)
                        prefix  = f"{os.path.basename(full_script_path)}:{num}"
                        COLUMN  = 40
                        message = f"{prefix.ljust(COLUMN)}| {val}"
                        dsl_script_logger.info(message)
                        continue

                    # ---------- RETURN -----------------------------------
                    if command == "RETURN":
                        raw_arg = args.strip()

                        # ───────── раскрываем inline LOAD'ы ────────────
                        raw_arg_expanded = self._expand_inline_loads(
                            raw_arg,
                            script_path=full_script_path,
                            line_num=num,
                            line_content=raw,
                        )

                        # 1) RETURN LOAD_REL ...
                        if raw_arg.upper().startswith(("LOAD_REL ", "LOADREL ")):
                            rel = raw_arg.split(None, 1)[1].strip().strip('"').strip("'")
                            txt = self._load_text(
                                self._resolve_path(rel),
                                f"LOAD_REL in {rel_script}:{num}",
                            )
                            txt = self._remove_tag_markers(txt)          # ← добавлено

                        # 2) RETURN LOAD <TAG> FROM "path"
                        elif raw_arg.upper().startswith("LOAD "):
                            after_load = raw_arg[5:].strip()
                            m = re.match(
                                r"([A-Z0-9_]+)\s+FROM\s+(.+)", after_load, re.IGNORECASE
                            )
                            if m:
                                tag_name = m.group(1).upper()
                                path_str = m.group(2).strip().strip('"').strip("'")
                                abs_path = self._resolve_path(path_str)
                                raw_tag  = self._extract_tag_section(abs_path, tag_name)
                                txt = self.process_template_content(
                                    raw_tag,
                                    f"LOAD {tag_name} FROM {path_str} in {rel_script}:{num}",
                                )
                            else:
                                # 3) RETURN LOAD "whole_file.txt"
                                rel_file = after_load.strip().strip('"').strip("'")
                                txt = self._load_text(
                                    self._resolve_path(rel_file),
                                    f"LOAD in {rel_script}:{num}",
                                )
                                txt = self._remove_tag_markers(txt)      # ← добавлено

                        # 4) RETURN <expression>  (уже с inline LOAD'ами)
                        else:
                            txt = str(
                                self._eval_expr(
                                    raw_arg_expanded, full_script_path, num, raw
                                )
                            )

                        # --- рекурсивная обработка шаблонов/вставок --------
                        returned = self.process_template_content(
                            txt, f"RETURN in {rel_script}:{num}"
                        )
                        returned_value_for_log = returned is not None
                        dsl_execution_logger.debug(
                            f"RETURN (value exists={returned_value_for_log}) "
                            f"({os.path.basename(full_script_path)}:{num})"
                        )
                        return returned

                    # ---------- НЕИЗВЕСТНАЯ КОМАНДА -----------------------
                    dsl_execution_logger.error(
                        f"Unknown DSL command '{command}' in "
                        f"{os.path.basename(full_script_path)}:{num} "
                        f"Line: \"{raw.strip()}\""
                    )
                    raise DslError(
                        f"Unknown DSL command '{command}'", full_script_path, num, raw
                    )

                # =====================================================
                #          КОНЕЦ ФАЙЛА (IF-стек пуст?  Возврат)
                # =====================================================
                if if_stack:
                    dsl_execution_logger.warning(
                        f"Script {rel_script} ended with unterminated IF block(s)."
                    )

                returned_value_for_log = returned is not None
                return returned or ""

        # ----------------------------------------------------------------
        #                         ОБРАБОТКА ОШИБОК
        # ----------------------------------------------------------------
        except DslError as e:
            dsl_execution_logger.error(
                f"DslError during execution of {rel_script} "
                f"(resolved: {e.script_path or full_script_path}): "
                f"{e.message} at line {e.line_num}",
                exc_info=False,
            )
            print(f"{RED}{str(e)}{RST}", file=sys.stderr)
            return (
                f"[DSL ERROR IN "
                f"{os.path.basename(e.script_path or full_script_path or rel_script)}]"
            )

        except Exception as e:
            dsl_execution_logger.error(
                f"Unexpected Python error during execution of {rel_script} "
                f"(resolved: {full_script_path}): {e}",
                exc_info=True,
            )
            print(
                f"{RED}Unexpected Python error in {rel_script}: {e}{RST}\n"
                f"{traceback.format_exc()}",
                file=sys.stderr,
            )
            return f"[PY ERROR IN {os.path.basename(full_script_path or rel_script)}]"

        finally:
            dsl_execution_logger.info(
                f"Finished DSL script: {rel_script}. Returned value: "
                f"{returned_value_for_log if returned_value_for_log is not None else False}"
            )

    def process_template_content(self, text: str, ctx="template") -> str:
        if not isinstance(text, str):
            text = str(text)

        depth = 0
        original_text_for_recursion_check = text

        while self.placeholder_pattern.search(text) and depth < MAX_RECURSION:
            depth += 1

            def repl(match):
                rel_path = match.group(1)
                dsl_execution_logger.debug(
                    f"Processing placeholder: {rel_path} in context '{ctx}', depth {depth}"
                )
                try:
                    abs_path = self._resolve_path(rel_path)
                    with self._use_base(os.path.dirname(abs_path)):
                        if rel_path.endswith(".script"):
                            return self.execute_dsl_script(rel_path)

                        if rel_path.endswith(".txt"):
                            raw_txt = self._load_text(
                                abs_path, f"placeholder {rel_path} in {ctx}"
                            )
                            return self.process_template_content(
                                raw_txt, f"{rel_path} (recursive from {ctx})"
                            )

                        dsl_execution_logger.error(
                            f"Unknown placeholder type: {rel_path} in {ctx}"
                        )
                        raise DslError("Unknown placeholder type", script_path=rel_path)

                except DslError as de:
                    dsl_execution_logger.error(
                        f"DSL ERROR while processing placeholder {rel_path} "
                        f"in {ctx}: {de}"
                    )
                    print(f"{RED}Error processing placeholder {rel_path}: {de}{RST}", file=sys.stderr)
                    return f"[DSL ERROR {rel_path}]"
                except Exception as exc:
                    dsl_execution_logger.error(
                        f"Unexpected Python error processing placeholder {rel_path} in {ctx}: {exc}",
                        exc_info=True
                    )
                    print(
                        f"{RED}Unexpected Python error in placeholder {rel_path}: {exc}{RST}\n"
                        f"{traceback.format_exc()}",
                        file=sys.stderr
                    )
                    return f"[PY ERROR {rel_path}]"

            processed_text = self.placeholder_pattern.sub(repl, text)
            if processed_text == text and self.placeholder_pattern.search(text):
                # Stalled
                dsl_execution_logger.error(
                    f"Template processing stalled at depth {depth} in context '{ctx}'. "
                    f"Unresolved placeholders remain but no change occurred. "
                    f"Placeholder: {self.placeholder_pattern.search(text).group(0)}"
                )
                text = self.placeholder_pattern.sub(
                    f"[STALLED DSL ERROR {self.placeholder_pattern.search(text).group(1)}]",
                    text,
                    count=1,
                )
            else:
                text = processed_text

            if depth == MAX_RECURSION - 1 and self.placeholder_pattern.search(text):
                dsl_execution_logger.warning(
                    f"Nearing max recursion depth ({depth+1}/{MAX_RECURSION}) in '{ctx}'. "
                    f"Next placeholder: "
                    f"{self.placeholder_pattern.search(text).group(0) if self.placeholder_pattern.search(text) else 'None'}"
                )

        if depth >= MAX_RECURSION:
            dsl_execution_logger.error(
                f"Max recursion depth ({MAX_RECURSION}) reached in template processing for context '{ctx}'. "
                f"Original text snippet: '{original_text_for_recursion_check[:100]}...'"
            )
            text += f"\n[DSL ERROR: MAX RECURSION {MAX_RECURSION} REACHED IN '{ctx}']"
        return text

    # region Вставки
    # ------------------------------------------------------------------ #
    #                       В С Т А В К И                                #
    # ------------------------------------------------------------------ #
    def set_insert(self, name: str, content: Any | None):
        """
        Сохраняет содержимое «вставки».
        content может быть:
            • str           – берётся как есть
            • list / tuple  – объединяется через '\n'
            • всё остальное – str(content)
        """
        if content is None:
            return

        if isinstance(content, (list, tuple)):
            content = "\n".join(map(str, content))

        self._insert_values[name.upper()] = str(content)

    def _apply_inserts(self, text: str, *, ctx: str = "") -> str:
        """
        Подставляет значения «вставок» в текст и предупреждает,
        если в шаблоне отсутствуют обязательные вставки.
        """
        # ---------- замена --------------------------------------------
        def _replace(match: re.Match):
            placeholder = match.group(1).upper()
            return self._insert_values.get(placeholder, match.group(0))

        processed = INSERT_PATTERN.sub(_replace, text)

        # ---------- проверка обязательных вставок ----------------------
        for mandatory in MANDATORY_INSERTS:
            token = f"{{{{{mandatory}}}}}"
            if token not in text:
                dsl_execution_logger.warning(
                    f"Mandatory insert {token} not found while processing {ctx or 'template'}"
                )

        return processed
    # endregion

    # region Теги (настоящие)
    _SECTION_MARKER_RE = re.compile(
        r"^[ \t]*\[(?:#|/)\s*[A-Z0-9_]+\s*][ \t]*\r?\n?",  # вся строка
        re.IGNORECASE | re.MULTILINE,
    )

    def _remove_tag_markers(self, text: str) -> str:
        """
        Удаляет ВСЕ строки, содержащие только
            [#TAG_NAME]   или   [/TAG_NAME]
        (регистр не важен).  Остальной текст остаётся нетронутым.
        """
        return self._SECTION_MARKER_RE.sub("", text)

    def _extract_tag_section(self, abs_path: str, tag_name: str) -> str:
        raw = self._load_text(abs_path, f"extract tag {tag_name}")

        tag_up  = tag_name.upper()
        pattern = re.compile(
            rf"\[#\s*{tag_up}\s*](.*?)\[/\s*{tag_up}\s*]",
            re.IGNORECASE | re.DOTALL,
        )
        m = pattern.search(raw)
        if not m:
            raise DslError(
                f"Tag section [#{tag_name}] not found in '{abs_path}'",
                script_path=abs_path,
            )

        content = m.group(1)

        # --- убираем *один* перевод после [#TAG] (если он есть) --------
        if content.startswith("\n"):
            content = content[1:]

        return content   # БЕЗ strip()/rstrip() – всё сохраняем как есть
    
    
    _INLINE_LOAD_RE = re.compile(
        r"""\bLOAD                      # ключевое слово
             (?:\s+([A-Z0-9_]+))?       # ① TAG (опц.)
             \s+FROM\s+                 #   FROM
             (['"])(.+?)\2              # ② "path/to/file"
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    def _expand_inline_loads(
        self,
        expr: str,
        *,
        script_path: str,
        line_num: int,
        line_content: str,
    ) -> str:
        """
        Заменяет все вхождения
            LOAD [TAG] FROM "file"
        в expr на python-литералы с уже подставленным содержимым.
        """

        def _handle_single(match: re.Match) -> str:
            tag_name = match.group(1)          # None => грузим ВЕСЬ файл
            path     = match.group(3)
            abs_path = self._resolve_path(path)

            # ---------- берём целиком файл -----------------------------
            if tag_name is None:
                raw = self._load_text(
                    abs_path, f"inline LOAD in {script_path}:{line_num}"
                )
                raw = self._remove_tag_markers(raw)   # <<< НОВОЕ
            # ---------- или конкретную секцию --------------------------
            else:
                raw = self._extract_tag_section(abs_path, tag_name)

            processed = self.process_template_content(
                raw,
                f"inline LOAD ({tag_name or 'FULL'}) FROM {path} "
                f"in {os.path.basename(script_path)}:{line_num}",
            )
            return repr(processed)  # превращаем в python-литерал

        return self._INLINE_LOAD_RE.sub(_handle_single, expr)

    # endregion

    def process_main_template_file(self, rel_path: str) -> str:
        full_resolved_path = ""
        try:
            char_ctx_filter.set_character_id(getattr(self.character, "char_id", "NO_CHAR_CTX"))
            dsl_execution_logger.info(f"Processing main template file: {rel_path} for character {self.character.char_id}")
            full_resolved_path = self._resolve_path(rel_path)
            raw_template_content = self._load_text(full_resolved_path, f"main template {rel_path}")
            final_prompt = self.process_template_content(
                raw_template_content, f"main template {rel_path}"
            )
            final_prompt = self._apply_inserts(
                final_prompt, ctx=f"main template {rel_path}"
            )
            dsl_execution_logger.info(f"Successfully processed main template: {rel_path}")
            return final_prompt
        except DslError as e:
            # Error should have been logged by the function that raised it (_load_text, process_template_content via execute_dsl_script)
            dsl_execution_logger.error(f"DslError while processing main template '{rel_path}' (resolved: {e.script_path or full_resolved_path}): {e.message}", exc_info=False)
            print(f"{RED}{str(e)}{RST}", file=sys.stderr)
            return f"[DSL ERROR IN MAIN TEMPLATE {os.path.basename(e.script_path or full_resolved_path or rel_path)} - CHECK LOGS]"
        except Exception as e:
            dsl_execution_logger.error(f"Unexpected Python error processing main template '{rel_path}' (resolved: {full_resolved_path}): {e}", exc_info=True)
            print(f"{RED}Unexpected Python error in main template {rel_path}: {e}{RST}\n{traceback.format_exc()}", file=sys.stderr)
            return f"[PY ERROR IN MAIN TEMPLATE {os.path.basename(full_resolved_path or rel_path)} - CHECK LOGS]"