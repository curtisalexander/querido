"""``qdo explain`` — show query execution plan."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Show query execution plan (EXPLAIN).")


@app.callback(invoke_without_command=True)
@friendly_errors
def explain(
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    sql: str | None = typer.Option(None, "--sql", "-s", help="SQL query to explain."),
    file: str | None = typer.Option(None, "--file", "-F", help="Path to a .sql file."),
    db_type: str | None = typer.Option(
        None,
        "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
    analyze: bool = typer.Option(
        False,
        "--analyze",
        help="Run EXPLAIN ANALYZE for actual execution stats (DuckDB).",
    ),
) -> None:
    """Show the query execution plan.

    SQL can be provided via --sql, --file, or stdin:

        qdo explain -c ./my.db --sql "select * from users where age > 30"
        qdo explain -c ./my.db --file query.sql --analyze
    """
    import sys

    from querido.cli._context import maybe_show_sql
    from querido.cli._errors import set_last_sql
    from querido.cli._options import resolve_sql
    from querido.cli._pipeline import dispatch_output
    from querido.config import resolve_connection
    from querido.connectors.factory import create_connector

    query_sql = resolve_sql(sql, file, sys.stdin)
    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        from rich.console import Console

        from querido.cli._progress import query_status

        maybe_show_sql(query_sql)
        set_last_sql(query_sql)

        console = Console(stderr=True)
        with query_status(console, "Getting query plan", connector):
            from querido.core.explain import get_explain

            result = get_explain(connector, query_sql, analyze=analyze)

        dispatch_output("explain", result)
