import typer

app = typer.Typer(help="Inspect table structure.")


@app.callback(invoke_without_command=True)
def inspect(
    table: str = typer.Option(..., "--table", "-t", help="Table name to inspect."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show extended metadata (comments, descriptions)."
    ),
) -> None:
    """Show column metadata and row count for a table."""
    from querido.cli._errors import friendly_errors

    @friendly_errors
    def _run() -> None:
        from querido.cli._context import maybe_show_sql
        from querido.cli._errors import set_last_sql
        from querido.cli._pipeline import dispatch_output, table_command

        with table_command(table=table, connection=connection, db_type=db_type) as ctx:
            with ctx.spin(f"Inspecting [bold]{ctx.table}[/bold]"):
                from querido.core.inspect import get_inspect
                from querido.sql.renderer import render_template

                count_sql = render_template("count", ctx.connector.dialect, table=ctx.table)
                maybe_show_sql(count_sql)
                set_last_sql(count_sql)
                result = get_inspect(ctx.connector, ctx.table, verbose=verbose)

            dispatch_output(
                "inspect",
                ctx.table,
                result["columns"],
                result["row_count"],
                verbose=verbose,
                table_comment=result["table_comment"],
            )

    _run()
