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
) -> None:
    """Show column metadata and row count for a table."""
    from querido.config import resolve_connection
    from querido.connectors.base import validate_table_name
    from querido.connectors.factory import create_connector
    from querido.output.console import print_inspect
    from querido.sql.renderer import render_template

    validate_table_name(table)
    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        columns = connector.get_columns(table)
        count_sql = render_template("count", connector.dialect, table=table)
        rows = connector.execute(count_sql)
        row_count = rows[0]["cnt"]
        print_inspect(table, columns, row_count)
