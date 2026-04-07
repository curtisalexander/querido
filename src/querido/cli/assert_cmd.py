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
    file: str | None = typer.Option(
        None, "--file", "-F", help="Path to a .sql file."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
    expect: float | None = typer.Option(
        None, "--expect", help="Assert result equals this value."
    ),
    expect_gt: float | None = typer.Option(
        None, "--expect-gt", help="Assert result > value."
    ),
    expect_lt: float | None = typer.Option(
        None, "--expect-lt", help="Assert result < value."
    ),
    expect_gte: float | None = typer.Option(
        None, "--expect-gte", help="Assert result >= value."
    ),
    expect_lte: float | None = typer.Option(
        None, "--expect-lte", help="Assert result <= value."
    ),
    name: str | None = typer.Option(
        None, "--name", "-n", help="Descriptive name for the assertion."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="No output, just exit code."
    ),
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
    from querido.config import resolve_connection
    from querido.connectors.factory import create_connector

    query_sql = _resolve_sql(sql, file, sys.stdin)
    operator, expected = _resolve_operator(
        expect, expect_gt, expect_lt, expect_gte, expect_lte
    )

    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        from rich.console import Console

        from querido.cli._progress import query_status

        maybe_show_sql(query_sql)
        set_last_sql(query_sql)

        console = Console(stderr=True)
        with query_status(console, "Running assertion", connector):
            from querido.core.assert_check import run_assertion

            result = run_assertion(
                connector,
                query_sql,
                operator=operator,
                expected=expected,
                name=name,
            )

    if not quiet:
        from querido.cli._pipeline import dispatch_output

        dispatch_output("assert_check", result)

    if not result["passed"]:
        raise typer.Exit(code=1)


def _resolve_sql(
    sql_option: str | None,
    file_option: str | None,
    stdin: object,
) -> str:
    """Resolve SQL from --sql, --file, or stdin."""
    if sql_option is not None:
        return sql_option

    if file_option is not None:
        from pathlib import Path

        path = Path(file_option)
        if not path.exists():
            raise typer.BadParameter(f"SQL file not found: {file_option}")
        return path.read_text().strip()

    if hasattr(stdin, "isatty") and not stdin.isatty():
        text = stdin.read().strip()
        if text:
            return text

    raise typer.BadParameter(
        "No SQL provided. Use --sql, --file, or pipe SQL via stdin."
    )


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
            "Must provide one of: --expect, --expect-gt, "
            "--expect-lt, --expect-gte, --expect-lte"
        )
    if len(provided) > 1:
        flags = [f"--expect-{op}" if op != "eq" else "--expect"
                 for op, _ in provided]
        raise typer.BadParameter(
            f"Only one comparison allowed, got: {', '.join(flags)}"
        )

    return provided[0]
