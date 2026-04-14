"""Agent-facing JSON envelope.

Scanning commands wrap their JSON output in a uniform envelope::

    {
      "command": "inspect",
      "data": {...},
      "next_steps": [{"cmd": "qdo ...", "why": "..."}],
      "meta": {"connection": "mydb", "table": "orders",
               "generated_at": "...", "qdo_version": "..."}
    }

This is intentionally breaking vs. the pre-1.x flat JSON shape — the envelope
gives agents a traversable graph (``next_steps``) and a place to attach
provenance (``meta``) without colliding with command-specific payload keys.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


def build_envelope(
    *,
    command: str,
    data: Any,
    next_steps: list[dict] | None = None,
    connection: str | None = None,
    table: str | None = None,
    extra_meta: dict | None = None,
) -> dict:
    """Assemble the envelope dict. Serialization is a separate step."""
    from querido import __version__

    meta: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "qdo_version": __version__,
    }
    if connection is not None:
        meta["connection"] = connection
    if table is not None:
        meta["table"] = table
    if extra_meta:
        meta.update(extra_meta)

    return {
        "command": command,
        "data": data,
        "next_steps": list(next_steps or []),
        "meta": meta,
    }


def emit_envelope(
    *,
    command: str,
    data: Any,
    next_steps: list[dict] | None = None,
    connection: str | None = None,
    table: str | None = None,
    extra_meta: dict | None = None,
) -> None:
    """Build an envelope and print it in the active structured format.

    Serialization follows ``--format``:

    - ``json``: pretty JSON (the canonical machine-readable form).
    - ``agent``: TOON where the envelope's shape allows it, YAML otherwise.
      Tuned for LLM consumption; see :mod:`querido.output.toon`.

    For any other format the envelope is rendered as JSON — the caller is
    expected to gate on :func:`is_structured_format` before calling.
    """
    envelope = build_envelope(
        command=command,
        data=data,
        next_steps=next_steps,
        connection=connection,
        table=table,
        extra_meta=extra_meta,
    )

    from querido.cli._context import get_output_format

    if get_output_format() == "agent":
        print(render_agent(envelope))
    else:
        print(json.dumps(envelope, indent=2, default=str))


def is_structured_format() -> bool:
    """Return True when the active ``--format`` wants the envelope (json or agent)."""
    from querido.cli._context import get_output_format

    return get_output_format() in ("json", "agent")


def render_agent(value: Any) -> str:
    """Render a JSON-like value as a TOON document, falling back to YAML.

    The TOON encoder covers the shapes we emit most often (tabular arrays,
    nested objects, primitive arrays); non-uniform arrays and arrays-of-arrays
    aren't in its v1 scope (see :mod:`querido.output.toon`). In those cases we
    fall back to YAML, which TOON's own authors note wins on nested data.
    """
    from querido.output.toon import ToonUnsupportedShape, encode

    normalized = _normalize_for_structured(value)
    try:
        return encode(normalized)
    except ToonUnsupportedShape:
        import yaml

        return yaml.safe_dump(normalized, sort_keys=False, default_flow_style=False).rstrip()


def _normalize_for_structured(value: Any) -> Any:
    """Coerce values the TOON/YAML path can't handle into strings.

    Mirrors what ``json.dumps(..., default=str)`` does for us on the JSON path:
    datetime, Decimal, bytes, etc. round-trip through ``str()``.
    """
    if isinstance(value, dict):
        return {k: _normalize_for_structured(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_for_structured(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def shell_quote_value(value: str) -> str:
    """Minimal shell quoting for values interpolated into ``qdo ...`` hints.

    Agents parse these as strings and may re-exec them via shell, so we need
    quotes around anything containing whitespace or shell-special characters.
    Identifiers (letters, digits, dot, underscore, dash) are returned as-is.
    """
    if value and all(c.isalnum() or c in "._-" for c in value):
        return value
    escaped = value.replace("'", "'\\''")
    return f"'{escaped}'"


def cmd(parts: list[str]) -> str:
    """Join a list of argv parts into a single ``qdo ...`` string with quoting."""
    return " ".join(shell_quote_value(p) for p in parts)
