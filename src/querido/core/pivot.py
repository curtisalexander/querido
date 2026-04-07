"""Pivot table query builder and executor."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def build_pivot_query(
    table: str,
    rows: list[str],
    values: list[str],
    agg: str,
    *,
    filter_expr: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> str:
    """Generate a GROUP BY SQL query for pivot summarization.

    Parameters
    ----------
    table : str
        Table name (already validated).
    rows : list[str]
        Columns to group by (already validated).
    values : list[str]
        Columns to aggregate (already validated).
    agg : str
        Aggregation function (COUNT, SUM, AVG, MIN, MAX).
    filter_expr : str, optional
        SQL WHERE clause expression (passed through, not validated).
    order_by : str, optional
        SQL ORDER BY expression. Defaults to group-by columns.
    limit : int, optional
        Maximum number of result rows.

    Returns
    -------
    str
        SQL query string.
    """

    from querido.connectors.base import validate_column_name, validate_table_name

    validate_table_name(table)
    for col in rows:
        validate_column_name(col)
    for col in values:
        validate_column_name(col)

    valid_aggs = {"COUNT", "SUM", "AVG", "MIN", "MAX"}
    if agg.upper() not in valid_aggs:
        raise ValueError(f"Invalid aggregation: {agg!r}. Must be one of: {sorted(valid_aggs)}")

    def _q(name: str) -> str:
        """Quote an identifier with double quotes."""
        return '"' + name.replace('"', '""') + '"'

    group_cols = ", ".join(_q(r) for r in rows)
    agg_exprs = ", ".join(f'{agg}({_q(v)}) AS "{agg.lower()}_{v}"' for v in values)

    parts = [f"select {group_cols}, {agg_exprs} from {_q(table)}"]

    if filter_expr:
        parts.append(f"where {filter_expr}")

    parts.append(f"group by {group_cols}")
    parts.append(f"order by {order_by}" if order_by else f"order by {group_cols}")

    if limit is not None and limit > 0:
        parts.append(f"limit {limit}")

    return " ".join(parts)


def get_pivot(
    connector: Connector,
    table: str,
    *,
    rows: list[str],
    values: list[str],
    agg: str,
    filter_expr: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> dict:
    """Execute a pivot query and return results.

    Returns::

        {
            "headers": list[str],
            "rows": list[dict],
            "row_count": int,
            "sql": str,
        }
    """
    sql = build_pivot_query(
        table, rows, values, agg,
        filter_expr=filter_expr, order_by=order_by, limit=limit,
    )
    data = connector.execute(sql)
    headers = list(data[0].keys()) if data else rows + [f"{agg.lower()}_{v}" for v in values]
    return {
        "headers": headers,
        "rows": data,
        "row_count": len(data),
        "sql": sql,
    }
