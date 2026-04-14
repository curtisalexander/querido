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
    pattern: str | None = typer.Option(
        None,
        "--pattern",
        "-p",
        help="Filter by name pattern (substring match; searches table and column names).",
    ),
    schema: str | None = typer.Option(None, "--schema", help="Schema filter (Snowflake only)."),
    enrich: bool = typer.Option(
        False,
        "--enrich",
        help="Merge stored metadata (descriptions, owner) into output.",
    ),
) -> None:
    """Show the full catalog for a database — all tables, columns, and row counts.

    Cache-first by default: uses cached metadata if fresh, falls back to live
    queries. Use --live to always query the database directly.

    Use --pattern to search for tables or columns by name (replaces the
    former ``search`` command). Use --enrich to merge business context from
    stored metadata files (.qdo/metadata/) into the catalog output.
    """
    from querido.cli._pipeline import database_command, dispatch_output

    # Try cache first (unless --live)
    result = None
    if not live:
        from querido.core.catalog import get_catalog_cached

        result = get_catalog_cached(connection, tables_only=tables_only)

    if result is None:
        with database_command(connection=connection, db_type=db_type) as ctx:
            from querido.core.catalog import get_catalog

            with ctx.spin("Loading catalog"):
                result = get_catalog(ctx.connector, tables_only=tables_only, schema=schema)

    if enrich and result:
        from querido.core.catalog import enrich_catalog

        result = enrich_catalog(result, connection)

    if pattern and result:
        from querido.core.catalog import filter_catalog

        result = filter_catalog(result, pattern)

    from querido.cli._context import get_output_format

    if get_output_format() == "json":
        from querido.core.next_steps import for_catalog
        from querido.output.envelope import emit_envelope

        emit_envelope(
            command="catalog",
            data=result,
            next_steps=for_catalog(result or {}, connection=connection, enriched=enrich),
            connection=connection,
        )
        return

    dispatch_output("catalog", result)
