import typer

app = typer.Typer(help="Generate documentation templates for tables.")


@app.callback(invoke_without_command=True)
def template(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    sample_values: int = typer.Option(
        3, "--sample-values", min=0, max=10, help="Number of sample values per column (0 to skip)."
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
    from querido.cli._util import (
        check_table_exists,
        friendly_errors,
    )

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

            with query_status(console, f"Generating template for [bold]{table}[/bold]", connector):
                from querido.core.template import get_template

                template_result = get_template(connector, table, sample_values=sample_values)

            from querido.cli._util import get_output_format

            fmt = get_output_format()
            if fmt == "rich":
                from querido.output.console import print_template

                print_template(template_result)
            elif fmt == "html":
                from querido.cli._util import emit_html
                from querido.output.html import format_template_html

                emit_html(format_template_html(template_result))
            else:
                from querido.output.formats import format_template

                print(format_template(template_result, fmt))

    _run()
