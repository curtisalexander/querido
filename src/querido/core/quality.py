"""Data quality checks — per-column null, uniqueness, and issue detection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from querido.connectors.base import Connector


class QualityResult(TypedDict):
    """Return shape of :func:`get_quality`. Per-column entries in
    ``columns`` carry violations + stored-metadata enrichment and are not
    narrowed further here."""

    table: str
    row_count: int
    sampled: bool
    sample_size: int | None
    sampling_note: str | None
    duplicate_rows: int | None
    columns: list[dict[str, Any]]


def get_quality(
    connector: Connector,
    table: str,
    *,
    columns: list[str] | None = None,
    check_duplicates: bool = False,
    sample: int | None = None,
    no_sample: bool = False,
    exact: bool = False,
    connection: str | None = None,
) -> QualityResult:
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
    connection:
        When provided, stored metadata is loaded and merged onto each
        column entry (``description``, ``valid_values``, ``pii``,
        ``temporal``, ``likely_sparse``).  When ``valid_values`` is
        stored for a column, a follow-up query counts rows that violate
        the allowed set and surfaces it as ``invalid_count`` plus an
        ``invalid_values`` issue on that column.

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

    # Merge stored metadata onto each column + run enum-membership checks
    # against any column with stored valid_values.
    if connection:
        from querido.core.metadata import load_column_metadata

        stored = load_column_metadata(connection, table)
        if stored:
            _apply_stored_metadata(connector, source, col_results, stored)

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


def _apply_stored_metadata(
    connector: Connector,
    source: str,
    col_results: list[dict],
    stored: dict[str, dict],
) -> None:
    """Merge stored metadata onto each column result and run enum checks.

    For every column with stored ``valid_values``, issues a single
    ``count(*) where col not in (...)`` query and records the result
    as ``invalid_count`` plus an issue + elevated status.
    """
    for col in col_results:
        name = col.get("name")
        if not isinstance(name, str):
            continue
        fields = stored.get(name)
        if not fields:
            continue

        for key in ("description", "pii", "temporal", "likely_sparse"):
            if key in fields:
                col[key] = fields.get(key)

        valid_values = fields.get("valid_values")
        if isinstance(valid_values, list) and valid_values:
            col["valid_values"] = valid_values
            invalid_count = _count_invalid(connector, source, name, valid_values)
            col["invalid_count"] = invalid_count
            if invalid_count > 0:
                issues = col.get("issues") or []
                issues.append(
                    f"{invalid_count} value(s) not in valid_values ({len(valid_values)} allowed)"
                )
                col["issues"] = issues
                if col.get("status") == "ok":
                    col["status"] = "warn"


def _count_invalid(
    connector: Connector,
    source: str,
    column: str,
    valid_values: list,
) -> int:
    """Count rows where ``column`` is non-null and not in ``valid_values``.

    Inlines ``valid_values`` as escaped SQL literals rather than bind
    params — paramstyle differs across SQLite (``?``), DuckDB (``?``),
    and Snowflake (``%s``), and the set is small (``< 20`` by the
    ``values --write-metadata`` writer rule).
    """
    from querido.connectors.base import validate_column_name

    validate_column_name(column)
    literals = ", ".join(_sql_literal(v) for v in valid_values)
    qcol = '"' + column.replace('"', '""') + '"'
    sql = (
        f"select count(*) as invalid "
        f"from {source} "
        f"where {qcol} is not null and {qcol} not in ({literals})"
    )
    rows = connector.execute(sql)
    if not rows:
        return 0
    return int(rows[0].get("invalid", 0) or 0)


def _sql_literal(value: object) -> str:
    """Render *value* as a SQL literal (numbers inline, others single-quoted)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


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
