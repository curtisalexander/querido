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
                sql_def = connector.get_view_definition(view)

            if sql_def is None:
                raise typer.BadParameter(
                    f"'{view}' is not a view or does not exist. "
                    "Use `qdo search` to find available views."
                )

            maybe_show_sql(sql_def)

            fmt = get_output_format()
            result = {
                "view": view,
                "dialect": connector.dialect,
                "definition": sql_def,
            }

            if fmt == "rich":
                from querido.output.console import print_lineage

                print_lineage(result)
            else:
                from querido.output.formats import format_lineage

                print(format_lineage(result, fmt))

    _run()
