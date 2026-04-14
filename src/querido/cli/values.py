"""``qdo values`` — enumerate distinct values for a column."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Show distinct values for a column.")


@app.callback(invoke_without_command=True)
@friendly_errors
def values(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    column: str = typer.Option(..., "--column", "-C", help="Column to enumerate."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
    max_values: int = typer.Option(
        1000, "--max", "-m", min=1, help="Maximum distinct values to return."
    ),
    sort: str = typer.Option(
        "value", "--sort", "-s", help="Sort order: value (alphabetical) or frequency (count desc)."
    ),
) -> None:
    """Show all distinct values for a column.

    For low-cardinality columns, returns every distinct value. For
    high-cardinality columns (> --max), returns the top values by frequency.
    """
    from querido.cli._pipeline import dispatch_output, table_command

    valid_sorts = {"value", "frequency"}
    if sort not in valid_sorts:
        raise typer.BadParameter(f"--sort must be one of: {', '.join(sorted(valid_sorts))}")

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        from querido.cli._validation import resolve_column

        resolved_column = resolve_column(ctx.connector, ctx.table, column)

        with ctx.spin(f"Loading values for [bold]{ctx.table}.{resolved_column}[/bold]"):
            from querido.core.values import get_distinct_values

            result = get_distinct_values(
                ctx.connector,
                ctx.table,
                resolved_column,
                max_values=max_values,
                sort=sort,
            )

        from querido.cli._context import get_output_format

        if get_output_format() == "json":
            from querido.core.next_steps import for_values
            from querido.output.envelope import emit_envelope

            emit_envelope(
                command="values",
                data=result,
                next_steps=for_values(result, connection=connection, table=ctx.table),
                connection=connection,
                table=ctx.table,
            )
            return

        dispatch_output("values", result)
