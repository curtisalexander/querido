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
    """Assemble the envelope dict. Serialization is a separate step.

    **Convention for ``command``** (R.10): the value must match the argv
    shape — agents re-exec the invocation by reading ``command`` back.
    Examples:

    - Leaf commands: ``"inspect"`` for ``qdo inspect``
    - Multi-word (nested) commands: ``"bundle export"`` for ``qdo bundle
      export``, ``"workflow list"`` for ``qdo workflow list``
    - Hyphenated commands: ``"view-def"`` for ``qdo view-def``

    Never use underscores or slashes to join parts. A single space between
    the group and the action mirrors argv exactly.
    """
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
    """Build an envelope and print it as pretty JSON.

    The caller is expected to gate on :func:`is_structured_format` before
    calling.
    """
    envelope = build_envelope(
        command=command,
        data=data,
        next_steps=next_steps,
        connection=connection,
        table=table,
        extra_meta=extra_meta,
    )

    print(json.dumps(envelope, indent=2, default=str))


def is_structured_format() -> bool:
    """Return True when the active ``--format`` wants the envelope (json)."""
    from querido._runtime import get_output_format

    return get_output_format() == "json"


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
