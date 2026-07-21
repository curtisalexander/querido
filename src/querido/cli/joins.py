"""``qdo joins`` — discover likely join keys between tables."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors
from querido.cli._options import conn_opt, dbtype_opt

app = typer.Typer(help="Discover likely join keys between tables.")


@app.callback(invoke_without_command=True)
@friendly_errors
def joins(
    table: str = typer.Option(..., "--table", "-t", help="Source table name."),
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
    target: str | None = typer.Option(
        None,
        "--target",
        help="Target table (default: check all tables).",
    ),
) -> None:
    """Discover likely join keys between a source table and other tables.

    Uses column name matching and type compatibility to recommend join keys.

    Examples:

        qdo joins -c ./my.db -t orders                    # check all tables
        qdo joins -c ./my.db -t orders --target customers  # specific target
    """
    from querido.cli._pipeline import emit, table_command

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        with ctx.spin(f"Discovering joins for [bold]{ctx.table}[/bold]"):
            from querido.core.joins import discover_joins

            result = discover_joins(ctx.connector, ctx.table, target=target)

        from querido.core.next_steps import for_joins

        if emit(
            "joins",
            result,
            next_steps=lambda: for_joins(result, connection=connection, source_table=ctx.table),
            connection=connection,
            table=ctx.table,
        ):
            return
