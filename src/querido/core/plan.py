"""Planning helpers for dry-run / --plan CLI paths."""

from __future__ import annotations

from typing import Any


def build_query_plan(
    *,
    sql: str,
    effective_sql: str,
    allow_write: bool,
    limit: int,
    destructive: bool,
) -> dict[str, Any]:
    """Build a plan payload for ``qdo query --plan``."""
    executable = not destructive or allow_write
    summary = "Would execute read-only query."
    if destructive and not allow_write:
        summary = "Would be blocked: write query requires --allow-write."
    elif destructive:
        summary = "Would execute write query."

    effects = ["Execute SQL against the target connection."]
    if limit > 0 and effective_sql != sql:
        effects.append(f"Wrap the SQL in an outer LIMIT {limit} safety cap.")
    if destructive and allow_write:
        effects.append("Commit the mutation if the connector supports transactions.")

    return {
        "mode": "plan",
        "action": "query",
        "summary": summary,
        "executable": executable,
        "destructive": destructive,
        "allow_write": allow_write,
        "limit": limit,
        "sql": effective_sql,
        "original_sql": sql,
        "effects": effects,
        "writes": [],
    }


def build_export_plan(
    *,
    sql: str,
    fmt: str,
    destination: str,
    output_path: str | None,
    clipboard: bool,
    table: str | None,
    columns: list[str] | None,
    limit: int | None,
    filter_expr: str | None,
) -> dict[str, Any]:
    """Build a plan payload for ``qdo export --plan``."""
    destination_label = (
        f"file: {output_path}" if destination == "file" else "clipboard" if clipboard else "stdout"
    )
    effects = [
        f"Run the export SQL and format rows as {fmt}.",
        f"Send the formatted output to {destination_label}.",
    ]
    writes = [output_path] if destination == "file" and output_path else []
    if clipboard:
        writes.append("clipboard")

    return {
        "mode": "plan",
        "action": "export",
        "summary": f"Would export {table or 'query results'} as {fmt} to {destination_label}.",
        "executable": True,
        "sql": sql,
        "format": fmt,
        "destination": destination,
        "output_path": output_path,
        "clipboard": clipboard,
        "table": table,
        "columns": columns or [],
        "limit": limit,
        "filter": filter_expr,
        "effects": effects,
        "writes": writes,
    }
