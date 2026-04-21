"""Helpers for classifying SQL statements for safety guardrails."""

from __future__ import annotations

import re

_DESTRUCTIVE_FIRST_KEYWORDS = frozenset(
    {
        "insert",
        "update",
        "delete",
        "drop",
        "create",
        "alter",
        "truncate",
        "merge",
        "replace",
        "grant",
        "revoke",
    }
)
_SQL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SQL_LINE_COMMENT = re.compile(r"--[^\n]*")


def any_statement_is_destructive(sql: str) -> bool:
    """Return True when any statement in *sql* starts with a write keyword."""
    stripped = _SQL_BLOCK_COMMENT.sub("", sql)
    stripped = _SQL_LINE_COMMENT.sub("", stripped)
    for statement in stripped.split(";"):
        first = first_word(statement)
        if first and first.lower() in _DESTRUCTIVE_FIRST_KEYWORDS:
            return True
    return False


def first_word(statement: str) -> str:
    """Return the first non-empty token from *statement*, or ``''``."""
    for word in statement.split():
        cleaned = word.strip("()[]{},;")
        if cleaned:
            return cleaned
    return ""
