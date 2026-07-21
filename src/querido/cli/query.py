"""``qdo query`` — execute ad-hoc SQL against a connection."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors
from querido.cli._options import conn_opt, dbtype_opt

app = typer.Typer(help="Execute ad-hoc SQL queries.")


def _build_run_cmd(
    *,
    connection: str,
    from_step: str | None,
    query_sql: str,
    allow_write: bool,
    limit: int,
) -> list[str]:
    """Reconstruct the equivalent ``qdo query`` invocation for next_steps.

    Shared by the ``--plan`` and ``--estimate`` paths so the two stay in sync.
    """
    run_cmd = ["qdo", "query", "-c", connection]
    if from_step:
        run_cmd += ["--from", from_step]
    else:
        run_cmd += ["--sql", query_sql]
    if allow_write:
        run_cmd.append("--allow-write")
    if limit != 1000:
        run_cmd += ["--limit", str(limit)]
    return run_cmd


@app.callback(invoke_without_command=True)
@friendly_errors
def query(
    connection: str = conn_opt,
    sql: str | None = typer.Option(None, "--sql", "-s", help="SQL query string."),
    file: str | None = typer.Option(None, "--file", "-F", help="Path to a .sql file to execute."),
    from_step: str | None = typer.Option(
        None,
        "--from",
        help=(
            "Reuse SQL from a prior session step "
            "(<session>:<step>, e.g. 'scratch:3' or 'scratch:last'). "
            "The source step must have been recorded with -f json."
        ),
    ),
    allow_write: bool = typer.Option(
        False,
        "--allow-write",
        help="Allow INSERT/UPDATE/DELETE/DDL statements. Read-only by default.",
    ),
    plan: bool = typer.Option(
        False,
        "--plan",
        help="Preview the SQL and side effects without executing it.",
    ),
    estimate: bool = typer.Option(
        False,
        "--estimate",
        help="Estimate query cost/shape without executing it.",
    ),
    limit: int = typer.Option(
        1000, "--limit", "-l", min=0, help="Max rows to return (0 = no limit)."
    ),
    db_type: str | None = dbtype_opt,
) -> None:
    """Execute arbitrary SQL and display results.

    SQL can be provided via --sql, --file, or stdin:

        qdo query -c ./my.db --sql "select * from users"
        qdo query -c ./my.db --file report.sql
        echo "select 1" | qdo query -c ./my.db
    """
    import sys

    from querido.cli._context import maybe_show_sql
    from querido.cli._errors import set_last_sql
    from querido.cli._options import build_source_meta, resolve_query_sql
    from querido.cli._pipeline import database_command, emit

    query_sql, source = resolve_query_sql(
        sql_option=sql,
        file_option=file,
        from_option=from_step,
        stdin=sys.stdin,
    )
    if plan and estimate:
        raise typer.BadParameter("Cannot use both --plan and --estimate.")

    source_meta = build_source_meta(source, connection=connection)

    from querido.core.query import _apply_limit
    from querido.core.sql_safety import any_statement_is_destructive

    destructive = any_statement_is_destructive(query_sql)
    effective_sql = _apply_limit(query_sql, limit) if limit > 0 and not destructive else query_sql

    if plan:
        from querido._shell import cmd
        from querido.core.plan import build_query_plan

        maybe_show_sql(effective_sql)
        set_last_sql(effective_sql)
        payload = build_query_plan(
            sql=query_sql,
            effective_sql=effective_sql,
            allow_write=allow_write,
            limit=limit,
            destructive=destructive,
        )
        run_cmd = _build_run_cmd(
            connection=connection,
            from_step=from_step,
            query_sql=query_sql,
            allow_write=allow_write,
            limit=limit,
        )

        steps = []
        if payload["executable"]:
            steps.append({"cmd": cmd(run_cmd), "why": "Run the planned query for real."})
        else:
            steps.append(
                {
                    "cmd": cmd([*run_cmd, "--allow-write"]),
                    "why": "Allow the write explicitly, then rerun the planned query.",
                }
            )
        emit(
            "query",
            payload,
            dispatch_as="plan",
            next_steps=steps,
            connection=connection,
            extra_meta=source_meta or None,
        )
        return

    if estimate:
        from querido._shell import cmd
        from querido.core.estimate import estimate_query

        with database_command(connection=connection, db_type=db_type) as ctx:
            maybe_show_sql(effective_sql)
            set_last_sql(effective_sql)
            payload = estimate_query(
                ctx.connector,
                query_sql,
                effective_sql=effective_sql,
                limit=limit,
                allow_write=allow_write,
                destructive=destructive,
            )

        run_cmd = _build_run_cmd(
            connection=connection,
            from_step=from_step,
            query_sql=query_sql,
            allow_write=allow_write,
            limit=limit,
        )

        steps = [{"cmd": cmd(run_cmd), "why": "Run the estimated query for real."}]
        if destructive and not allow_write:
            steps.insert(
                0,
                {
                    "cmd": cmd([*run_cmd, "--allow-write"]),
                    "why": "Allow the write explicitly before running the estimated query.",
                },
            )
        emit(
            "query",
            payload,
            dispatch_as="estimate",
            next_steps=steps,
            connection=connection,
            extra_meta=source_meta or None,
        )
        return

    from querido.cli._validation import require_allow_write

    require_allow_write(query_sql, allow_write=allow_write)

    with database_command(
        connection=connection, db_type=db_type, read_only=not allow_write
    ) as ctx:
        maybe_show_sql(query_sql)
        set_last_sql(query_sql)

        with ctx.spin("Executing query"):
            from querido.core.query import run_query

            result = run_query(ctx.connector, query_sql, limit=limit, allow_write=allow_write)

        from querido.core.next_steps import for_query

        if emit(
            "query",
            result.get("columns", []),
            result.get("rows", []),
            result.get("row_count", 0),
            data={
                "columns": result.get("columns", []),
                "row_count": result.get("row_count", 0),
                "limited": result.get("limited", False),
                "rows": result.get("rows", []),
                "sql": query_sql,
            },
            next_steps=lambda: for_query(result, connection=connection),
            connection=connection,
            extra_meta=source_meta or None,
            limited=result.get("limited", False),
            sql=query_sql,
        ):
            return
