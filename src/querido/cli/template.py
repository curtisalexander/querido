import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Generate documentation templates for tables.")


@app.callback(invoke_without_command=True)
@friendly_errors
def template(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    sample_values: int = typer.Option(
        25,
        "--sample-values",
        min=0,
        max=100,
        help="Distinct sample values per column (0 to skip). Snowflake recommends 25+.",
    ),
    style: str = typer.Option(
        "table",
        "--style",
        help="Markdown style: 'table' (flat table) or 'detailed' (per-column sections).",
    ),
    db_type: str | None = typer.Option(
        None,
        "--db-type",
        help="Database type (sqlite/duckdb/snowflake). Inferred from path if omitted.",
    ),
) -> None:
    """Generate a documentation template for a table.

    Auto-populates column metadata (name, type, nullable, distinct count,
    min/max, sample values) and leaves placeholders for business definitions,
    data owner, and notes.
    """
    from querido.cli._pipeline import dispatch_output, table_command

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        from querido.core.template import (
            assemble_template,
            get_columns_and_count,
            get_profile_stats,
            get_sample_rows,
        )

        with ctx.spin(f"Fetching column metadata for [bold]{ctx.table}[/bold]"):
            columns, table_comment, row_count, col_info = get_columns_and_count(
                ctx.connector, ctx.table
            )

        if ctx.console.is_terminal:
            ctx.console.print(
                f"  Found [bold]{len(columns)}[/bold] columns, [bold]{row_count:,}[/bold] rows",
                highlight=False,
            )

        with ctx.spin(f"Profiling [bold]{len(col_info)}[/bold] columns"):
            profile_data = get_profile_stats(ctx.connector, ctx.table, col_info, row_count)

        if sample_values > 0:
            with ctx.spin(f"Fetching [bold]{sample_values}[/bold] sample values"):
                sample_rows = get_sample_rows(ctx.connector, ctx.table, sample_values)
        else:
            sample_rows = []

        template_result = assemble_template(
            columns, ctx.table, table_comment, row_count, profile_data, sample_rows
        )

        dispatch_output("template", template_result, style=style)
