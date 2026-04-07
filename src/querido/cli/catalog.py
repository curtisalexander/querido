"""``qdo catalog`` — full database catalog in one call."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Show full database catalog (tables, columns, row counts).")


@app.callback(invoke_without_command=True)
@friendly_errors
def catalog(
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
    tables_only: bool = typer.Option(
        False, "--tables-only", help="List tables only (skip columns and row counts)."
    ),
    live: bool = typer.Option(
        False, "--live", help="Bypass cache and query the database directly."
    ),
    schema: str | None = typer.Option(None, "--schema", help="Schema filter (Snowflake only)."),
) -> None:
    """Show the full catalog for a database — all tables, columns, and row counts.

    Cache-first by default: uses cached metadata if fresh, falls back to live
    queries. Use --live to always query the database directly.
    """
    from querido.cli._pipeline import dispatch_output
    from querido.config import resolve_connection
    from querido.connectors.factory import create_connector

    # Try cache first (unless --live)
    result = None
    if not live:
        from querido.core.catalog import get_catalog_cached

        result = get_catalog_cached(connection, tables_only=tables_only)

    if result is None:
        config = resolve_connection(connection, db_type)
        with create_connector(config) as connector:
            from rich.console import Console

            from querido.cli._progress import query_status
            from querido.core.catalog import get_catalog

            console = Console(stderr=True)
            with query_status(console, "Loading catalog", connector):
                result = get_catalog(
                    connector, tables_only=tables_only, schema=schema
                )

    dispatch_output("catalog", result)
