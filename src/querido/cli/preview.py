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
    from querido.cli._util import check_table_exists, friendly_errors, maybe_show_sql, set_last_sql

    @friendly_errors
    def _run() -> None:
        from querido.config import resolve_connection
        from querido.connectors.base import validate_table_name
        from querido.connectors.factory import create_connector

        validate_table_name(table)
        config = resolve_connection(connection, db_type)

        with create_connector(config) as connector:
            from rich.console import Console

            console = Console(stderr=True)

            check_table_exists(connector, table)

            from querido.cli._progress import query_status

            with query_status(console, f"Loading preview of [bold]{table}[/bold]", connector):
                from querido.core.preview import get_preview
                from querido.sql.renderer import render_template

                sql = render_template("preview", connector.dialect, table=table, limit=rows)
                maybe_show_sql(sql)
                set_last_sql(sql)

                data = get_preview(connector, table, limit=rows)

            from querido.cli._util import get_output_format

            fmt = get_output_format()
            if fmt == "rich":
                from querido.output.console import print_preview

                print_preview(table, data, rows)
            elif fmt == "html":
                from querido.cli._util import emit_html
                from querido.output.html import format_preview_html

                emit_html(format_preview_html(table, data, rows))
            else:
                from querido.output.formats import format_preview

                print(format_preview(table, data, rows, fmt))

    _run()
