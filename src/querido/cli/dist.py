import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Column distribution visualization.")


@app.callback(invoke_without_command=True)
@friendly_errors
def dist(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    columns: str = typer.Option(..., "--columns", "-C", help="Column to visualize (exactly one)."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    buckets: int = typer.Option(
        20, "--buckets", "-b", min=2, max=100, help="Number of buckets for numeric histograms."
    ),
    top: int = typer.Option(
        20, "--top", min=1, help="Number of top values for categorical columns."
    ),
    sample: int | None = typer.Option(
        None,
        "--sample",
        "-s",
        min=1,
        help="Sample size (number of rows). Default: auto-sample at >1M rows.",
    ),
    no_sample: bool = typer.Option(
        False, "--no-sample", help="Force full table scan, no sampling."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
) -> None:
    """Visualize distribution of a column's values."""
    from querido.cli._options import parse_column_list
    from querido.cli._pipeline import dispatch_output, table_command
    from querido.cli._validation import resolve_column
    from querido.connectors.base import validate_column_name

    col_names = parse_column_list(columns) or []
    if len(col_names) != 1:
        raise typer.BadParameter(
            "--columns must name exactly one column for 'qdo dist' "
            f"(got {len(col_names)}: {', '.join(col_names) or '(none)'})"
        )
    column = col_names[0]
    validate_column_name(column)

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        canonical_col = resolve_column(ctx.connector, ctx.table, column)

        with ctx.spin(f"Computing distribution for [bold]{canonical_col}[/bold]"):
            from querido.core.dist import get_distribution

            dist_result = get_distribution(
                ctx.connector,
                ctx.table,
                canonical_col,
                buckets=buckets,
                top=top,
                sample=sample,
                no_sample=no_sample,
            )

        from querido.output.envelope import emit_envelope, is_structured_format

        if is_structured_format():
            from querido.core.next_steps import for_dist

            emit_envelope(
                command="dist",
                data=dist_result,
                next_steps=for_dist(dist_result, connection=connection, table=ctx.table),
                connection=connection,
                table=ctx.table,
            )
            return

        dispatch_output("dist", dist_result)
