"""``qdo joins`` — discover likely join keys between tables."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Discover likely join keys between tables.")


@app.callback(invoke_without_command=True)
@friendly_errors
def joins(
    table: str = typer.Option(..., "--table", "-t", help="Source table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
    target: str | None = typer.Option(
        None, "--target",
        help="Target table (default: check all tables).",
    ),
) -> None:
    """Discover likely join keys between a source table and other tables.

    Uses column name matching and type compatibility to recommend join keys.

    Examples:

        qdo joins -c ./my.db -t orders                    # check all tables
        qdo joins -c ./my.db -t orders --target customers  # specific target
    """
    from querido.cli._pipeline import dispatch_output, table_command

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        with ctx.spin(f"Discovering joins for [bold]{ctx.table}[/bold]"):
            from querido.core.joins import discover_joins

            result = discover_joins(
                ctx.connector, ctx.table, target=target
            )

        dispatch_output("joins", result)
