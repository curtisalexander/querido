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
    from querido.cli._util import friendly_errors

    @friendly_errors
    def _run() -> None:
        from querido.cli._util import get_output_format, maybe_show_sql
        from querido.config import resolve_connection
        from querido.connectors.base import validate_table_name
        from querido.connectors.factory import create_connector

        validate_table_name(view)
        config = resolve_connection(connection, db_type)

        with create_connector(config) as connector:
            from rich.console import Console

            console = Console(stderr=True)

            with console.status(f"Retrieving definition for [bold]{view}[/bold]…"):
                from querido.core.lineage import get_view_definition

                try:
                    result = get_view_definition(connector, view)
                except LookupError as exc:
                    raise typer.BadParameter(str(exc)) from exc

            maybe_show_sql(result["definition"])

            fmt = get_output_format()
            if fmt == "rich":
                from querido.output.console import print_lineage

                print_lineage(result)
            else:
                from querido.output.formats import format_lineage

                print(format_lineage(result, fmt))

    _run()
