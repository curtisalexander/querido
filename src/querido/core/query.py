"""Ad-hoc SQL query execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def run_query(
    connector: Connector,
    sql: str,
    *,
    limit: int = 1000,
    allow_write: bool = False,
) -> dict:
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
    from querido.core.sql_safety import any_statement_is_destructive

    is_write = any_statement_is_destructive(sql)
    effective_sql = _apply_limit(sql, limit) if limit > 0 and not is_write else sql
    data, is_arrow = execute_arrow_or_dicts(connector, effective_sql)
    rows = arrow_to_dicts(data, is_arrow)
    if is_write and allow_write:
        _commit_if_possible(connector)

    columns = list(rows[0].keys()) if rows else []

    return {
        "sql": effective_sql,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "limited": limit > 0 and len(rows) >= limit,
    }


def _commit_if_possible(connector: Connector) -> None:
    """Commit a write if the connector exposes a transaction object."""
    conn = getattr(connector, "conn", None)
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()


def _apply_limit(sql: str, limit: int) -> str:
    """Wrap *sql* in a subquery with a LIMIT clause.

    If the user's SQL already contains a LIMIT, the outer LIMIT acts as a
    ceiling — the database will use the smaller of the two.
    """
    stripped = sql.rstrip().rstrip(";")
    return f"select * from ({stripped}) as _q limit {limit}"
