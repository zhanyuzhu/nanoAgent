"""calculator 工具：基于 AST 白名单的安全表达式求值。"""

import ast
import math
import operator

from pydantic import BaseModel, Field

from app.tools.registry import tool

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "pow": math.pow,
    "min": min,
    "max": max,
}
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval(node: ast.AST) -> float:
    match node:
        case ast.Expression(body=body):
            return _eval(body)
        case ast.Constant(value=v) if isinstance(v, (int, float)):
            return v
        case ast.Name(id=name) if name in _CONSTS:
            return _CONSTS[name]
        case ast.BinOp(left=l, op=op, right=r) if type(op) in _BIN_OPS:
            return _BIN_OPS[type(op)](_eval(l), _eval(r))
        case ast.UnaryOp(op=op, operand=v) if type(op) in _UNARY_OPS:
            return _UNARY_OPS[type(op)](_eval(v))
        case ast.Call(func=ast.Name(id=name), args=args, keywords=[]) if name in _FUNCS:
            return _FUNCS[name](*(_eval(a) for a in args))
        case _:
            raise ValueError(f"unsupported expression element: {ast.dump(node)}")


class CalculatorParams(BaseModel):
    expression: str = Field(
        description=(
            "A pure math expression, e.g. '(3 + 5) * 2 / sqrt(16)'. "
            "Supports + - * / // % **, parentheses, constants pi/e, and functions: "
            "abs, round, sqrt, sin, cos, tan, log, log10, exp, floor, ceil, pow, min, max."
        )
    )


@tool(
    name="calculator",
    description="Evaluate a math expression and return the numeric result. "
    "Use this for any arithmetic instead of computing yourself.",
    params=CalculatorParams,
)
async def calculator(params: CalculatorParams) -> str:
    tree = ast.parse(params.expression, mode="eval")
    result = _eval(tree)
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return str(result)
