# File: logic/dsl_engine.py
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import sys
import traceback
from typing import List
from contextlib import contextmanager

RED = "\033[91m"
YEL = "\033[93m"
RST = "\033[0m"

PROMPTS_ROOT = os.path.abspath("Prompts")
LOG_DIR = "Logs"
LOG_FILE = os.path.join(LOG_DIR, "dsl_execution.log")
MAX_RECURSION = 10
MULTILINE_DELIM = '"""'
MAX_LOG_BYTES = 2_000_000
BACKUP_COUNT = 3

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
    full = os.path.normpath(os.path.join(base, *paths))
    if os.path.commonpath([base, full]) != base:
        raise DslError(f"SecurityError: '{full}' is outside '{base}'", script_path=full)
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
        
        self._context_dir_stack: list[str] = []

    @contextmanager
    def _use_base(self, base_dir: str):
        """
        Временно добавляет base_dir в стек «текущих» директорий.
        Нужно для корректного резолва относительных путей внутри
        вложенных .script/.txt, включая рекурсивные PLACEHOLDER’ы.
        """
        self._context_dir_stack.append(base_dir)
        try:
            yield
        finally:
            self._context_dir_stack.pop()

    def _resolve_path(self, rel_path: str) -> str:
        # --- 0. Всегда пользуемся абсолютным PROMPTS_ROOT
        prompts_root_abs = PROMPTS_ROOT  # он уже os.path.abspath()

        # --- 1. Общие расшаренные каталоги ----------------------------------
        if rel_path.startswith(("_CommonPrompts/", "_CommonScripts/")):
            return secure_join(prompts_root_abs, rel_path)

        # Текущий «рабочий» каталог (директория файла, в котором мы сейчас)
        current_dir = (
            self._context_dir_stack[-1]
            if self._context_dir_stack
            else self.character.base_data_path
        )
        current_dir = os.path.abspath(current_dir)  # гарантируем абсолютный

        # --- 2. Пути вида ./something.txt -----------------------------------
        if rel_path.startswith("./"):
            # убираем './' и склеиваем
            return secure_join(current_dir, rel_path[2:])

        # --- 3. Пути вида ../something.txt ----------------------------------
        if rel_path.startswith("../"):
            tentative = os.path.abspath(os.path.normpath(os.path.join(current_dir, rel_path)))

            # Безопасность: не выходим за пределы PROMPTS_ROOT
            try:
                if os.path.commonpath([prompts_root_abs, tentative]) != prompts_root_abs:
                    raise DslError(
                        f"SecurityError: '{tentative}' is outside '{prompts_root_abs}'",
                        script_path=tentative,
                    )
            except ValueError:
                # Разные диски или абсолютный+относительный путь —
                # считаем это нарушением границ
                raise DslError(
                    f"SecurityError: '{tentative}' cannot be combined with '{prompts_root_abs}'",
                    script_path=tentative,
                )

            return tentative

        # --- 4. Старый (по умолчанию) режим ---------------------------------
        # base_data_path может быть относительным → делаем абсолютным
        base_abs = os.path.abspath(self.character.base_data_path)
        return secure_join(base_abs, rel_path)

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


    def execute_dsl_script(self, rel_script: str) -> str:
        """
        Полностью прежняя логика + обёртка _use_base, чтобы всё,
        что встречается ВНУТРИ этого скрипта, считалось относительным
        к директории текущего скрипта.
        """
        full_script_path = ""
        returned_value_for_log = None
        try:
            # Сначала получаем абсолютный путь, после чего «запоминаем» его dir
            full_script_path = self._resolve_path(rel_script)
            with self._use_base(os.path.dirname(full_script_path)):
                dsl_execution_logger.info(
                    f"Executing DSL script: {rel_script} (resolved: {full_script_path})"
                )
                content = self._load_text(full_script_path, f"script {rel_script}")
                logical_lines = _split_into_logical_lines(content)

                if_stack = []
                returned = None

                for num, raw in enumerate(logical_lines, 1):
                    stripped = raw.strip()
                    if not stripped or stripped.startswith("//"):
                        continue

                    skipping = any(level['skip'] for level in if_stack)
                    cmd_for_log = stripped.split(maxsplit=1)[0].upper()

                    # ---------------  IF / ELSEIF / ELSE / ENDIF -------------
                    if cmd_for_log == "IF":
                        cond_str = stripped[3:].rstrip()
                        if cond_str.upper().endswith(" THEN"):
                            cond_str = cond_str[:-5].rstrip()
                        parent_skip = skipping
                        cond_met = False
                        if not parent_skip:
                            cond_met = self._eval_condition(cond_str, full_script_path, num, raw)
                        dsl_execution_logger.debug(
                            f"IF condition '{cond_str}' evaluated to {cond_met} in {os.path.basename(full_script_path)}:{num}. Skipping: {parent_skip}"
                        )
                        if_stack.append({"branch_taken": cond_met, "skip": parent_skip or not cond_met})
                        continue

                    if cmd_for_log == "ELSEIF":
                        if not if_stack:
                            raise DslError("ELSEIF without IF", full_script_path, num, raw)
                        level = if_stack[-1]
                        parent_skip = any(l['skip'] for l in if_stack[:-1])
                        cond_met_elseif = False
                        if not parent_skip and not level['branch_taken']:
                            cond_str_elseif = stripped[7:].rstrip()
                            if cond_str_elseif.upper().endswith(" THEN"):
                                cond_str_elseif = cond_str_elseif[:-5].rstrip()
                            cond_met_elseif = self._eval_condition(cond_str_elseif, full_script_path, num, raw)
                            level['branch_taken'] = cond_met_elseif
                            level['skip'] = not cond_met_elseif
                        else:
                            level['skip'] = True
                        dsl_execution_logger.debug(
                            f"ELSEIF evaluated. Branch taken: {level.get('branch_taken', False)}, "
                            f"Skip: {level['skip']} in {os.path.basename(full_script_path)}:{num}. "
                            f"Parent skip: {parent_skip}"
                        )
                        continue

                    if cmd_for_log == "ELSE":
                        if not if_stack:
                            raise DslError("ELSE without IF", full_script_path, num, raw)
                        level = if_stack[-1]
                        parent_skip = any(l['skip'] for l in if_stack[:-1])
                        level['skip'] = parent_skip or level['branch_taken']
                        if not level['skip']:
                            level['branch_taken'] = True
                        dsl_execution_logger.debug(
                            f"ELSE evaluated. Skip: {level['skip']} in {os.path.basename(full_script_path)}:{num}. "
                            f"Parent skip: {parent_skip}"
                        )
                        continue

                    if cmd_for_log == "ENDIF":
                        if not if_stack:
                            raise DslError("ENDIF without IF", full_script_path, num, raw)
                        if_stack.pop()
                        dsl_execution_logger.debug(f"ENDIF in {os.path.basename(full_script_path)}:{num}")
                        continue
                    # ---------------------------------------------------------

                    if skipping:
                        continue

                    parts = stripped.split(maxsplit=1)
                    command = parts[0].upper()
                    args = parts[1] if len(parts) > 1 else ""

                    # ---------- SET -----------------------------------------
                    if command == "SET":
                        if "=" not in args:
                            raise DslError("SET requires '='", full_script_path, num, raw)
                        var, expr = [s.strip() for s in args.split("=", 1)]
                        value = self._eval_expr(expr, full_script_path, num, raw)
                        self.character.variables[var] = value
                        dsl_execution_logger.debug(
                            f"SET {var} = {value} in {os.path.basename(full_script_path)}:{num}"
                        )
                        continue

                    # ---------- LOG -----------------------------------------
                    if command == "LOG":
                        val = self._eval_expr(args, full_script_path, num, raw)
                        prefix = f"{os.path.basename(full_script_path)}:{num}"
                        COLUMN = 40
                        formatted = f"{prefix.ljust(COLUMN)}| {val}"
                        dsl_script_logger.info(formatted)
                        continue

                    # ---------- RETURN / LOAD / LOAD_REL --------------------
                    if command == "RETURN":
                        raw_arg = args.strip()
                        # Новая команда LOAD_REL
                        if raw_arg.upper().startswith(("LOAD_REL ", "LOADREL ")):
                            rel = raw_arg.split(None, 1)[1].strip().strip('"').strip("'")
                            txt = self._load_text(
                                self._resolve_path(rel), f"LOAD_REL in {rel_script}:{num}"
                            )
                        # Старая команда LOAD
                        elif raw_arg.upper().startswith("LOAD "):
                            rel = raw_arg[5:].strip().strip('"').strip("'")
                            txt = self._load_text(
                                self._resolve_path(rel), f"LOAD in {rel_script}:{num}"
                            )
                        else:
                            txt = str(self._eval_expr(raw_arg, full_script_path, num, raw))

                        returned = self.process_template_content(
                            txt, f"RETURN in {rel_script}:{num}"
                        )
                        returned_value_for_log = returned is not None
                        dsl_execution_logger.debug(
                            f"RETURN in {os.path.basename(full_script_path)}:{num}. "
                            f"Value exists: {returned_value_for_log}"
                        )
                        return returned

                    # ---------- Неизвестная команда ------------------------
                    dsl_execution_logger.error(
                        f"Unknown DSL command '{command}' in {os.path.basename(full_script_path)}:{num} "
                        f"Line: \"{raw.strip()}\""
                    )
                    raise DslError(f"Unknown DSL command '{command}'", full_script_path, num, raw)

                if if_stack:
                    dsl_execution_logger.warning(
                        f"Script {rel_script} ended with unterminated IF block(s)."
                    )

                returned_value_for_log = returned is not None
                return returned or ""

        except DslError as e:
            dsl_execution_logger.error(
                f"DslError during execution of {rel_script} (resolved: {e.script_path or full_script_path}): "
                f"{e.message} at line {e.line_num}",
                exc_info=False
            )
            print(f"{RED}{str(e)}{RST}", file=sys.stderr)
            return f"[DSL ERROR IN {os.path.basename(e.script_path or full_script_path or rel_script)}]"
        except Exception as e:
            dsl_execution_logger.error(
                f"Unexpected Python error during execution of {rel_script} "
                f"(resolved: {full_script_path}): {e}", exc_info=True
            )
            print(
                f"{RED}Unexpected Python error in {rel_script}: {e}{RST}\n{traceback.format_exc()}",
                file=sys.stderr
            )
            return f"[PY ERROR IN {os.path.basename(full_script_path or rel_script)}]"
        finally:
            dsl_execution_logger.info(
                f"Finished DSL script: {rel_script}. Returned value: "
                f"{returned_value_for_log if returned_value_for_log is not None else (returned is not None)}"
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

    def process_main_template_file(self, rel_path: str) -> str:
        full_resolved_path = ""
        try:
            char_ctx_filter.set_character_id(getattr(self.character, "char_id", "NO_CHAR_CTX"))
            dsl_execution_logger.info(f"Processing main template file: {rel_path} for character {self.character.char_id}")
            full_resolved_path = self._resolve_path(rel_path)
            raw_template_content = self._load_text(full_resolved_path, f"main template {rel_path}")
            final_prompt = self.process_template_content(raw_template_content, f"main template {rel_path}")
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