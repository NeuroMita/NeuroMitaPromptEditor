import re
import os
from typing import List, Dict, Any, Tuple, Optional

class SyntaxError:
    def __init__(self, message: str, line_num: int, line_content: str, error_type: str = "Syntax"):
        self.message = message
        self.line_num = line_num
        self.line_content = line_content
        self.error_type = error_type
    
    def __str__(self):
        return f"[{self.error_type} Error] Line {self.line_num}: '{self.line_content.strip()}' - {self.message}"

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
        raise SyntaxError('Unterminated multiline block (""" not closed)', 0, script_text)
    
    return logical_lines

class PostScriptSyntaxChecker:
    # Matches: LOAD TAG_NAME FROM "file.txt" or LOAD FROM "file.txt"
    _INLINE_LOAD_RE = re.compile(
        r"\bLOAD"
        r"(?:\s+([A-Z0-9_]+))?"  # Optional TAG_NAME
        r"\s+FROM\s+"
        r"(['\"])(.+?)\2",  # Quoted file path
        re.IGNORECASE | re.VERBOSE,
    )
    
    # Matches: [<file.script>], [<path/file.txt>], [<module.system>]
    _PLACEHOLDER_PATTERN = re.compile(r"\[<([^>]+\.(?:script|txt|system))>\]")
    
    # Matches: {{INSERT_NAME}}, {{SYS_INFO}}
    _INSERT_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

    # Matches: RULE rule_name
    _RULE_START_PATTERN = re.compile(r"RULE\s+(.+)", re.IGNORECASE)
    
    # Matches: MATCH TEXT "pattern" or MATCH REGEX "pattern"
    _MATCH_PATTERN = re.compile(r"MATCH\s+(TEXT|REGEX)\s+(.+)", re.IGNORECASE)
    
    # Matches: CAPTURE(var1, var2, var3)
    _CAPTURE_PATTERN = re.compile(r"CAPTURE\s*KATEX_INLINE_OPEN(.*?)KATEX_INLINE_CLOSE", re.IGNORECASE)
    
    # Matches: ACTIONS
    _ACTIONS_START_PATTERN = re.compile(r"ACTIONS", re.IGNORECASE)
    
    # Matches: END_ACTIONS
    _END_ACTIONS_PATTERN = re.compile(r"END_ACTIONS", re.IGNORECASE)
    
    # Matches: END_RULE
    _END_RULE_PATTERN = re.compile(r"END_RULE", re.IGNORECASE)
    
    # Matches: DEBUG_DISPLAY
    _DEBUG_DISPLAY_START_PATTERN = re.compile(r"DEBUG_DISPLAY", re.IGNORECASE)
    
    # Matches: END_DEBUG_DISPLAY
    _END_DEBUG_DISPLAY_PATTERN = re.compile(r"END_DEBUG_DISPLAY", re.IGNORECASE)
    
    # Matches: "Label": var_name or Label: var_name
    _DEBUG_DISPLAY_ENTRY_PATTERN = re.compile(r'^\s*("[^"]*"|\w+)\s*:\s*(\w+)\s*$', re.IGNORECASE)

    def __init__(self):
        self.errors: List[SyntaxError] = []
        self.variables: Dict[str, Any] = {}
        self.defined_rules: Dict[str, bool] = {}
        self.current_file_path: str = ""

    def _add_error(self, message: str, line_num: int, line_content: str, error_type: str = "Syntax"):
        self.errors.append(SyntaxError(message, line_num, line_content, error_type))

    def _validate_expression(self, expr: str, line_num: int, line_content: str, is_condition: bool = False):
        if expr.count('(') != expr.count(')'):
            self._add_error("Несбалансированные скобки в выражении.", line_num, line_content, "Expression")
        if expr.count('"') % 2 != 0 or expr.count("'") % 2 != 0:
            self._add_error("Несбалансированные кавычки в выражении.", line_num, line_content, "Expression")
        if self._INLINE_LOAD_RE.search(expr):
            pass
        if self._PLACEHOLDER_PATTERN.search(expr):
            pass
        if self._INSERT_PATTERN.search(expr):
            pass
        # Matches: ++, --, //, ==, etc (but allows ==, !=, <=, >=)
        if re.search(r'[+\-*/=]{2,}', expr) and not re.search(r'==|!=|<=|>=', expr):
            self._add_error("Повторяющиеся операторы в выражении.", line_num, line_content, "Expression")

    def check_dsl_syntax(self, script_content: str, file_path: str = "unknown_script.script") -> List[SyntaxError]:
        self.errors = []
        self.variables = {}
        self.current_file_path = file_path

        try:
            logical_lines = _split_into_logical_lines(script_content)
        except SyntaxError as e:
            self.errors.append(e)
            return self.errors

        if_stack: List[Dict[str, Any]] = []

        for num, raw_line in enumerate(logical_lines, 1):
            stripped_line = raw_line.strip()
            if not stripped_line or stripped_line.startswith("//"):
                continue

            command_part = stripped_line.split("//", 1)[0].strip()
            parts = command_part.split(maxsplit=1)
            command = parts[0].upper()
            args = parts[1] if len(parts) > 1 else ""

            if command == "IF":
                if not args.upper().endswith(" THEN"):
                    self._add_error("IF-условие должно заканчиваться на 'THEN'.", num, raw_line)
                cond_str = args[:-len(" THEN")].strip() if args.upper().endswith(" THEN") else args
                self._validate_expression(cond_str, num, raw_line, is_condition=True)
                if_stack.append({"type": "IF", "line": num})

            elif command == "ELSEIF":
                if not if_stack:
                    self._add_error("ELSEIF без соответствующего IF.", num, raw_line)
                if not args.upper().endswith(" THEN"):
                    self._add_error("ELSEIF-условие должно заканчиваться на 'THEN'.", num, raw_line)
                cond_str = args[:-len(" THEN")].strip() if args.upper().endswith(" THEN") else args
                self._validate_expression(cond_str, num, raw_line, is_condition=True)

            elif command == "ELSE":
                if not if_stack:
                    self._add_error("ELSE без соответствующего IF.", num, raw_line)
                if args:
                    self._add_error("ELSE не должен иметь аргументов.", num, raw_line)

            elif command == "ENDIF":
                if not if_stack:
                    self._add_error("ENDIF без соответствующего IF.", num, raw_line)
                else:
                    if_stack.pop()
                if args:
                    self._add_error("ENDIF не должен иметь аргументов.", num, raw_line)

            elif command == "SET":
                parts_after_set = args.split(maxsplit=1)
                if len(parts_after_set) > 1 and parts_after_set[0].upper() == "LOCAL":
                    args = parts_after_set[1]
                if "=" not in args:
                    self._add_error("Команда SET требует оператора '='.", num, raw_line)
                else:
                    var_name, expr = [s.strip() for s in args.split("=", 1)]
                    # Matches: valid_var_name123
                    if not var_name or not re.match(r"^[a-zA-Z0-9_]+$", var_name):
                        self._add_error(f"Некорректное имя переменной '{var_name}'.", num, raw_line, "Variable Naming")
                    self._validate_expression(expr, num, raw_line)
                    self.variables[var_name] = None

            elif command == "LOG":
                if not args:
                    self._add_error("Команда LOG требует аргумент.", num, raw_line)
                self._validate_expression(args, num, raw_line)

            elif command == "ADD_SYSTEM_INFO":
                if not args:
                    self._add_error("ADD_SYSTEM_INFO требует аргумент.", num, raw_line)
                else:
                    arg_u = args.strip().upper()
                    if arg_u.startswith(("LOAD_REL ", "LOADREL ")):
                        path_arg = args.split(None, 1)[1].strip().strip('"').strip("'")
                        if not path_arg:
                            self._add_error("LOAD_REL требует путь к файлу.", num, raw_line)
                        elif not (path_arg.endswith(".script") or path_arg.endswith(".txt") or path_arg.endswith(".system")):
                            self._add_error(f"LOAD_REL: Неподдерживаемое расширение '{os.path.basename(path_arg)}'.", num, raw_line, "File Type")
                    elif arg_u.startswith("LOAD "):
                        after_load = args[5:].strip()
                        # Matches: TAG_NAME FROM "file.txt"
                        m = re.match(r"([A-Z0-9_]+)\s+FROM\s+(.+)", after_load, re.IGNORECASE)
                        if m:
                            tag_name = m.group(1)
                            path_str = m.group(2).strip().strip('"').strip("'")
                            if not path_str:
                                self._add_error("LOAD FROM требует путь к файлу.", num, raw_line)
                            elif not (path_str.endswith(".script") or path_str.endswith(".txt") or path_str.endswith(".system")):
                                self._add_error(f"LOAD FROM: Неподдерживаемое расширение '{os.path.basename(path_str)}'.", num, raw_line, "File Type")
                            # Matches: TAG_NAME123
                            if not re.match(r"^[A-Z0-9_]+$", tag_name):
                                self._add_error(f"Некорректное имя тега '{tag_name}'.", num, raw_line, "Tag Naming")
                        else:
                            path_arg = after_load.strip().strip('"').strip("'")
                            if not path_arg:
                                self._add_error("LOAD требует путь к файлу.", num, raw_line)
                            elif not (path_arg.endswith(".script") or path_arg.endswith(".txt") or path_arg.endswith(".system")):
                                self._add_error(f"LOAD: Неподдерживаемое расширение '{os.path.basename(path_arg)}'.", num, raw_line, "File Type")
                    else:
                        self._validate_expression(args, num, raw_line)

            elif command == "RETURN":
                if not args:
                    self._add_error("Команда RETURN требует аргумент.", num, raw_line)
                if args.upper().startswith(("LOAD_REL ", "LOADREL ")):
                    path_arg = args.split(None, 1)[1].strip().strip('"').strip("'")
                    if not path_arg:
                        self._add_error("LOAD_REL требует путь к файлу.", num, raw_line)
                    elif not (path_arg.endswith(".script") or path_arg.endswith(".txt") or path_arg.endswith(".system")):
                        self._add_error(f"LOAD_REL: Неподдерживаемое расширение файла '{os.path.basename(path_arg)}'.", num, raw_line, "File Type")
                elif args.upper().startswith("LOAD "):
                    after_load = args[5:].strip()
                    # Matches: TAG_NAME FROM "file.txt"
                    m = re.match(r"([A-Z0-9_]+)\s+FROM\s+(.+)", after_load, re.IGNORECASE)
                    if m:
                        tag_name = m.group(1)
                        path_str = m.group(2).strip().strip('"').strip("'")
                        if not path_str:
                            self._add_error("LOAD FROM требует путь к файлу.", num, raw_line)
                        elif not (path_str.endswith(".script") or path_str.endswith(".txt") or path_str.endswith(".system")):
                            self._add_error(f"LOAD FROM: Неподдерживаемое расширение файла '{os.path.basename(path_str)}'.", num, raw_line, "File Type")
                        # Matches: TAG_NAME123
                        if not re.match(r"^[A-Z0-9_]+$", tag_name):
                            self._add_error(f"LOAD FROM: Некорректное имя тега '{tag_name}'.", num, raw_line, "Tag Naming")
                    else:
                        path_arg = after_load.strip().strip('"').strip("'")
                        if not path_arg:
                            self._add_error("LOAD требует путь к файлу.", num, raw_line)
                        elif not (path_arg.endswith(".script") or path_arg.endswith(".txt") or path_arg.endswith(".system")):
                            self._add_error(f"LOAD: Неподдерживаемое расширение файла '{os.path.basename(path_arg)}'.", num, raw_line, "File Type")
                else:
                    self._validate_expression(args, num, raw_line)

            elif command:
                self._add_error(f"Неизвестная команда DSL: '{command}'.", num, raw_line, "Unknown Command")

        if if_stack:
            for level in if_stack:
                self._add_error(f"Незакрытый блок IF, начатый на строке {level['line']}.", level['line'], logical_lines[level['line']-1], "Unterminated Block")

        return self.errors

    def check_postscript_syntax(self, script_content: str, file_path: str = "unknown_postscript.postscript") -> List[SyntaxError]:
        self.errors = []
        self.defined_rules = {}
        self.current_file_path = file_path

        logical_lines = script_content.splitlines()
        current_rule_name: Optional[str] = None
        in_actions_block = False
        in_debug_display_block = False

        for num, raw_line in enumerate(logical_lines, 1):
            stripped_line = raw_line.strip()
            if not stripped_line or stripped_line.startswith("//"):
                continue

            line_without_comment = stripped_line.split("//", 1)[0].strip()
            if not line_without_comment:
                continue

            rule_match = self._RULE_START_PATTERN.match(line_without_comment)
            if rule_match:
                if current_rule_name:
                    self._add_error(f"Незакрытое правило '{current_rule_name}'. Ожидался END_RULE.", num-1, logical_lines[num-2], "Unterminated Rule")
                current_rule_name = rule_match.group(1).strip()
                # Matches: rule_name123
                if not re.match(r"^[a-zA-Z0-9_]+$", current_rule_name):
                    self._add_error(f"Некорректное имя правила '{current_rule_name}'.", num, raw_line, "Rule Naming")
                if current_rule_name in self.defined_rules:
                    self._add_error(f"Повторное определение правила '{current_rule_name}'.", num, raw_line, "Duplicate Rule")
                self.defined_rules[current_rule_name] = False
                in_actions_block = False
                in_debug_display_block = False
                continue

            match_match = self._MATCH_PATTERN.match(line_without_comment)
            if match_match:
                if not current_rule_name:
                    self._add_error("MATCH без соответствующего RULE.", num, raw_line)
                else:
                    match_type = match_match.group(1).upper()
                    pattern_str_raw = match_match.group(2).strip()
                    capture_match = self._CAPTURE_PATTERN.search(pattern_str_raw)
                    if capture_match:
                        capture_names_str = capture_match.group(1)
                        capture_names = [name.strip() for name in capture_names_str.split(',')]
                        for name in capture_names:
                            # Matches: valid_capture_name123
                            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
                                self._add_error(f"Некорректное имя группы захвата '{name}'.", num, raw_line, "Capture Naming")
                        pattern_str_raw = pattern_str_raw[:capture_match.start()].strip()

                    if not (pattern_str_raw.startswith('"') and pattern_str_raw.endswith('"')):
                        self._add_error("Паттерн MATCH должен быть заключен в двойные кавычки.", num, raw_line)
                    else:
                        pattern_str = pattern_str_raw.strip('"')
                        if match_type == "REGEX":
                            try:
                                re.compile(pattern_str)
                            except re.error as e:
                                self._add_error(f"Некорректный REGEX паттерн: {e}", num, raw_line, "Regex Error")
                self.defined_rules[current_rule_name] = True
                continue

            if self._ACTIONS_START_PATTERN.match(line_without_comment):
                if not current_rule_name:
                    self._add_error("ACTIONS без соответствующего RULE.", num, raw_line)
                elif not self.defined_rules.get(current_rule_name):
                    self._add_error(f"ACTIONS для правила '{current_rule_name}' объявлен до MATCH.", num, raw_line)
                in_actions_block = True
                continue

            if self._END_ACTIONS_PATTERN.match(line_without_comment):
                if not current_rule_name or not in_actions_block:
                    self._add_error("END_ACTIONS без соответствующего ACTIONS.", num, raw_line)
                in_actions_block = False
                continue

            if in_actions_block:
                parts = line_without_comment.split(maxsplit=1)
                command = parts[0].upper()
                args = parts[1] if len(parts) > 1 else ""

                if command == "SET":
                    if "=" not in args:
                        self._add_error("Команда SET требует оператора '='.", num, raw_line)
                    else:
                        var_name, expr = [s.strip() for s in args.split("=", 1)]
                        # Matches: valid_var_name123
                        if not var_name or not re.match(r"^[a-zA-Z0-9_]+$", var_name):
                            self._add_error(f"Некорректное имя переменной '{var_name}'.", num, raw_line, "Variable Naming")
                        self._validate_expression(expr, num, raw_line)
                elif command == "LOG":
                    if not args:
                        self._add_error("Команда LOG требует аргумент.", num, raw_line)
                    self._validate_expression(args, num, raw_line)
                elif command == "REMOVE_MATCH":
                    if args:
                        self._add_error("REMOVE_MATCH не должен иметь аргументов.", num, raw_line)
                elif command == "REPLACE_MATCH":
                    if not args.upper().startswith("WITH "):
                        self._add_error("REPLACE_MATCH требует 'WITH' и выражение.", num, raw_line)
                    else:
                        expr = args[len("WITH "):].strip()
                        if not expr:
                            self._add_error("REPLACE_MATCH WITH требует выражение.", num, raw_line)
                        self._validate_expression(expr, num, raw_line)
                elif command:
                    self._add_error(f"Неизвестная команда в блоке ACTIONS: '{command}'.", num, raw_line, "Unknown Command")
                continue

            if self._END_RULE_PATTERN.match(line_without_comment):
                if not current_rule_name:
                    self._add_error("END_RULE без соответствующего RULE.", num, raw_line)
                else:
                    current_rule_name = None
                continue

            if self._DEBUG_DISPLAY_START_PATTERN.match(line_without_comment):
                in_debug_display_block = True
                continue

            if self._END_DEBUG_DISPLAY_PATTERN.match(line_without_comment):
                in_debug_display_block = False
                continue

            if in_debug_display_block:
                entry_match = self._DEBUG_DISPLAY_ENTRY_PATTERN.match(line_without_comment)
                if not entry_match:
                    self._add_error("Некорректный формат записи в DEBUG_DISPLAY. Ожидается 'Label: variable_name'.", num, raw_line, "Format Error")
                else:
                    label_part = entry_match.group(1)
                    var_name_part = entry_match.group(2)
                    if (label_part.startswith('"') and not label_part.endswith('"')) or \
                       (label_part.startswith("'") and not label_part.endswith("'")):
                        self._add_error("Несбалансированные кавычки в метке DEBUG_DISPLAY.", num, raw_line, "Format Error")
                    # Matches: valid_var_name123
                    if not re.match(r"^[a-zA-Z0-9_]+$", var_name_part):
                        self._add_error(f"Некорректное имя переменной '{var_name_part}' в DEBUG_DISPLAY.", num, raw_line, "Variable Naming")
                continue

            self._add_error(f"Неизвестная или некорректно расположенная строка: '{line_without_comment}'.", num, raw_line, "Unknown Line")

        if current_rule_name:
            self._add_error(f"Незакрытое правило '{current_rule_name}'. Ожидался END_RULE.", len(logical_lines), logical_lines[-1], "Unterminated Rule")

        return self.errors