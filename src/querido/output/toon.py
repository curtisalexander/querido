"""TOON (Token-Oriented Object Notation) encoder.

Encode-only. Pinned to TOON specification v3.0 (2025-11-24).
Spec: https://github.com/toon-format/spec/blob/main/SPEC.md

Supported shapes:
    - Primitives (string, number, bool, null)
    - Objects (flat and nested)
    - Primitive arrays (inline)
    - Tabular arrays of uniform primitive-only objects

Out of scope for this version (raises ``ToonUnsupportedShape``):
    - Arrays of arrays (§9.2)
    - Non-uniform / mixed arrays (§9.4)
    - Objects as list items (§10)
    - Custom delimiters (only comma is emitted)
    - Key folding (§13.4)

The AgentFormatter routes nested/non-uniform shapes to YAML instead of
stretching this encoder to cover territory it would rarely reach.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal
from typing import Any

TOON_SPEC_VERSION = "3.0"

# §7.3 — unquoted key pattern.
_SAFE_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

# §7.2 — numeric-like strings that MUST be quoted so they don't decode as numbers.
_NUMERIC_LIKE_RE = re.compile(r"^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$", re.IGNORECASE)
_LEADING_ZERO_RE = re.compile(r"^0\d+$")

# Characters whose presence forces a string to be quoted (§7.2).
_FORCE_QUOTE_CHARS = frozenset(':"\\[]{}\n\r\t')


class ToonUnsupportedShape(ValueError):
    """Raised when a value can't be expressed in the v1 encoder subset."""


def encode(value: Any, *, indent: int = 2) -> str:
    """Encode a JSON-like value as a TOON document.

    ``value`` follows the JSON data model: dict, list, str, int, float,
    bool, None. Non-finite floats are normalized to null per §3.

    Returns a string with no trailing newline. The caller decides
    whether to append one.
    """
    lines: list[str] = []
    _emit_root(value, lines, indent)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Root / recursion
# --------------------------------------------------------------------------- #


def _emit_root(value: Any, lines: list[str], indent: int) -> None:
    if isinstance(value, dict):
        _emit_object_body(value, lines, depth=0, indent=indent)
    elif isinstance(value, list):
        _emit_root_array(value, lines, indent)
    else:
        # §5: single primitive at root is a valid document.
        lines.append(_encode_primitive(value, delimiter=","))


def _emit_root_array(arr: list[Any], lines: list[str], indent: int) -> None:
    if not arr:
        lines.append("[0]:")
        return
    if _is_tabular(arr):
        fields = list(arr[0].keys())
        header = f"[{len(arr)}]{{{_encode_fields(fields)}}}:"
        lines.append(header)
        pad = " " * indent
        lines.extend(pad + _encode_tabular_row(obj, fields) for obj in arr)
        return
    if _is_primitive_array(arr):
        lines.append(f"[{len(arr)}]: {_encode_inline_values(arr)}")
        return
    raise ToonUnsupportedShape("root array is neither uniform-tabular nor all-primitive")


def _emit_object_body(obj: dict[str, Any], lines: list[str], *, depth: int, indent: int) -> None:
    pad = " " * (depth * indent)
    for key in obj:
        val = obj[key]
        ekey = _encode_key(key)
        if isinstance(val, dict):
            if not val:
                lines.append(f"{pad}{ekey}:")
            else:
                lines.append(f"{pad}{ekey}:")
                _emit_object_body(val, lines, depth=depth + 1, indent=indent)
        elif isinstance(val, list):
            _emit_array_field(ekey, val, lines, depth=depth, indent=indent)
        else:
            lines.append(f"{pad}{ekey}: {_encode_primitive(val, delimiter=',')}")


def _emit_array_field(
    ekey: str, arr: list[Any], lines: list[str], *, depth: int, indent: int
) -> None:
    pad = " " * (depth * indent)
    if not arr:
        lines.append(f"{pad}{ekey}[0]:")
        return
    if _is_tabular(arr):
        fields = list(arr[0].keys())
        lines.append(f"{pad}{ekey}[{len(arr)}]{{{_encode_fields(fields)}}}:")
        row_pad = " " * ((depth + 1) * indent)
        lines.extend(row_pad + _encode_tabular_row(obj, fields) for obj in arr)
        return
    if _is_primitive_array(arr):
        lines.append(f"{pad}{ekey}[{len(arr)}]: {_encode_inline_values(arr)}")
        return
    raise ToonUnsupportedShape(
        f"field {ekey!r}: array is neither uniform-tabular nor all-primitive"
    )


# --------------------------------------------------------------------------- #
# Shape detection
# --------------------------------------------------------------------------- #


def _is_primitive_array(arr: list[Any]) -> bool:
    return all(not isinstance(v, (dict, list)) for v in arr)


def _is_tabular(arr: list[Any]) -> bool:
    """§9.3: every element is an object, same key set, all values primitive."""
    if not arr or not all(isinstance(v, dict) for v in arr):
        return False
    first_keys = set(arr[0].keys())
    if not all(set(obj.keys()) == first_keys for obj in arr):
        return False
    return all(not isinstance(v, (dict, list)) for obj in arr for v in obj.values())


# --------------------------------------------------------------------------- #
# Primitive / string / number encoding
# --------------------------------------------------------------------------- #


def _encode_primitive(value: Any, *, delimiter: str) -> str:
    if value is None:
        return "null"
    # bool is a subclass of int — check first.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _encode_number(value)
    if isinstance(value, str):
        return _encode_string(value, delimiter=delimiter)
    raise ToonUnsupportedShape(f"unsupported scalar type: {type(value).__name__}")


def _encode_number(value: int | float) -> str:
    """Canonical decimal form per §2."""
    if isinstance(value, float):
        if not math.isfinite(value):
            return "null"
        if value == 0.0:
            return "0"
        # repr gives shortest round-trip representation. Expand any
        # exponent form into plain decimal via Decimal(repr(...)).
        r = repr(value)
        if "e" in r or "E" in r:
            d = Decimal(r)
            s = format(d, "f")
        else:
            s = r
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s or "0"
    # int (already excluded bool above)
    return str(value)


def _encode_string(s: str, *, delimiter: str) -> str:
    if _needs_quoting(s, delimiter):
        return _quote(s)
    return s


def _needs_quoting(s: str, delimiter: str) -> bool:
    if s == "":
        return True
    if s != s.strip():
        return True  # leading/trailing whitespace
    if s in ("true", "false", "null"):
        return True
    if _NUMERIC_LIKE_RE.match(s) or _LEADING_ZERO_RE.match(s):
        return True
    if s == "-" or s.startswith("-"):
        return True
    if any(ch in _FORCE_QUOTE_CHARS for ch in s):
        return True
    return delimiter in s


def _quote(s: str) -> str:
    out = ['"']
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


# --------------------------------------------------------------------------- #
# Keys, fields, rows
# --------------------------------------------------------------------------- #


def _encode_key(key: str) -> str:
    if key != "" and _SAFE_KEY_RE.match(key):
        return key
    return _quote(key)


def _encode_fields(fields: list[str]) -> str:
    return ",".join(_encode_key(f) for f in fields)


def _encode_tabular_row(obj: dict[str, Any], fields: list[str]) -> str:
    return ",".join(_encode_primitive(obj[f], delimiter=",") for f in fields)


def _encode_inline_values(values: list[Any]) -> str:
    return ",".join(_encode_primitive(v, delimiter=",") for v in values)
