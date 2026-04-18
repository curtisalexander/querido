"""``qdo context`` — rich table context for agents and humans."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Get rich context for a table: schema, stats, sample values, metadata.")


@app.callback(invoke_without_command=True)
@friendly_errors
def context(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
    sample_values: int = typer.Option(
        5,
        "--sample-values",
        "-s",
        help="Number of sample values per non-numeric column (0 to skip).",
    ),
    no_sample: bool = typer.Option(
        False,
        "--no-sample",
        help="Profile the full table without sampling (slower on large tables).",
    ),
    sample: int | None = typer.Option(
        None,
        "--sample",
        help="Override sample size (rows). Defaults to auto-sampling at >1M rows.",
    ),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Use exact COUNT(DISTINCT) instead of approximations (slower).",
    ),
) -> None:
    """Get rich context for a table: schema, stats, sample values, and metadata.

    This is the primary command for giving a coding agent everything it needs
    to write accurate SQL for a table. Output includes column types, null rates,
    distinct counts, min/max values, and a representative sample of values for
    categorical columns.

    On DuckDB and Snowflake, all information is gathered in a single table scan
    using approx_top_k. On SQLite, one profile scan plus per-column frequency
    queries are used.

    Stored metadata (from ``qdo metadata init``) is automatically merged in,
    adding business descriptions, valid values, and PII flags.

    \b
    Examples:
        qdo context -c ./my.duckdb -t orders
        qdo context -c ./my.duckdb -t orders --sample-values 10
        qdo context -c ./my.duckdb -t orders --no-sample
        qdo --format json context -c mydb -t orders
    """
    from querido.cli._context import maybe_show_sql
    from querido.cli._errors import set_last_sql
    from querido.cli._pipeline import dispatch_output, table_command

    with (
        table_command(table=table, connection=connection, db_type=db_type) as ctx,
        ctx.spin(f"Loading context for [bold]{ctx.table}[/bold]"),
    ):
        from querido.core.context import get_context

        result = get_context(
            ctx.connector,
            ctx.table,
            connection,
            sample_values=sample_values,
            no_sample=no_sample,
            sample=sample,
            exact=exact,
        )

    rendered_sql = result.get("sql") or ""
    if rendered_sql:
        maybe_show_sql(rendered_sql)
        set_last_sql(rendered_sql)

    from querido.output.envelope import emit_envelope, is_structured_format

    if is_structured_format():
        from querido.core.next_steps import for_context

        emit_envelope(
            command="context",
            data=result,
            next_steps=for_context(result, connection=connection, table=result.get("table", "")),
            connection=connection,
            table=result.get("table"),
        )
        return

    dispatch_output("context", result)
