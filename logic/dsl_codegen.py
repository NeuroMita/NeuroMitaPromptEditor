# logic/dsl_codegen.py
from __future__ import annotations
from typing import List
from logic.dsl_ast import Script, Set, Log, AddSystemInfo, Return, If, AstNode

IND = "    "

def _gen_block(body: List[AstNode], depth: int, out: List[str]):
    for node in body:
        if isinstance(node, Set):
            prefix = f"{IND*depth}SET "
            if node.local: prefix += "LOCAL "
            out.append(f"{prefix}{node.var} = {node.expr}")
        elif isinstance(node, Log):
            out.append(f"{IND*depth}LOG {node.expr}")
        elif isinstance(node, AddSystemInfo):
            out.append(f"{IND*depth}ADD_SYSTEM_INFO {node.expr}")
        elif isinstance(node, Return):
            out.append(f"{IND*depth}RETURN {node.expr}")
        elif isinstance(node, If):
            _gen_if(node, depth, out)
        else:
            out.append(f"{IND*depth}// [UNKNOWN NODE TYPE] {type(node).__name__}")

def _gen_if(node: If, depth: int, out: List[str]):
    if not node.branches:
        out.append(f"{IND*depth}// IF without branches")
        return
    first = node.branches[0]
    out.append(f"{IND*depth}IF {first.cond} THEN")
    _gen_block(first.body, depth + 1, out)
    for br in node.branches[1:]:
        out.append(f"{IND*depth}ELSEIF {br.cond} THEN")
        _gen_block(br.body, depth + 1, out)
    if node.else_body is not None:
        out.append(f"{IND*depth}ELSE")
        _gen_block(node.else_body, depth + 1, out)
    out.append(f"{IND*depth}ENDIF")

def generate_script(script: Script) -> str:
    out: List[str] = []
    _gen_block(script.body, 0, out)
    return "\n".join(out) + ("\n" if out else "")