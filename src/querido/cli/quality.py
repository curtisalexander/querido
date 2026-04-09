"""``qdo quality`` — data quality summary for a table."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Data quality summary for a table.")


@app.callback(invoke_without_command=True)
@friendly_errors
def quality(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None,
        "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
    columns: str | None = typer.Option(
        None,
        "--columns",
        help="Comma-separated column names to check (default: all).",
    ),
    check_duplicates: bool = typer.Option(
        False,
        "--check-duplicates",
        help="Check for fully duplicate rows (can be slow).",
    ),
    sample: int | None = typer.Option(
        None,
        "--sample",
        "-s",
        min=1,
        help="Sample size (rows). Default: auto-sample at >1M rows.",
    ),
    no_sample: bool = typer.Option(
        False,
        "--no-sample",
        help="Force full table scan — exact results, slower on large tables.",
    ),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Use exact COUNT(DISTINCT) instead of approximate counts.",
    ),
) -> None:
    """Show data quality summary — nulls, uniqueness, issues per column.

    Each column gets a status: ok, warn, or fail based on null rates
    and uniqueness thresholds.

    By default, tables over 1M rows are automatically sampled for speed.
    Distinct counts use approximate algorithms on DuckDB and Snowflake.
    Use --no-sample and --exact for precise results on large tables.
    """
    from querido.cli._options import parse_column_list
    from querido.cli._pipeline import dispatch_output, table_command

    col_list = parse_column_list(columns)

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        with ctx.spin(f"Checking quality of [bold]{ctx.table}[/bold]"):
            from querido.core.quality import get_quality

            result = get_quality(
                ctx.connector,
                ctx.table,
                columns=col_list,
                check_duplicates=check_duplicates,
                sample=sample,
                no_sample=no_sample,
                exact=exact,
            )

        dispatch_output("quality", result)
