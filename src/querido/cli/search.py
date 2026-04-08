from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Search table and column metadata. (Tip: try catalog --pattern)")


@app.callback(invoke_without_command=True)
@friendly_errors
def search(
    pattern: str = typer.Option(
        ..., "--pattern", "-p", help="Search pattern (case-insensitive substring match)."
    ),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
    search_type: str = typer.Option(
        "all",
        "--type",
        help="What to search: table, column, or all.",
    ),
    schema: str | None = typer.Option(None, "--schema", help="Schema filter (Snowflake only)."),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Bypass cache and query the database directly."
    ),
) -> None:
    """Search for tables and columns matching a pattern.

    Note: consider using ``qdo catalog --pattern`` instead, which provides
    richer output including columns and row counts.
    """
    from querido.cli._pipeline import dispatch_output
    from querido.config import resolve_connection
    from querido.connectors.factory import create_connector

    valid_types = {"table", "column", "all"}
    if search_type not in valid_types:
        raise typer.BadParameter(f"--type must be one of: {', '.join(sorted(valid_types))}")

    config = resolve_connection(connection, db_type)

    # Try cache first (unless --no-cache)
    results = None
    if not no_cache:
        from querido.core.search import try_cached_search

        results = try_cached_search(connection, pattern, search_type, schema)

    if results is None:
        with create_connector(config) as connector:
            from rich.console import Console

            from querido.cli._progress import query_status
            from querido.core.search import search_metadata

            console = Console(stderr=True)
            with query_status(console, f"Searching for [bold]{pattern}[/bold]", connector):
                results = search_metadata(connector, pattern, search_type, schema)

    dispatch_output("search", pattern, results)
