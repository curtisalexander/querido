"""Cheap read-only cost / shape estimates for query and export."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def estimate_query(
    connector: Connector,
    sql: str,
    *,
    effective_sql: str,
    limit: int,
    allow_write: bool,
    destructive: bool,
) -> dict[str, Any]:
    """Estimate query shape and rough cost without executing the SQL."""
    from querido.core.explain import get_explain

    explain_plan = None
    if not destructive:
        try:
            explain_plan = get_explain(connector, effective_sql)["plan"]
        except Exception:
            explain_plan = None

    complexity = _classify_complexity(effective_sql)
    cost_hint = _cost_hint(
        complexity=complexity,
        row_estimate=None,
        limit=limit,
        destructive=destructive,
    )
    output_row_ceiling = limit if limit > 0 else None

    notes = []
    if destructive and not allow_write:
        notes.append("Would still require --allow-write to run for real.")
    if explain_plan is None:
        notes.append("No cheap row estimate available for this SQL shape.")

    summary = "Estimated read-only query cost."
    if destructive:
        summary = "Estimated write-query cost (no mutation performed)."

    return {
        "mode": "estimate",
        "action": "query",
        "summary": summary,
        "dialect": connector.dialect,
        "sql": effective_sql,
        "original_sql": sql,
        "destructive": destructive,
        "allow_write": allow_write,
        "limit": limit,
        "output_row_ceiling": output_row_ceiling,
        "row_estimate": None,
        "row_estimate_source": None,
        "complexity": complexity,
        "cost_hint": cost_hint,
        "explain_plan": explain_plan,
        "notes": notes,
    }


def estimate_export(
    connector: Connector,
    *,
    sql: str,
    table: str | None,
    fmt: str,
    destination: str,
    output_path: str | None,
    clipboard: bool,
    columns: list[str] | None,
    limit: int | None,
    filter_expr: str | None,
) -> dict[str, Any]:
    """Estimate export shape and rough cost without executing the export."""
    from querido.core.explain import get_explain

    row_estimate = None
    row_estimate_source = None
    if table and filter_expr is None:
        try:
            row_estimate = connector.get_row_count(table)
            row_estimate_source = "table metadata"
        except Exception:
            row_estimate = None

    explain_plan = None
    try:
        explain_plan = get_explain(connector, sql)["plan"]
    except Exception:
        explain_plan = None

    output_row_ceiling = limit
    if isinstance(row_estimate, int) and limit is not None:
        output_row_ceiling = min(row_estimate, limit)
    elif isinstance(row_estimate, int):
        output_row_ceiling = row_estimate

    complexity = _classify_complexity(sql)
    cost_hint = _cost_hint(
        complexity=complexity,
        row_estimate=row_estimate,
        limit=limit or 0,
        destructive=False,
    )

    destination_label = (
        f"file: {output_path}" if destination == "file" else "clipboard" if clipboard else "stdout"
    )

    notes = []
    if row_estimate is None:
        notes.append("Row estimate unavailable; shape depends on the query/filter.")

    return {
        "mode": "estimate",
        "action": "export",
        "summary": f"Estimated export cost for {destination_label}.",
        "dialect": connector.dialect,
        "sql": sql,
        "format": fmt,
        "destination": destination,
        "output_path": output_path,
        "clipboard": clipboard,
        "table": table,
        "columns": columns or [],
        "limit": limit,
        "filter": filter_expr,
        "row_estimate": row_estimate,
        "row_estimate_source": row_estimate_source,
        "output_row_ceiling": output_row_ceiling,
        "complexity": complexity,
        "cost_hint": cost_hint,
        "explain_plan": explain_plan,
        "notes": notes,
    }


def _classify_complexity(sql: str) -> str:
    lowered = sql.lower()
    score = 0
    for token, weight in (
        (" join ", 2),
        (" group by ", 2),
        (" order by ", 1),
        (" distinct ", 1),
        (" union ", 2),
        (" with ", 2),
        (" over (", 2),
        (" having ", 1),
    ):
        if token in lowered:
            score += weight
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _cost_hint(
    *,
    complexity: str,
    row_estimate: int | None,
    limit: int,
    destructive: bool,
) -> str:
    if destructive:
        return "high"
    if isinstance(row_estimate, int):
        effective_rows = min(row_estimate, limit) if limit > 0 else row_estimate
        if effective_rows > 1_000_000 or complexity == "high":
            return "high"
        if effective_rows > 100_000 or complexity == "medium":
            return "medium"
        return "low"
    return "medium" if complexity in {"medium", "high"} else "low"
