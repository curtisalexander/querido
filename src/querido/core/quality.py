"""Data quality checks — per-column null, uniqueness, and issue detection."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def get_quality(
    connector: Connector,
    table: str,
    *,
    columns: list[str] | None = None,
    check_duplicates: bool = False,
) -> dict:
    """Run quality checks on a table.

    Returns::

        {
            "table": str,
            "row_count": int,
            "duplicate_rows": int | None,
            "columns": [
                {
                    "name": str,
                    "type": str,
                    "null_count": int,
                    "null_pct": float,
                    "distinct_count": int,
                    "uniqueness_pct": float,
                    "min": any,
                    "max": any,
                    "status": "ok" | "warn" | "fail",
                    "issues": [str, ...],
                }
            ],
        }
    """
    from querido.connectors.base import validate_table_name
    from querido.sql.renderer import render_template

    validate_table_name(table)

    # Get row count
    count_sql = render_template("count", connector.dialect, table=table)
    row_count = connector.execute(count_sql)[0].get("cnt", 0)

    # Get column metadata
    all_columns = connector.get_columns(table)

    if columns:
        col_names_lower = {c.lower() for c in columns}
        all_columns = [c for c in all_columns if c.get("name", "").lower() in col_names_lower]

    # Build per-column quality query
    col_results = _compute_column_quality(connector, table, all_columns, row_count)

    # Optional duplicate row check
    duplicate_rows = None
    if check_duplicates:
        duplicate_rows = _check_duplicate_rows(connector, table, all_columns)

    return {
        "table": table,
        "row_count": row_count,
        "duplicate_rows": duplicate_rows,
        "columns": col_results,
    }


def _compute_column_quality(
    connector: Connector,
    table: str,
    columns: list[dict],
    row_count: int,
) -> list[dict]:
    """Compute quality metrics for each column via SQL."""
    if not columns or row_count == 0:
        return [
            {
                "name": c.get("name", ""),
                "type": c.get("type", ""),
                "null_count": 0,
                "null_pct": 0.0,
                "distinct_count": 0,
                "uniqueness_pct": 0.0,
                "min": None,
                "max": None,
                "status": "ok",
                "issues": [],
            }
            for c in columns
        ]

    def _q(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    # Build a single query that computes stats for all columns at once
    parts = []
    for col in columns:
        col_name = col.get("name", "")
        qn = _q(col_name)
        parts.append(f'count(*) - count({qn}) as "{col_name}_nulls"')
        parts.append(f'count(distinct {qn}) as "{col_name}_distinct"')
        parts.append(f'min({qn}) as "{col_name}_min"')
        parts.append(f'max({qn}) as "{col_name}_max"')

    sql = f'select {", ".join(parts)} from "{table}"'
    stats_row = connector.execute(sql)[0]

    results = []
    for col in columns:
        name = col.get("name", "")
        null_count = stats_row.get(f"{name}_nulls", 0)
        distinct_count = stats_row.get(f"{name}_distinct", 0)
        min_val = stats_row.get(f"{name}_min")
        max_val = stats_row.get(f"{name}_max")

        null_pct = round(100.0 * null_count / row_count, 2) if row_count else 0.0
        uniqueness_pct = (
            round(100.0 * distinct_count / row_count, 2) if row_count else 0.0
        )

        status, issues = _classify(null_pct, distinct_count, row_count)

        results.append({
            "name": name,
            "type": col.get("type", ""),
            "null_count": null_count,
            "null_pct": null_pct,
            "distinct_count": distinct_count,
            "uniqueness_pct": uniqueness_pct,
            "min": min_val,
            "max": max_val,
            "status": status,
            "issues": issues,
        })

    return results


def _classify(
    null_pct: float,
    distinct_count: int,
    row_count: int,
) -> tuple[str, list[str]]:
    """Classify column quality status and list issues."""
    issues: list[str] = []

    if null_pct > 20:
        issues.append(f"{null_pct}% null")

    if row_count > 0 and distinct_count == 0:
        issues.append("0 distinct values (all null)")

    uniqueness = 100.0 * distinct_count / row_count if row_count else 0
    if row_count > 0 and distinct_count > 0 and uniqueness < 1:
        issues.append(f"{uniqueness:.1f}% unique")

    # Determine status
    if null_pct > 90 or (row_count > 0 and distinct_count == 0):
        status = "fail"
    elif null_pct > 20 or (row_count > 0 and 0 < uniqueness < 1):
        status = "warn"
    else:
        status = "ok"

    return status, issues


def _check_duplicate_rows(
    connector: Connector,
    table: str,
    columns: list[dict],
) -> int:
    """Count fully duplicate rows in the table."""
    def _q(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    col_list = ", ".join(_q(c.get("name", "")) for c in columns)

    # Count groups that appear more than once
    sql = (
        f"select coalesce(sum(dup_count - 1), 0) as duplicates from "
        f"(select {col_list}, count(*) as dup_count "
        f'from "{table}" group by {col_list} having count(*) > 1) as _d'
    )
    result = connector.execute(sql)
    return int(result[0].get("duplicates", 0)) if result else 0
