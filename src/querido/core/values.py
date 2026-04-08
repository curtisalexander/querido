"""Distinct value enumeration for a column."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def get_distinct_values(
    connector: Connector,
    table: str,
    column: str,
    *,
    max_values: int = 1000,
    sort: str = "value",
) -> dict:
    """Return distinct values for a column.

    Returns::

        {
            "table": str,
            "column": str,
            "distinct_count": int,
            "total_rows": int,
            "null_count": int,
            "truncated": bool,
            "values": [{"value": any, "count": int}, ...],
        }

    When distinct count exceeds *max_values*, returns the top values by
    frequency and sets ``truncated=True``.

    *sort*: ``"value"`` for alphabetical, ``"frequency"`` for count desc.
    """
    from querido.connectors.base import validate_column_name, validate_table_name

    validate_table_name(table)
    validate_column_name(column)

    # Single-scan CTE: group once, derive stats from the grouped result.
    # We fetch max_values + 1 rows to detect truncation without a separate
    # count(distinct) query.
    fetch_limit = max_values + 1
    values_sql = (
        f"with grouped as ("
        f'select "{column}" as value, count(*) as count '
        f'from "{table}" '
        f'group by "{column}"'
        f") "
        f"select value, count, "
        f"sum(count) over() as total_rows, "
        f"coalesce((select count from grouped where value is null), 0) as null_count, "
        f"count(*) over() as distinct_count "
        f"from grouped "
        f"where value is not null "
        f"order by count desc, value asc "
        f"limit {fetch_limit}"
    )
    rows = connector.execute(values_sql)

    # Extract stats from first row (window functions populate every row)
    if rows:
        total_rows = rows[0].get("total_rows", 0)
        null_count = rows[0].get("null_count", 0)
        distinct_count = rows[0].get("distinct_count", 0)
    else:
        total_rows = connector.get_row_count(table)
        null_count = 0
        distinct_count = 0

    # Detect truncation: if we got more rows than max_values, trim
    truncated = len(rows) > max_values
    if truncated:
        rows = rows[:max_values]

    # Strip stats columns from result rows
    rows = [{"value": r.get("value"), "count": r.get("count", 0)} for r in rows]

    # If user wants value sort, re-sort (we always fetch by frequency for truncation)
    if sort == "value":
        rows.sort(key=lambda r: (r.get("value") is None, str(r.get("value", ""))))

    return {
        "table": table,
        "column": column,
        "distinct_count": distinct_count,
        "total_rows": total_rows,
        "null_count": null_count,
        "truncated": truncated,
        "values": rows,
    }
