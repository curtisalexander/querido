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
    """Build an envelope and print it as pretty JSON to stdout."""
    envelope = build_envelope(
        command=command,
        data=data,
        next_steps=next_steps,
        connection=connection,
        table=table,
        extra_meta=extra_meta,
    )
    print(json.dumps(envelope, indent=2, default=str))


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
