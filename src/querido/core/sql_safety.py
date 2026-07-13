"""Helpers for enforcing read-only arbitrary SQL execution."""

from __future__ import annotations

import re

_READ_ONLY_FIRST_KEYWORDS = frozenset({"select", "values", "show", "describe", "desc"})
_DOLLAR_QUOTE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def any_statement_is_destructive(sql: str) -> bool:
    """Return ``True`` unless every statement is recognizably read-only.

    This is intentionally an allowlist. Database statement vocabularies grow,
    and operations such as DuckDB ``copy`` or Snowflake ``put`` can mutate
    external state even when the database connection itself is read-only.
    Malformed or unterminated SQL also fails closed.
    """
    statements = _split_statements(sql)
    if statements is None or not statements:
        return True
    return any(not _statement_is_read_only(statement) for statement in statements)


def require_read_only_sql(sql: str, *, context: str = "SQL") -> None:
    """Raise when *sql* is not a sequence of recognized read-only statements."""
    if any_statement_is_destructive(sql):
        raise ValueError(
            f"{context} must be read-only. Use qdo query --allow-write for intentional writes."
        )


def first_word(statement: str) -> str:
    """Return the first non-empty token from *statement*, or ``''``."""
    tokens = _top_level_tokens(statement)
    return tokens[0] if tokens else ""


def _statement_is_read_only(statement: str) -> bool:
    keyword = first_word(statement).lower()
    if keyword in _READ_ONLY_FIRST_KEYWORDS:
        return True
    if keyword == "with":
        return _first_keyword_after_ctes(statement) in _READ_ONLY_FIRST_KEYWORDS
    if keyword == "explain":
        return _explain_target_is_read_only(statement)
    return False


def _explain_target_is_read_only(statement: str) -> bool:
    """Classify the statement nested under EXPLAIN, including ANALYZE."""
    tokens = _top_level_tokens(statement)
    if not tokens or tokens[0] != "explain":
        return False
    i = 1
    if tokens[i : i + 2] in (["query", "plan"], ["using", "text"]):
        i += 2
    if i < len(tokens) and tokens[i] == "analyze":
        i += 1
    if i >= len(tokens):
        return False
    keyword = tokens[i]
    if keyword in _READ_ONLY_FIRST_KEYWORDS:
        return True
    if keyword == "with":
        nested = " ".join(tokens[i:])
        return _first_keyword_after_ctes(nested) in _READ_ONLY_FIRST_KEYWORDS
    return False


def _split_statements(sql: str) -> list[str] | None:
    """Split SQL on real statement separators while removing real comments.

    Quote/comment markers inside string literals or quoted identifiers remain
    ordinary text. ``None`` signals an unterminated quote or block comment.
    """
    statements: list[str] = []
    current: list[str] = []
    i = 0
    n = len(sql)

    def consume_quoted(quote: str, *, doubled_escape: bool = True) -> bool:
        nonlocal i
        current.append(quote)
        i += 1
        while i < n:
            ch = sql[i]
            current.append(ch)
            i += 1
            if ch != quote:
                continue
            if doubled_escape and i < n and sql[i] == quote:
                current.append(sql[i])
                i += 1
                continue
            return True
        return False

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if ch in ("'", '"', "`"):
            if not consume_quoted(ch):
                return None
            continue
        if ch == "[":
            if not consume_quoted("]", doubled_escape=True):
                return None
            continue
        if ch == "$":
            match = _DOLLAR_QUOTE.match(sql, i)
            if match:
                delimiter = match.group(0)
                end = sql.find(delimiter, match.end())
                if end < 0:
                    return None
                current.append(sql[i : end + len(delimiter)])
                i = end + len(delimiter)
                continue
        if ch == "-" and nxt == "-":
            i += 2
            while i < n and sql[i] not in "\r\n":
                i += 1
            current.append(" ")
            continue
        if ch == "/" and nxt == "*":
            end = sql.find("*/", i + 2)
            if end < 0:
                return None
            current.append(" ")
            i = end + 2
            continue
        if ch == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current.clear()
            i += 1
            continue
        current.append(ch)
        i += 1

    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements


def _top_level_tokens(statement: str) -> list[str]:
    """Return lowercase word tokens and top-level CTE punctuation."""
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
        if ch in ("'", '"', "`"):
            quote = ch
            if depth == 0 and quote != "'":
                word.append(ch)
            i += 1
            while i < n:
                if depth == 0 and quote != "'":
                    word.append(statement[i])
                if statement[i] == quote:
                    if i + 1 < n and statement[i + 1] == quote:
                        if depth == 0 and quote != "'":
                            word.append(statement[i + 1])
                        i += 2
                        continue
                    break
                i += 1
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
    """Return the first top-level keyword after a ``with`` clause's CTEs."""
    tokens = _top_level_tokens(statement)
    if not tokens or tokens[0] != "with":
        return ""
    i = 1
    if i < len(tokens) and tokens[i] == "recursive":
        i += 1
    while i < len(tokens):
        if tokens[i] in (",", "()", "as"):
            return ""
        i += 1
        if i < len(tokens) and tokens[i] == "()":
            i += 1
        if i >= len(tokens) or tokens[i] != "as":
            return ""
        i += 1
        if i < len(tokens) and tokens[i] == "not":
            i += 1
        if i < len(tokens) and tokens[i] == "materialized":
            i += 1
        if i >= len(tokens) or tokens[i] != "()":
            return ""
        i += 1
        if i < len(tokens) and tokens[i] == ",":
            i += 1
            continue
        return tokens[i] if i < len(tokens) else ""
    return ""
