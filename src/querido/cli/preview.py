import typer

app = typer.Typer(help="Preview rows from a table.")


@app.callback(invoke_without_command=True)
def preview(
    table: str = typer.Option(..., "--table", "-t", help="Table name to preview."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    rows: int = typer.Option(20, "--rows", "-r", min=1, help="Number of rows to display."),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
) -> None:
    """Show a preview of rows from a table."""
    from querido.cli._util import maybe_show_sql
    from querido.config import resolve_connection
    from querido.connectors.base import validate_table_name
    from querido.connectors.factory import create_connector
    from querido.output.console import print_preview
    from querido.sql.renderer import render_template

    validate_table_name(table)
    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        from rich.console import Console

        console = Console(stderr=True)
        with console.status(f"Loading preview of [bold]{table}[/bold]…"):
            sql = render_template("preview", connector.dialect, table=table, limit=rows)
            maybe_show_sql(sql)
            data = connector.execute(sql)

        from querido.cli._util import get_output_format

        fmt = get_output_format()
        if fmt == "rich":
            print_preview(table, data, rows)
        else:
            from querido.output.formats import format_preview

            print(format_preview(table, data, rows, fmt))
