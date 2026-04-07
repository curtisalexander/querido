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
    file: str | None = typer.Option(
        None, "--file", "-F", help="Path to a .sql file to execute."
    ),
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
    from querido.cli._pipeline import dispatch_output
    from querido.config import resolve_connection
    from querido.connectors.factory import create_connector

    query_sql = _resolve_sql(sql, file, sys.stdin)
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
            result["columns"],
            result["rows"],
            result["row_count"],
            limited=result["limited"],
            sql=query_sql,
        )


def _resolve_sql(
    sql_option: str | None,
    file_option: str | None,
    stdin: object,
) -> str:
    """Resolve the SQL string from --sql, --file, or stdin.

    Priority: --sql > --file > stdin.
    """
    if sql_option is not None:
        return sql_option

    if file_option is not None:
        from pathlib import Path

        path = Path(file_option)
        if not path.exists():
            raise typer.BadParameter(f"SQL file not found: {file_option}")
        return path.read_text().strip()

    # Try stdin — only if it's not a tty (i.e. something is piped in)
    if hasattr(stdin, "isatty") and not stdin.isatty():
        text = stdin.read().strip()
        if text:
            return text

    raise typer.BadParameter(
        "No SQL provided. Use --sql, --file, or pipe SQL via stdin."
    )
