import typer

app = typer.Typer(help="View definition and simple lineage.")


@app.callback(invoke_without_command=True)
def lineage(
    view: str = typer.Option(..., "--view", "-v", help="View name to retrieve definition for."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
) -> None:
    """Retrieve the SQL definition of a view."""
    from querido.cli._errors import friendly_errors

    @friendly_errors
    def _run() -> None:
        from querido.cli._context import maybe_show_sql
        from querido.cli._pipeline import dispatch_output, table_command

        with table_command(table=view, connection=connection, db_type=db_type) as ctx:
            with ctx.spin(f"Retrieving definition for [bold]{ctx.table}[/bold]"):
                from querido.core.lineage import get_view_definition

                try:
                    result = get_view_definition(ctx.connector, ctx.table)
                except LookupError as exc:
                    raise typer.BadParameter(str(exc)) from exc

            maybe_show_sql(result["definition"])
            dispatch_output("lineage", result)

    _run()
