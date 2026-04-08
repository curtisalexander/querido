"""``qdo assert`` — verify SQL assertions with exit codes."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Assert conditions on query results.")


@app.callback(invoke_without_command=True)
@friendly_errors
def assert_cmd(
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    sql: str | None = typer.Option(
        None, "--sql", "-s", help="SQL query (must return a single numeric value)."
    ),
    file: str | None = typer.Option(None, "--file", "-F", help="Path to a .sql file."),
    db_type: str | None = typer.Option(
        None,
        "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
    expect: float | None = typer.Option(None, "--expect", help="Assert result equals this value."),
    expect_gt: float | None = typer.Option(None, "--expect-gt", help="Assert result > value."),
    expect_lt: float | None = typer.Option(None, "--expect-lt", help="Assert result < value."),
    expect_gte: float | None = typer.Option(None, "--expect-gte", help="Assert result >= value."),
    expect_lte: float | None = typer.Option(None, "--expect-lte", help="Assert result <= value."),
    name: str | None = typer.Option(
        None, "--name", "-n", help="Descriptive name for the assertion."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="No output, just exit code."),
) -> None:
    """Assert a SQL query result meets a condition.

    Exit codes: 0 = passed, 1 = failed, 2 = SQL error.

    Examples:

        qdo assert -c ./my.db --sql "select count(*) from users" --expect 100
        qdo assert -c ./my.db --sql "select count(*) from users where age < 0" --expect 0
        qdo assert -c ./my.db --sql "select avg(score) from results" --expect-gte 80
    """
    import sys

    from querido.cli._context import maybe_show_sql
    from querido.cli._errors import set_last_sql
    from querido.cli._options import resolve_sql
    from querido.cli._pipeline import database_command

    query_sql = resolve_sql(sql, file, sys.stdin)
    operator, expected = _resolve_operator(expect, expect_gt, expect_lt, expect_gte, expect_lte)

    with database_command(connection=connection, db_type=db_type) as ctx:
        maybe_show_sql(query_sql)
        set_last_sql(query_sql)

        with ctx.spin("Running assertion"):
            from querido.core.assert_check import run_assertion

            result = run_assertion(
                ctx.connector,
                query_sql,
                operator=operator,
                expected=expected,
                name=name,
            )

    if not quiet:
        from querido.cli._pipeline import dispatch_output

        dispatch_output("assert_check", result)

    if not result.get("passed", False):
        raise typer.Exit(code=1)


def _resolve_operator(
    expect: float | None,
    expect_gt: float | None,
    expect_lt: float | None,
    expect_gte: float | None,
    expect_lte: float | None,
) -> tuple[str, float]:
    """Return (operator, expected_value) from the provided flags."""
    options = [
        ("eq", expect),
        ("gt", expect_gt),
        ("lt", expect_lt),
        ("gte", expect_gte),
        ("lte", expect_lte),
    ]
    provided = [(op, val) for op, val in options if val is not None]

    if len(provided) == 0:
        raise typer.BadParameter(
            "Must provide one of: --expect, --expect-gt, --expect-lt, --expect-gte, --expect-lte"
        )
    if len(provided) > 1:
        flags = [f"--expect-{op}" if op != "eq" else "--expect" for op, _ in provided]
        raise typer.BadParameter(f"Only one comparison allowed, got: {', '.join(flags)}")

    return provided[0]
