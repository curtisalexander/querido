"""Shell-quoting helpers for the ``qdo ...`` command strings in agent hints.

These build the ``cmd`` strings that appear in ``next_steps`` and report
output. They live at the package root (not under ``output/``) because both the
``core`` layer (``next_steps``) and the ``output`` layer (``envelope``) need
them, and ``core`` must not depend on ``output``. ``output.envelope`` re-exports
``cmd``/``shell_quote_value`` so existing importers keep working.
"""

from __future__ import annotations


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
