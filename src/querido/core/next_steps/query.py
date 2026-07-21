"""``next_steps`` rules for ad-hoc SQL and analysis commands."""

from __future__ import annotations

from querido.core.next_steps._helpers import _step


def for_diff(
    result: dict,
    *,
    connection: str,
    left_table: str,
    right_table: str | None,
    target_connection: str | None = None,
) -> list[dict]:
    """Rules for ``qdo diff``.

    If schemas match, encourage data-level checks. Otherwise, offer context
    on each side so the agent can reason about why they diverged.
    """
    steps: list[dict] = []
    added = result.get("added") or []
    removed = result.get("removed") or []
    changed = result.get("changed") or []
    right_conn = target_connection or connection
    right_target = right_table or result.get("right") or left_table

    if not added and not removed and not changed:
        steps.append(
            _step(
                ["qdo", "context", "-c", connection, "-t", left_table],
                "Schemas match — compare data shape instead via context.",
            )
        )
        return steps

    steps.append(
        _step(
            ["qdo", "inspect", "-c", connection, "-t", left_table],
            f"Full schema for left side ('{left_table}').",
        )
    )
    steps.append(
        _step(
            ["qdo", "inspect", "-c", right_conn, "-t", right_target],
            f"Full schema for right side ('{right_target}').",
        )
    )
    return steps


def for_query(
    result: dict,
    *,
    connection: str,
) -> list[dict]:
    """Rules for ``qdo query``.

    Limited results → nudge toward raising the limit or exporting. No rows
    → suggest a schema check. Rows with recognizable table-like output →
    (no action; the agent already has what it needs).
    """
    steps: list[dict] = []
    rows = result.get("rows") or []
    row_count = len(rows)
    limited = bool(result.get("limited"))

    if row_count == 0:
        steps.append(
            _step(
                ["qdo", "catalog", "-c", connection],
                "Query returned no rows — confirm the referenced tables exist.",
            )
        )
        return steps

    if limited:
        steps.append(
            _step(
                ["qdo", "export", "-c", connection, "--export-format", "csv"],
                "Results were limit-capped — use export to stream everything.",
            )
        )

    return steps


def for_assert(
    result: dict,
    *,
    connection: str,
) -> list[dict]:
    """Rules for ``qdo assert``.

    On fail: point at the underlying query so the agent can see the actual
    rows behind the counter it asserted on. On pass: no nudge — success
    rarely warrants a follow-up, and noise here costs agent tokens.
    """
    steps: list[dict] = []
    if result.get("passed", False):
        return steps

    sql = result.get("sql") or ""
    if sql:
        steps.append(
            _step(
                ["qdo", "query", "-c", connection, "--sql", sql],
                "Assertion failed — run the underlying query to see actual rows.",
            )
        )
    return steps


def for_explain(
    result: dict,
    *,
    connection: str,
) -> list[dict]:
    """Rules for ``qdo explain``.

    Natural next moves: run the query for real, or (DuckDB only) re-run
    with ``--analyze`` for runtime stats.
    """
    steps: list[dict] = []
    sql = result.get("sql") or ""
    dialect = result.get("dialect") or ""
    analyzed = bool(result.get("analyzed"))

    if sql:
        steps.append(
            _step(
                ["qdo", "query", "-c", connection, "--sql", sql],
                "Execute the query to see actual results.",
            )
        )

    if not analyzed and dialect == "duckdb" and sql:
        steps.append(
            _step(
                ["qdo", "explain", "-c", connection, "--sql", sql, "--analyze"],
                "Re-run with --analyze for actual runtime stats (DuckDB).",
            )
        )

    return steps
