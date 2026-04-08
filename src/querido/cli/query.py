"""``qdo query`` — execute ad-hoc SQL against a connection."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Execute ad-hoc SQL queries.")


@app.callback(invoke_without_command=True)
@friendly_errors
def query(
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    sql: str | None = typer.Option(None, "--sql", "-s", help="SQL query string."),
    file: str | None = typer.Option(None, "--file", "-F", help="Path to a .sql file to execute."),
    limit: int = typer.Option(
        1000, "--limit", "-l", min=0, help="Max rows to return (0 = no limit)."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
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
        with query_status(console, "Executing query", connector):
            from querido.core.query import run_query

            result = run_query(connector, query_sql, limit=limit)

        dispatch_output(
            "query",
            result.get("columns", []),
            result.get("rows", []),
            result.get("row_count", 0),
            limited=result.get("limited", False),
            sql=query_sql,
        )
