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

    Returns
    -------
    str
        SQL query string.
    """

    valid_aggs = {"COUNT", "SUM", "AVG", "MIN", "MAX"}
    if agg.upper() not in valid_aggs:
        raise ValueError(f"Invalid aggregation: {agg!r}. Must be one of: {sorted(valid_aggs)}")

    def _q(name: str) -> str:
        """Quote an identifier with double quotes."""
        return '"' + name.replace('"', '""') + '"'

    group_cols = ", ".join(_q(r) for r in rows)
    agg_exprs = ", ".join(f'{agg}({_q(v)}) AS "{agg.lower()}_{v}"' for v in values)
    return (
        f"select {group_cols}, {agg_exprs} from {_q(table)}"
        f" group by {group_cols} order by {group_cols}"
    )


def get_pivot(
    connector: Connector,
    table: str,
    *,
    rows: list[str],
    values: list[str],
    agg: str,
) -> dict:
    """Execute a pivot query and return results.

    Returns::

        {
            "headers": list[str],
            "rows": list[dict],
            "sql": str,
        }
    """
    sql = build_pivot_query(table, rows, values, agg)
    data = connector.execute(sql)
    headers = list(data[0].keys()) if data else rows + [f"{agg.lower()}_{v}" for v in values]
    return {
        "headers": headers,
        "rows": data,
        "sql": sql,
    }
