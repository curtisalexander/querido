"""Tiny restricted expression evaluator for workflow ``when`` / ``outputs``.

Supports:

- ``${dotted.path}`` references resolved against the runner's context
  (bound inputs plus prior-step captures).
- Comparisons (``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``).
- Boolean combinations (``and``, ``or``, ``not``).
- Numeric, string, and boolean literals.

No function calls, attribute access, subscripts outside dotted refs, or
arbitrary names — the deliberate opposite of ``eval()``.  Workflows are
declarative files, not code.
"""

from __future__ import annotations

import ast
import re
from typing import Any

REF_RE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")


class UnresolvedReference(KeyError):
    """Raised when a ``${path}`` can't be resolved in the context."""


class ExpressionError(ValueError):
    """Raised for malformed ``when`` / output expressions."""


def iter_refs(template: str) -> list[str]:
    """Return every ``${path}`` found in *template*, preserving order."""
    return [m.group(1) for m in REF_RE.finditer(template)]


def resolve_path(path: str, context: dict[str, Any]) -> Any:
    """Walk ``a.b.c`` through nested dicts/lists in *context*."""
    parts = path.split(".")
    val: Any = context
    for i, p in enumerate(parts):
        if isinstance(val, dict):
            if p not in val:
                where = ".".join(parts[: i + 1])
                raise UnresolvedReference(f"unresolved reference: {where}")
            val = val[p]
        elif isinstance(val, list):
            try:
                idx = int(p)
                val = val[idx]
            except (ValueError, IndexError) as exc:
                where = ".".join(parts[: i + 1])
                raise UnresolvedReference(f"unresolved reference: {where}") from exc
        else:
            where = ".".join(parts[: i + 1])
            raise UnresolvedReference(f"unresolved reference: {where}")
    return val


def interpolate(template: str, context: dict[str, Any]) -> str:
    """Return *template* with every ``${path}`` replaced by ``str(value)``."""

    def repl(m: re.Match[str]) -> str:
        return str(resolve_path(m.group(1), context))

    return REF_RE.sub(repl, template)


def resolve_output(expr: str, context: dict[str, Any]) -> Any:
    """Resolve an output expression.

    If the whole expression is exactly a single ``${path}``, the raw resolved
    value is returned (preserving type).  Otherwise the expression is treated
    as a string template and every reference is stringified in-place.
    """
    stripped = expr.strip()
    m = REF_RE.fullmatch(stripped)
    if m is not None:
        return resolve_path(m.group(1), context)
    return interpolate(expr, context)


def evaluate_when(expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a ``when`` expression and return its truthy/falsy result as a bool."""
    refs: dict[str, Any] = {}

    def repl(m: re.Match[str]) -> str:
        placeholder = f"__qdo_ref_{len(refs)}"
        refs[placeholder] = resolve_path(m.group(1), context)
        return placeholder

    normalized = REF_RE.sub(repl, expr)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid expression: {expr!r} ({exc.msg})") from exc
    return bool(_eval_node(tree.body, refs))


_BOOL_NAMES = {
    "True": True,
    "true": True,
    "False": False,
    "false": False,
    # Null literal — both Python (``None``) and YAML/JSON (``null``/``none``)
    # spellings resolve to Python None so ``${x} != null`` works as authors
    # expect.
    "None": None,
    "null": None,
    "none": None,
}


def _eval_node(node: ast.AST, refs: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in refs:
            return refs[node.id]
        if node.id in _BOOL_NAMES:
            return _BOOL_NAMES[node.id]
        raise ExpressionError(f"unknown name in expression: {node.id}")
    if isinstance(node, ast.BoolOp):
        # Short-circuit evaluation: walk children one at a time so a failing
        # ordering comparison on the right side of ``${x} != null and ${x} > 0``
        # never fires when the equality check already decided the result.
        if isinstance(node.op, ast.And):
            last: Any = True
            for v_node in node.values:
                v = _eval_node(v_node, refs)
                if not v:
                    return v
                last = v
            return last
        if isinstance(node.op, ast.Or):
            last = False
            for v_node in node.values:
                v = _eval_node(v_node, refs)
                if v:
                    return v
                last = v
            return last
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, refs)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand, refs)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, refs)
        for op, comp in zip(node.ops, node.comparators, strict=False):
            right = _eval_node(comp, refs)
            if not _apply_compare(op, left, right):
                return False
            left = right
        return True
    raise ExpressionError(f"unsupported expression construct: {type(node).__name__}")


_ORDERING_OPS: dict[type[ast.cmpop], str] = {
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}


def _apply_compare(op: ast.cmpop, left: Any, right: Any) -> bool:
    if isinstance(op, ast.Eq):
        return bool(left == right)
    if isinstance(op, ast.NotEq):
        return bool(left != right)
    # Ordering comparisons wrap Python's raw ``<``/``>`` so mismatched types
    # or nulls surface as a workflow-level ExpressionError (attributable to
    # the failing ``when:``) instead of a bare TypeError with no context.
    symbol = _ORDERING_OPS.get(type(op))
    if symbol is not None:
        try:
            if symbol == "<":
                return bool(left < right)
            if symbol == "<=":
                return bool(left <= right)
            if symbol == ">":
                return bool(left > right)
            return bool(left >= right)
        except TypeError as exc:
            raise ExpressionError(
                f"cannot compare {left!r} ({type(left).__name__}) "
                f"{symbol} {right!r} ({type(right).__name__}) — "
                "null or mismatched types. Guard with an equality check first, "
                f"e.g. `${{ref}} != null and ${{ref}} {symbol} {right!r}`."
            ) from exc
    raise ExpressionError(f"unsupported comparison: {type(op).__name__}")


__all__ = [
    "REF_RE",
    "ExpressionError",
    "UnresolvedReference",
    "evaluate_when",
    "interpolate",
    "iter_refs",
    "resolve_output",
    "resolve_path",
]
