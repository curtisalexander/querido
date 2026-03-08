import typer

app = typer.Typer(help="Profile table data.")


@app.callback(invoke_without_command=True)
def profile(
    table: str = typer.Option(..., "--table", "-t", help="Table name to profile."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    columns: str | None = typer.Option(
        None, "--columns", help="Comma-separated column names to profile."
    ),
    sample: int | None = typer.Option(
        None,
        "--sample",
        "-s",
        min=1,
        help="Sample size (number of rows). Default: auto-sample at >1M rows.",
    ),
    no_sample: bool = typer.Option(
        False, "--no-sample", help="Force full table scan, no sampling."
    ),
    top: int = typer.Option(0, "--top", min=0, help="Show top N most frequent values per column."),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
) -> None:
    """Statistical profile of table columns."""
    from querido.cli._util import is_numeric_type, maybe_show_sql
    from querido.config import resolve_connection
    from querido.connectors.base import validate_column_name, validate_table_name
    from querido.connectors.factory import create_connector
    from querido.output.console import print_frequencies, print_profile
    from querido.sql.renderer import render_template

    validate_table_name(table)
    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        from rich.console import Console

        console = Console(stderr=True)

        col_meta = connector.get_columns(table)

        if columns:
            filter_names = {c.strip() for c in columns.split(",")}
            col_meta = [c for c in col_meta if c["name"] in filter_names]
            if not col_meta:
                raise typer.BadParameter(f"No matching columns found in '{table}'.")

        col_info = [
            {
                "name": validate_column_name(c["name"]),
                "type": c["type"],
                "numeric": is_numeric_type(c["type"]),
            }
            for c in col_meta
        ]

        # Determine source expression (table or sampled subquery)
        count_sql = render_template("count", connector.dialect, table=table)
        maybe_show_sql(count_sql)
        row_count_result = connector.execute(count_sql)
        row_count = row_count_result[0]["cnt"]

        source = table
        sampled = False
        sample_size = None

        if not no_sample:
            auto_threshold = 1_000_000
            if sample is not None:
                sample_size = sample
            elif row_count > auto_threshold:
                sample_size = 100_000

            if sample_size is not None and sample_size < row_count:
                source = render_template(
                    "sample",
                    connector.dialect,
                    table=table,
                    sample_size=sample_size,
                ).strip()
                sampled = True

        sql = render_template("profile", connector.dialect, columns=col_info, source=source)
        maybe_show_sql(sql)

        with console.status(f"Profiling [bold]{table}[/bold]…"):
            data = connector.execute(sql)

        from querido.cli._util import get_output_format

        fmt = get_output_format()

        if fmt == "rich":
            print_profile(table, data, row_count, sampled, sample_size)
        else:
            from querido.output.formats import format_profile

            print(format_profile(table, data, row_count, sampled, sample_size, fmt))

        if top > 0:
            freq_data: dict[str, list[dict]] = {}
            with console.status(f"Computing top {top} values…"):
                for col in col_info:
                    col_name = str(col["name"])
                    freq_sql = render_template(
                        "frequency",
                        connector.dialect,
                        column=col_name,
                        source=source,
                        top=top,
                    )
                    maybe_show_sql(freq_sql)
                    freq_data[col_name] = connector.execute(freq_sql)

            if fmt == "rich":
                print_frequencies(table, freq_data, row_count)
            else:
                from querido.output.formats import format_frequencies

                print(format_frequencies(table, freq_data, row_count, fmt))
