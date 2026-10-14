"""Small strict S-expression reader; quoted names never become numbers."""
from __future__ import annotations

import json
import re

from ceda.errors import CedaError

TOKEN = re.compile(r'\s+|;[^\n]*|\(|\)|"(?:\\.|[^"\\])*"|[^\s();]+')


def parse(text: str) -> list:
    stack: list[list] = []
    roots = []
    for match in TOKEN.finditer(text):
        token = match.group()
        if token.isspace() or token.startswith(";"):
            continue
        if token == "(":
            value: list = []
            if stack:
                stack[-1].append(value)
            else:
                roots.append(value)
            stack.append(value)
        elif token == ")":
            if not stack:
                raise CedaError("PCB 文件括号不匹配。")
            stack.pop()
        else:
            if not stack:
                raise CedaError("PCB 文件出现根表达式外的内容。")
            if token.startswith('"'):
                try:
                    value = json.loads(token)
                except ValueError as exc:
                    raise CedaError("PCB 文件包含无法解析的字符串转义。") from exc
            else:
                value = token
            stack[-1].append(value)
    if stack or len(roots) != 1:
        raise CedaError("PCB 文件应包含一个完整的根表达式。")
    return roots[0]


def children(node: list, key: str) -> list[list]:
    return [item for item in node[1:] if isinstance(item, list) and item and item[0] == key]


def child(node: list, key: str, default=None):
    values = children(node, key)
    return values[0] if values else default


def number(node: list, key: str, default=None):
    value = child(node, key)
    return float(value[1]) if value is not None and len(value) > 1 else default
