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
    sample: int | None = None,
    no_sample: bool = False,
    exact: bool = False,
) -> dict:
    """Run quality checks on a table.

    Parameters
    ----------
    sample:
        Explicit sample size (rows).  ``None`` = auto-sample at >1M rows.
    no_sample:
        If ``True``, scan the full table (slower but exact).
    exact:
        If ``True``, use exact ``COUNT(DISTINCT)`` instead of
        ``APPROX_COUNT_DISTINCT`` on Snowflake/DuckDB.

    Returns::

        {
            "table": str,
            "row_count": int,
            "sampled": bool,
            "sample_size": int | None,
            "sampling_note": str | None,
            "duplicate_rows": int | None,
            "columns": [...]
        }
    """
    from querido.connectors.base import validate_table_name
    from querido.core._utils import build_sample_source, resolve_row_count_for_sampling

    validate_table_name(table)

    # Get column metadata
    all_columns = connector.get_columns(table)

    if columns:
        col_names_lower = {c.lower() for c in columns}
        all_columns = [c for c in all_columns if c.get("name", "").lower() in col_names_lower]

    # Determine sampling
    row_count_for_sample = resolve_row_count_for_sampling(
        connector, table, sample=sample, no_sample=no_sample
    )
    source, sampled, sample_size = build_sample_source(
        connector, table, row_count_for_sample, sample=sample, no_sample=no_sample
    )

    use_approx = not exact and connector.dialect in ("snowflake", "duckdb")

    # Build per-column quality query — row count comes from the same scan
    col_results, row_count = _compute_column_quality(
        connector, source, all_columns, approx=use_approx
    )

    # Optional duplicate row check (always against the real table, not sample)
    duplicate_rows = None
    if check_duplicates:
        duplicate_rows = _check_duplicate_rows(connector, table, all_columns)

    # Build sampling note for human / agent consumption
    sampling_note = None
    if sampled and sample_size:
        sampling_note = (
            f"Results based on a sample of {sample_size:,} rows. "
            "Use --no-sample for exact results (slower)."
        )

    return {
        "table": table,
        "row_count": row_count,
        "sampled": sampled,
        "sample_size": sample_size,
        "sampling_note": sampling_note,
        "duplicate_rows": duplicate_rows,
        "columns": col_results,
    }


def _compute_column_quality(
    connector: Connector,
    source: str,
    columns: list[dict],
    *,
    approx: bool = False,
) -> tuple[list[dict], int]:
    """Compute quality metrics for each column via a single SQL scan.

    Returns ``(col_results, row_count)``.  ``count(*)`` is included in the
    same query as the per-column stats so the table is scanned only once.

    When *approx* is ``True``, uses ``APPROX_COUNT_DISTINCT`` instead of
    exact ``COUNT(DISTINCT)`` for faster execution on large tables.
    """
    if not columns:
        return [], 0

    def _q(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    # count(*) rides along with per-column stats — one scan total
    parts = ["count(*) as _total_rows"]
    for col in columns:
        col_name = col.get("name", "")
        qn = _q(col_name)
        parts.append(f'count(*) - count({qn}) as "{col_name}_nulls"')
        if approx:
            parts.append(f'approx_count_distinct({qn}) as "{col_name}_distinct"')
        else:
            parts.append(f'count(distinct {qn}) as "{col_name}_distinct"')
        parts.append(f'min({qn}) as "{col_name}_min"')
        parts.append(f'max({qn}) as "{col_name}_max"')

    sql = f"select {', '.join(parts)} from {source}"
    stats_row = connector.execute(sql)[0]
    row_count = int(stats_row.get("_total_rows", 0) or 0)

    if row_count == 0:
        return (
            [
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
            ],
            0,
        )

    results = []
    for col in columns:
        name = col.get("name", "")
        null_count = stats_row.get(f"{name}_nulls", 0)
        distinct_count = stats_row.get(f"{name}_distinct", 0)
        min_val = stats_row.get(f"{name}_min")
        max_val = stats_row.get(f"{name}_max")

        null_pct = round(100.0 * null_count / row_count, 2) if row_count else 0.0
        uniqueness_pct = round(100.0 * distinct_count / row_count, 2) if row_count else 0.0

        status, issues = _classify(null_pct, distinct_count, row_count)

        results.append(
            {
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
            }
        )

    return results, row_count


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
