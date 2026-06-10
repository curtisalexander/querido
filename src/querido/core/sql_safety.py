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
    """Return True when any statement in *sql* starts with a write keyword.

    Statements that open with ``with`` are classified by the first top-level
    keyword *after* the CTE definitions, so ``with x as (select 1) delete
    from t`` counts as destructive.
    """
    stripped = _SQL_BLOCK_COMMENT.sub("", sql)
    stripped = _SQL_LINE_COMMENT.sub("", stripped)
    for statement in stripped.split(";"):
        first = first_word(statement)
        if not first:
            continue
        keyword = first.lower()
        if keyword == "with":
            keyword = _first_keyword_after_ctes(statement)
            if not keyword:
                # Could not parse the CTE list — fail closed.
                return True
        if keyword in _DESTRUCTIVE_FIRST_KEYWORDS:
            return True
    return False


def first_word(statement: str) -> str:
    """Return the first non-empty token from *statement*, or ``''``."""
    for word in statement.split():
        cleaned = word.strip("()[]{},;")
        if cleaned:
            return cleaned
    return ""


def _top_level_tokens(statement: str) -> list[str]:
    """Tokenize *statement* at paren depth zero.

    Returns lowercase word tokens plus ``","`` for top-level commas and
    ``"()"`` for each top-level parenthesized group (contents skipped).
    Single-quoted strings and double-quoted identifiers never affect the
    paren depth.
    """
    tokens: list[str] = []
    word: list[str] = []
    depth = 0
    i = 0
    n = len(statement)

    def flush() -> None:
        if word:
            tokens.append("".join(word).lower())
            word.clear()

    while i < n:
        ch = statement[i]
        if ch == "'":
            # Skip a single-quoted string, honoring '' escapes.
            i += 1
            while i < n:
                if statement[i] == "'":
                    if i + 1 < n and statement[i + 1] == "'":
                        i += 2
                        continue
                    break
                i += 1
        elif ch == '"':
            # A double-quoted identifier is part of the current word.
            end = statement.find('"', i + 1)
            if end == -1:
                end = n
            if depth == 0:
                word.extend(statement[i : end + 1])
            i = end
        elif ch == "(":
            if depth == 0:
                flush()
                tokens.append("()")
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif depth == 0:
            if ch == ",":
                flush()
                tokens.append(",")
            elif ch.isspace():
                flush()
            else:
                word.append(ch)
        i += 1
    flush()
    return tokens


def _first_keyword_after_ctes(statement: str) -> str:
    """Return the first top-level keyword after a ``with`` clause's CTEs.

    Returns ``''`` when the CTE list cannot be parsed; callers should treat
    that as destructive (fail closed).
    """
    tokens = _top_level_tokens(statement)
    if not tokens or tokens[0] != "with":
        return ""
    i = 1
    if i < len(tokens) and tokens[i] == "recursive":
        i += 1
    while i < len(tokens):
        if tokens[i] in (",", "()", "as"):
            return ""
        i += 1  # CTE name
        if i < len(tokens) and tokens[i] == "()":
            i += 1  # optional column list
        if i >= len(tokens) or tokens[i] != "as":
            return ""
        i += 1
        # Optional [not] materialized hint (DuckDB / Postgres).
        if i < len(tokens) and tokens[i] == "not":
            i += 1
        if i < len(tokens) and tokens[i] == "materialized":
            i += 1
        if i >= len(tokens) or tokens[i] != "()":
            return ""
        i += 1  # CTE body
        if i < len(tokens) and tokens[i] == ",":
            i += 1
            continue
        return tokens[i] if i < len(tokens) else ""
    return ""
