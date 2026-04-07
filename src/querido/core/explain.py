"""Query plan / EXPLAIN wrapper per dialect."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def get_explain(
    connector: Connector,
    sql: str,
    *,
    analyze: bool = False,
) -> dict:
    """Run EXPLAIN on *sql* and return the query plan.

    Returns::

        {
            "plan": str,
            "sql": str,
            "dialect": str,
            "analyzed": bool,
        }
    """
    dialect = connector.dialect

    explain_sql = _explain_analyze_sql(dialect, sql) if analyze else _explain_sql(dialect, sql)

    rows = connector.execute(explain_sql)
    plan_text = _format_plan(dialect, rows, analyze)

    return {
        "plan": plan_text,
        "sql": sql,
        "dialect": dialect,
        "analyzed": analyze,
    }


def _explain_sql(dialect: str, sql: str) -> str:
    """Build the EXPLAIN statement for each dialect."""
    stripped = sql.rstrip().rstrip(";")
    if dialect == "sqlite":
        return f"explain query plan {stripped}"
    if dialect == "snowflake":
        return f"explain using text {stripped}"
    # duckdb and others
    return f"explain {stripped}"


def _explain_analyze_sql(dialect: str, sql: str) -> str:
    """Build EXPLAIN ANALYZE where supported."""
    stripped = sql.rstrip().rstrip(";")
    if dialect == "sqlite":
        # SQLite doesn't support EXPLAIN ANALYZE — fall back to regular
        return f"explain query plan {stripped}"
    if dialect == "snowflake":
        return f"explain using text {stripped}"
    # duckdb supports explain analyze
    return f"explain analyze {stripped}"


def _format_plan(dialect: str, rows: list[dict], analyzed: bool) -> str:
    """Convert EXPLAIN result rows into a readable plan string."""
    if not rows:
        return "(empty plan)"

    if dialect == "sqlite":
        # SQLite EXPLAIN QUERY PLAN returns: id, parent, notused, detail
        lines = []
        for row in rows:
            detail = row.get("detail", "")
            row_id = row.get("id", 0)
            parent = row.get("parent", 0)
            indent = "  " * (1 if parent > 0 else 0)
            prefix = "|--" if row_id > 0 else ""
            lines.append(f"{indent}{prefix}{detail}")
        return "\n".join(lines)

    if dialect == "duckdb":
        # DuckDB EXPLAIN returns a single column "explain_value"
        # or for EXPLAIN ANALYZE, may return multiple columns
        lines = []
        for row in rows:
            # Try common column names
            val = (
                row.get("explain_value")
                or row.get("explain_key", "")
                or next(iter(row.values()), "")
            )
            lines.append(str(val))
        return "\n".join(lines)

    # Snowflake and others — concatenate all values
    lines = []
    for row in rows:
        vals = [str(v) for v in row.values() if v is not None]
        lines.append(" ".join(vals))
    return "\n".join(lines)
