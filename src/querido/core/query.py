"""Ad-hoc SQL query execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def run_query(connector: Connector, sql: str, *, limit: int = 1000) -> dict:
    """Execute arbitrary SQL and return structured results.

    Returns::

        {
            "sql": str,
            "columns": [str, ...],
            "rows": [dict, ...],
            "row_count": int,
            "limited": bool,
        }

    When *limit* is > 0, the query is wrapped with a LIMIT clause as a
    safety net.  Set *limit* to 0 to disable the limit.
    """
    from querido.connectors.arrow_util import arrow_to_dicts, execute_arrow_or_dicts

    effective_sql = _apply_limit(sql, limit) if limit > 0 else sql
    data, is_arrow = execute_arrow_or_dicts(connector, effective_sql)
    rows = arrow_to_dicts(data, is_arrow)

    columns = list(rows[0].keys()) if rows else []

    return {
        "sql": effective_sql,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "limited": limit > 0 and len(rows) >= limit,
    }


def _apply_limit(sql: str, limit: int) -> str:
    """Wrap *sql* in a subquery with a LIMIT clause.

    If the user's SQL already contains a LIMIT, the outer LIMIT acts as a
    ceiling — the database will use the smaller of the two.
    """
    stripped = sql.rstrip().rstrip(";")
    return f"select * from ({stripped}) as _q limit {limit}"
