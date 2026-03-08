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

        validate_table_name(table)
        config = resolve_connection(connection, db_type)

        with create_connector(config) as connector:
            from rich.console import Console

            console = Console(stderr=True)

            check_table_exists(connector, table)

            with console.status(f"Profiling [bold]{table}[/bold]…"):
                from querido.core.profile import get_profile
                from querido.sql.renderer import render_template

                # Show SQL if requested
                count_sql = render_template("count", connector.dialect, table=table)
                maybe_show_sql(count_sql)
                set_last_sql(count_sql)

                try:
                    result = get_profile(
                        connector,
                        table,
                        columns=columns,
                        sample=sample,
                        no_sample=no_sample,
                    )
                except ValueError as exc:
                    raise typer.BadParameter(str(exc)) from exc

                # Show the profile SQL too
                profile_sql = render_template(
                    "profile",
                    connector.dialect,
                    columns=result["col_info"],
                    source=result["source"],
                )
                maybe_show_sql(profile_sql)
                set_last_sql(profile_sql)

            from querido.cli._util import get_output_format

            fmt = get_output_format()
            data = result["stats"]
            row_count = result["row_count"]
            sampled = result["sampled"]
            sample_size = result["sample_size"]

            if fmt == "rich":
                from querido.output.console import print_profile

                print_profile(table, data, row_count, sampled, sample_size)
            else:
                from querido.output.formats import format_profile

                print(format_profile(table, data, row_count, sampled, sample_size, fmt))

            if top > 0:
                with console.status(f"Computing top {top} values…"):
                    from querido.core.profile import get_frequencies

                    freq_data = get_frequencies(
                        connector,
                        result["source"],
                        result["col_info"],
                        top,
                    )

                if fmt == "rich":
                    from querido.output.console import print_frequencies

                    print_frequencies(table, freq_data, row_count)
                else:
                    from querido.output.formats import format_frequencies

                    print(format_frequencies(table, freq_data, row_count, fmt))

    _run()
