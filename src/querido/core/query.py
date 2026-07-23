"""Ad-hoc SQL query execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


@dataclass(frozen=True)
class PreparedQuery:
    """SQL facts shared by query planning, estimation, and execution."""

    original_sql: str
    effective_sql: str
    destructive: bool


def prepare_query(sql: str, *, limit: int = 1000) -> PreparedQuery:
    """Classify *sql* and apply the read-only row limit used at execution."""
    from querido.core.sql_safety import any_statement_is_destructive

    destructive = any_statement_is_destructive(sql)
    effective_sql = _apply_limit(sql, limit) if limit > 0 and not destructive else sql
    return PreparedQuery(
        original_sql=sql,
        effective_sql=effective_sql,
        destructive=destructive,
    )


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

    prepared = prepare_query(sql, limit=limit)
    if prepared.destructive and not allow_write:
        raise ValueError(
            "Write queries require allow_write=True; this query is read-only by default."
        )
    data, is_arrow = execute_arrow_or_dicts(connector, prepared.effective_sql)
    rows = arrow_to_dicts(data, is_arrow)
    if prepared.destructive and allow_write:
        _commit_if_possible(connector)

    columns = list(rows[0].keys()) if rows else []

    return {
        "sql": prepared.effective_sql,
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
