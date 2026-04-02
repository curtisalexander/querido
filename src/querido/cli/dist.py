import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Column distribution visualization.")


@app.callback(invoke_without_command=True)
@friendly_errors
def dist(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    column: str = typer.Option(..., "--column", "-C", help="Column name to visualize."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    buckets: int = typer.Option(
        20, "--buckets", "-b", min=2, max=100, help="Number of buckets for numeric histograms."
    ),
    top: int = typer.Option(
        20, "--top", min=1, help="Number of top values for categorical columns."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
) -> None:
    """Visualize distribution of a column's values."""
    from querido.cli._pipeline import dispatch_output, table_command
    from querido.cli._validation import resolve_column
    from querido.connectors.base import validate_column_name

    validate_column_name(column)

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        canonical_col = resolve_column(ctx.connector, ctx.table, column)

        with ctx.spin(f"Computing distribution for [bold]{canonical_col}[/bold]"):
            from querido.core.dist import get_distribution

            dist_result = get_distribution(
                ctx.connector, ctx.table, canonical_col, buckets=buckets, top=top
            )

        dispatch_output("dist", dist_result)
