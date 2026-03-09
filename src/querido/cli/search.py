from __future__ import annotations

import typer

app = typer.Typer(help="Search table and column metadata.")


@app.callback(invoke_without_command=True)
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
    """Search for tables and columns matching a pattern."""
    from querido.cli._util import friendly_errors

    @friendly_errors
    def _run() -> None:
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

            results = try_cached_search(connection, pattern, search_type)

        if results is None:
            with create_connector(config) as connector:
                from rich.console import Console

                from querido.core.search import search_metadata

                console = Console(stderr=True)
                from querido.cli._progress import query_status

                with query_status(console, f"Searching for [bold]{pattern}[/bold]", connector):
                    results = search_metadata(connector, pattern, search_type, schema)

        from querido.cli._util import get_output_format

        fmt = get_output_format()
        if fmt == "rich":
            from querido.output.console import print_search

            print_search(pattern, results)
        elif fmt == "html":
            from querido.cli._util import emit_html
            from querido.output.html import format_search_html

            emit_html(format_search_html(pattern, results))
        else:
            from querido.output.formats import format_search

            print(format_search(pattern, results, fmt))

    _run()
