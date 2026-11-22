"""The calculation engine. Agents name a formula and its inputs; this module computes it. Never a language model."""
from __future__ import annotations

import ast
import math
import operator

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod}
_UN = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {
    "sum": lambda *a: math.fsum(a), "avg": lambda *a: math.fsum(a) / len(a), "min": min, "max": max,
    "round": lambda x, n=0: round(x, int(n)), "abs": abs,
}


class CalcError(ValueError):
    pass


def evaluate(formula: str, variables: dict[str, float]) -> float:
    if len(formula) > 300:
        raise CalcError("formula too long")
    try:
        tree = ast.parse(formula.strip(), mode="eval")
    except SyntaxError as e:
        raise CalcError(f"syntax error in formula: {e.msg}") from e

    def ev(n: ast.AST) -> float:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.Name):
            if n.id not in variables:
                raise CalcError(f"unknown variable '{n.id}'")
            return float(variables[n.id])
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and (abs(b) > 8 or abs(a) > 1e6):
                raise CalcError("exponent too large")
            if isinstance(n.op, (ast.Div, ast.Mod)) and b == 0:
                raise CalcError("division by zero")
            return _BIN[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UN:
            return _UN[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            if not n.args:
                raise CalcError(f"{n.func.id}() needs arguments")
            return float(_FUNCS[n.func.id](*[ev(a) for a in n.args]))
        raise CalcError("only numbers, variables, + - * / ** %, and sum/avg/min/max/round/abs are allowed")

    v = ev(tree)
    if math.isnan(v) or math.isinf(v):
        raise CalcError("result is not a finite number")
    return v
