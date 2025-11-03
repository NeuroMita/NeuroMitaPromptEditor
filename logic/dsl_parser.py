# logic/dsl_parser.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
import re

from logic.dsl_ast import Script, AstNode, Set, Log, AddSystemInfo, Return, If, IfBranch

@dataclass
class ParseError:
    message: str
    line_num: int
    line_content: str
    def __str__(self):
        return f"[Parse Error] Line {self.line_num}: '{self.line_content.strip()}' - {self.message}"

TRIPLE = '"""'

def _split_into_logical_lines(script_text: str) -> list[str]:
    logical_lines: list[str] = []
    buff: list[str] = []
    inside_triple = False
    i = 0
    text = script_text
    n = len(text)

    while i < n:
        if text.startswith(TRIPLE, i):
            buff.append(TRIPLE)
            inside_triple = not inside_triple
            i += 3
            continue
        ch = text[i]
        if ch == '\n' and not inside_triple:
            logical_lines.append(''.join(buff))
            buff.clear()
            i += 1
            continue
        buff.append(ch); i += 1

    if buff:
        logical_lines.append(''.join(buff))
    if inside_triple:
        raise ValueError('Unterminated multiline block (""" not closed)')
    return logical_lines

def parse_script(text: str) -> Tuple[Script, List[ParseError]]:
    errors: List[ParseError] = []
    script = Script()
    try:
        lines = _split_into_logical_lines(text)
    except ValueError as e:
        return script, [ParseError(str(e), 0, text)]

    current_body_stack: List[List[AstNode]] = [script.body]
    if_stack: List[If] = []

    def add_node(node: AstNode):
        current_body_stack[-1].append(node)

    for num, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("//"):
            continue
        command_part = stripped.split("//", 1)[0].strip()
        if not command_part:
            continue

        parts = command_part.split(maxsplit=1)
        command = parts[0].upper()
        args = parts[1] if len(parts) > 1 else ""

        if command == "IF":
            cond_raw = args.strip()
            cond = cond_raw[:-len(" THEN")].strip() if cond_raw.upper().endswith(" THEN") else cond_raw
            if_node = If(branches=[IfBranch(cond=cond)])
            add_node(if_node)
            if_stack.append(if_node)
            current_body_stack.append(if_node.branches[0].body)
            continue

        if command == "ELSEIF":
            if not if_stack:
                errors.append(ParseError("ELSEIF without IF", num, raw)); continue
            cond_raw = args.strip()
            cond = cond_raw[:-len(" THEN")].strip() if cond_raw.upper().endswith(" THEN") else cond_raw
            node = if_stack[-1]
            if current_body_stack: current_body_stack.pop()
            node.branches.append(IfBranch(cond=cond))
            current_body_stack.append(node.branches[-1].body)
            continue

        if command == "ELSE":
            if not if_stack:
                errors.append(ParseError("ELSE without IF", num, raw)); continue
            if args.strip():
                errors.append(ParseError("ELSE should not have arguments", num, raw))
            node = if_stack[-1]
            if current_body_stack: current_body_stack.pop()
            node.ensure_else()
            current_body_stack.append(node.else_body)  # type: ignore
            continue

        if command == "ENDIF":
            if not if_stack:
                errors.append(ParseError("ENDIF without IF", num, raw)); continue
            if args.strip():
                errors.append(ParseError("ENDIF should not have arguments", num, raw))
            if current_body_stack: current_body_stack.pop()
            if_stack.pop()
            continue

        if not current_body_stack:
            errors.append(ParseError("Internal parser state error: empty body stack", num, raw))
            current_body_stack = [script.body]

        if command == "SET":
            local = False
            rest = args
            parts_after_set = rest.split(maxsplit=1)
            if len(parts_after_set) > 1 and parts_after_set[0].upper() == "LOCAL":
                local = True; rest = parts_after_set[1]
            if "=" not in rest:
                errors.append(ParseError("SET requires '='", num, raw)); continue
            var, expr = [s.strip() for s in rest.split("=", 1)]
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", var):
                errors.append(ParseError(f"Invalid variable name '{var}'", num, raw))
            add_node(Set(var=var, expr=expr, local=local))
            continue

        if command == "LOG":
            add_node(Log(expr=args.strip())); continue

        if command == "ADD_SYSTEM_INFO":
            if not args.strip():
                errors.append(ParseError("ADD_SYSTEM_INFO requires argument", num, raw))
            add_node(AddSystemInfo(expr=args.strip())); continue

        if command == "RETURN":
            if not args.strip():
                errors.append(ParseError("RETURN requires argument", num, raw))
            add_node(Return(expr=args.strip())); continue

        errors.append(ParseError(f"Unknown DSL command '{command}'", num, raw))

    if if_stack:
        errors.append(ParseError("Unterminated IF block(s)", len(lines), lines[-1] if lines else ""))

    return script, errors