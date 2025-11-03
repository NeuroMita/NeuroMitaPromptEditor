# logic/dsl_ast.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import uuid

def gen_id() -> str:
    return uuid.uuid4().hex

@dataclass
class AstNode:
    id: str = field(default_factory=gen_id)

@dataclass
class Script(AstNode):
    body: List[AstNode] = field(default_factory=list)

@dataclass
class Set(AstNode):
    var: str = ""
    expr: str = ""
    local: bool = False

@dataclass
class Log(AstNode):
    expr: str = ""

@dataclass
class AddSystemInfo(AstNode):
    expr: str = ""

@dataclass
class Return(AstNode):
    expr: str = ""

@dataclass
class IfBranch:
    cond: str
    body: List[AstNode] = field(default_factory=list)

@dataclass
class If(AstNode):
    branches: List[IfBranch] = field(default_factory=list)  # IF(cond), ELSEIF(cond)...
    else_body: Optional[List[AstNode]] = None

    def ensure_else(self):
        if self.else_body is None:
            self.else_body = []