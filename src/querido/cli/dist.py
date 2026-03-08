import typer

app = typer.Typer(help="Column distribution visualization.")


@app.callback(invoke_without_command=True)
def dist(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    column: str = typer.Option(..., "--column", "-col", help="Column name to visualize."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    buckets: int = typer.Option(
        20, "--buckets", "-b", min=2, max=100, help="Number of buckets for numeric histograms."
    ),
    top: int = typer.Option(
        20, "--top", min=1, help="Number of top values for categorical columns."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
) -> None:
    """Visualize distribution of a column's values."""
    from querido.cli._util import (
        check_table_exists,
        friendly_errors,
    )

    @friendly_errors
    def _run() -> None:
        from querido.cli._util import (
            get_output_format,
            maybe_show_sql,
            resolve_column,
            set_last_sql,
        )
        from querido.config import resolve_connection
        from querido.connectors.base import validate_column_name, validate_table_name
        from querido.connectors.factory import create_connector

        validate_table_name(table)
        validate_column_name(column)
        config = resolve_connection(connection, db_type)

        with create_connector(config) as connector:
            from rich.console import Console

            console = Console(stderr=True)

            check_table_exists(connector, table)
            canonical_col = resolve_column(connector, table, column)

            with console.status(f"Computing distribution for [bold]{canonical_col}[/bold]…"):
                from querido.core.dist import get_distribution
                from querido.sql.renderer import render_template

                null_sql = render_template(
                    "null_count", connector.dialect, column=canonical_col, table=table
                )
                maybe_show_sql(null_sql)
                set_last_sql(null_sql)

                dist_result = get_distribution(
                    connector, table, canonical_col, buckets=buckets, top=top
                )

            fmt = get_output_format()
            if fmt == "rich":
                from querido.output.console import print_dist

                print_dist(dist_result)
            elif fmt == "html":
                from querido.cli._util import emit_html
                from querido.output.html import format_dist_html

                emit_html(format_dist_html(dist_result))
            else:
                from querido.output.formats import format_dist

                print(format_dist(dist_result, fmt))

    _run()
