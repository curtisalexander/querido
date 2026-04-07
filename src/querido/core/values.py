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

    # Get total rows and null count in one query
    stats_sql = (
        f"select count(*) as total_rows, "
        f'count(*) - count("{column}") as null_count, '
        f'count(distinct "{column}") as distinct_count '
        f'from "{table}"'
    )
    stats = connector.execute(stats_sql)[0]
    total_rows = stats.get("total_rows", 0)
    null_count = stats.get("null_count", 0)
    distinct_count = stats.get("distinct_count", 0)

    # Decide whether to fetch all or top-N
    truncated = distinct_count > max_values
    limit = max_values if truncated else distinct_count + 1  # +1 headroom

    # Always fetch with counts — useful for both sort modes
    values_sql = (
        f'select "{column}" as value, count(*) as count '
        f'from "{table}" '
        f'where "{column}" is not null '
        f'group by "{column}" '
    )

    if sort == "frequency" or truncated:
        # When truncated, always sort by frequency to get the top values
        values_sql += f"order by count desc, value asc limit {limit}"
    else:
        values_sql += f"order by value asc limit {limit}"

    rows = connector.execute(values_sql)

    # If user wants value sort but we fetched by frequency (truncated), re-sort
    if truncated and sort == "value":
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
