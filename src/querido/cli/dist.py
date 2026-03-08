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
        resolve_column,
    )

    @friendly_errors
    def _run() -> None:
        from querido.cli._util import (
            get_output_format,
            is_numeric_type,
            maybe_show_sql,
            set_last_sql,
        )
        from querido.config import resolve_connection
        from querido.connectors.base import validate_column_name, validate_table_name
        from querido.connectors.factory import create_connector
        from querido.sql.renderer import render_template

        validate_table_name(table)
        validate_column_name(column)
        config = resolve_connection(connection, db_type)

        with create_connector(config) as connector:
            from rich.console import Console

            console = Console(stderr=True)

            check_table_exists(connector, table)

            # Resolve column name using case-insensitive match
            canonical_col = resolve_column(connector, table, column)

            col_meta = connector.get_columns(table)
            col_match = [c for c in col_meta if c["name"] == canonical_col]
            col_type = col_match[0]["type"]
            is_num = is_numeric_type(col_type)

            # Count nulls
            null_sql = (
                f"SELECT COUNT(*) AS total, "
                f'SUM(CASE WHEN "{canonical_col}" IS NULL THEN 1 ELSE 0 END) AS null_count '
                f"FROM {table}"
            )
            maybe_show_sql(null_sql)
            set_last_sql(null_sql)
            null_result = connector.execute(null_sql)
            total_rows = null_result[0]["total"]
            null_count = null_result[0]["null_count"]

            fmt = get_output_format()

            if is_num:
                sql = render_template(
                    "dist", connector.dialect, column=canonical_col, source=table, buckets=buckets
                )
                maybe_show_sql(sql)
                set_last_sql(sql)
                with console.status(f"Computing distribution for [bold]{canonical_col}[/bold]…"):
                    data = connector.execute(sql)

                dist_result = {
                    "table": table,
                    "column": canonical_col,
                    "column_type": col_type,
                    "mode": "numeric",
                    "total_rows": total_rows,
                    "null_count": null_count,
                    "buckets": data,
                }

                if fmt == "rich":
                    from querido.output.console import print_dist_numeric

                    print_dist_numeric(dist_result)
                else:
                    from querido.output.formats import format_dist

                    print(format_dist(dist_result, fmt))
            else:
                # Categorical: use frequency query
                freq_sql = render_template(
                    "frequency",
                    connector.dialect,
                    column=canonical_col,
                    source=table,
                    top=top,
                )
                maybe_show_sql(freq_sql)
                set_last_sql(freq_sql)
                with console.status(f"Computing distribution for [bold]{canonical_col}[/bold]…"):
                    data = connector.execute(freq_sql)

                dist_result = {
                    "table": table,
                    "column": canonical_col,
                    "column_type": col_type,
                    "mode": "categorical",
                    "total_rows": total_rows,
                    "null_count": null_count,
                    "values": data,
                }

                if fmt == "rich":
                    from querido.output.console import print_dist_categorical

                    print_dist_categorical(dist_result)
                else:
                    from querido.output.formats import format_dist

                    print(format_dist(dist_result, fmt))

    _run()
