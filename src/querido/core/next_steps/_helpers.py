"""Shared analysis vocabulary for the ``next_steps`` rule modules.

``_step`` is the core primitive (every rule builds suggestions with it); the
rest are small predicates the command modules use to pick which follow-up to
propose. Nothing here is part of the public API — command modules import these
by explicit name.
"""

from __future__ import annotations

from querido._shell import cmd


def _step(argv: list[str], why: str) -> dict:
    return {"cmd": cmd(argv), "why": why}


def _maybe_suggest_metadata(connection: str, table: str) -> dict | None:
    """If *table* has a low stored metadata score, propose ``metadata suggest``.

    Returns ``None`` when no metadata file exists (other rules handle init)
    or when the score is already healthy.
    """
    from querido.core.metadata_score import LOW_SCORE_THRESHOLD, peek_score

    score = peek_score(connection, table)
    if score is None or score >= LOW_SCORE_THRESHOLD:
        return None
    return _step(
        ["qdo", "metadata", "suggest", "-c", connection, "-t", table],
        f"Stored metadata score is {score:.2f} — propose additions from fresh scans.",
    )


def _preview_column_sql(table: str, column: str) -> str:
    quoted_table = table.replace('"', '""')
    quoted_column = column.replace('"', '""')
    return (
        f'select "{quoted_column}" '
        f'from "{quoted_table}" '
        f'where "{quoted_column}" is not null limit 20'
    )


def _pick_largest_table(tables: list[dict]) -> str | None:
    """Return the name of the table with the highest row_count (or None)."""
    best_name: str | None = None
    best_count = -1
    for t in tables:
        rc = t.get("row_count")
        if rc is None:
            continue
        if rc > best_count:
            best_count = rc
            best_name = t.get("name")
    return best_name


def _first_high_null_column(
    columns: list[dict], *, threshold: float, null_key: str = "null_pct"
) -> str | None:
    for col in columns:
        pct = col.get(null_key)
        if pct is not None and pct >= threshold:
            # Profile and context use different name keys.
            return col.get("name") or col.get("column_name")
    return None


def _first_low_cardinality_by_profile(columns: list[dict], *, max_distinct: int) -> str | None:
    """``profile`` uses ``column_name``/``column_type`` and ``min_length`` to mark
    strings."""
    for col in columns:
        distinct = col.get("distinct_count")
        is_stringy = col.get("min_length") is not None
        if is_stringy and distinct is not None and 1 < distinct <= max_distinct:
            return col.get("column_name")
    return None


def _first_numeric_by_profile(columns: list[dict]) -> str | None:
    for col in columns:
        if col.get("min_val") is not None or col.get("mean_val") is not None:
            return col.get("column_name")
    return None


def _first_low_cardinality_string(columns: list[dict], *, max_distinct: int) -> str | None:
    for col in columns:
        distinct = col.get("distinct_count")
        col_type = (col.get("type") or "").upper()
        is_stringy = any(tok in col_type for tok in ("CHAR", "TEXT", "STRING", "VARCHAR"))
        if is_stringy and distinct is not None and 1 < distinct <= max_distinct:
            return col.get("name")
    return None


def _first_numeric_column(columns: list[dict]) -> str | None:
    numeric_tokens = ("INT", "DEC", "NUM", "FLOAT", "DOUBLE", "REAL")
    for col in columns:
        col_type = (col.get("type") or "").upper()
        if any(tok in col_type for tok in numeric_tokens):
            return col.get("name")
    return None
