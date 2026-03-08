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
    from querido.cli._util import (
        check_table_exists,
        friendly_errors,
        maybe_show_sql,
        set_last_sql,
    )

    @friendly_errors
    def _run() -> None:
        from querido.config import resolve_connection
        from querido.connectors.base import validate_table_name
        from querido.connectors.factory import create_connector
        from querido.output.console import print_inspect
        from querido.sql.renderer import render_template

        validate_table_name(table)
        config = resolve_connection(connection, db_type)

        with create_connector(config) as connector:
            from rich.console import Console

            console = Console(stderr=True)

            check_table_exists(connector, table)

            with console.status(f"Inspecting [bold]{table}[/bold]…"):
                columns = connector.get_columns(table)
                count_sql = render_template("count", connector.dialect, table=table)
                maybe_show_sql(count_sql)
                set_last_sql(count_sql)
                rows = connector.execute(count_sql)
                row_count = rows[0]["cnt"]

                table_comment = None
                if verbose:
                    table_comment = connector.get_table_comment(table)

            from querido.cli._util import get_output_format

            fmt = get_output_format()
            if fmt == "rich":
                print_inspect(
                    table, columns, row_count, verbose=verbose, table_comment=table_comment
                )
            else:
                from querido.output.formats import format_inspect

                print(
                    format_inspect(
                        table,
                        columns,
                        row_count,
                        fmt,
                        verbose=verbose,
                        table_comment=table_comment,
                    )
                )

    _run()
