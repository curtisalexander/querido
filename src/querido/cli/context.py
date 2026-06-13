"""``qdo context`` — rich table context for agents and humans."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors
from querido.cli._options import conn_opt, dbtype_opt, table_opt

app = typer.Typer(help="Get rich context for a table: schema, stats, sample values, metadata.")


@app.callback(invoke_without_command=True)
@friendly_errors
def context(
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
    sample_values: int = typer.Option(
        5,
        "--sample-values",
        help=(
            "Number of sample values per non-numeric column (0 to skip). "
            "context-only — profile and quality don't emit sample values."
        ),
    ),
    no_sample: bool = typer.Option(
        False,
        "--no-sample",
        help="Scan the full table — exact stats, slower on large tables.",
    ),
    sample: int | None = typer.Option(
        None,
        "--sample",
        "-s",
        help="Sample size (rows). Default: auto-sample at >1M rows.",
    ),
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Use exact COUNT(DISTINCT) instead of approximations (slower).",
    ),
    write_metadata: bool = typer.Option(
        False,
        "--write-metadata",
        help=(
            "Write deterministic inferences (valid_values, likely_sparse, temporal) to "
            ".qdo/metadata/<conn>/<table>.yaml. Human-authored fields "
            "(confidence 1.0) are preserved unless --force."
        ),
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="With --write-metadata: overwrite human-authored fields (confidence 1.0).",
    ),
    plan: bool = typer.Option(
        False,
        "--plan",
        help="With --write-metadata: preview metadata changes without writing the YAML.",
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
    from querido.cli._options import resolve_write_metadata
    from querido.cli._pipeline import dispatch_output, table_command

    if plan and not write_metadata:
        raise typer.BadParameter("--plan requires --write-metadata.")
    effective_write_metadata = resolve_write_metadata(write_metadata)

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        with ctx.spin(f"Loading context for [bold]{ctx.table}[/bold]"):
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

        metadata_write_summary = None
        if effective_write_metadata:
            from querido.core.metadata_write import preview_from_context, write_from_context

            if plan:
                metadata_write_summary = preview_from_context(
                    ctx.connector, connection, ctx.table, result, force=force
                )
            else:
                metadata_write_summary = write_from_context(
                    ctx.connector, connection, ctx.table, result, force=force
                )

        from querido.output.envelope import emit_envelope, is_structured_format

        if is_structured_format():
            from querido.core.next_steps import for_context

            envelope_data: dict = dict(result)
            if metadata_write_summary is not None:
                envelope_data["metadata_write"] = metadata_write_summary

            emit_envelope(
                command="context",
                data=envelope_data,
                next_steps=for_context(
                    result, connection=connection, table=result.get("table", "")
                ),
                connection=connection,
                table=result.get("table"),
            )
            return

        dispatch_output("context", result)

        import sys

        if metadata_write_summary is not None:
            from querido.core.metadata_write import format_write_note

            print(format_write_note(metadata_write_summary), file=sys.stderr)
        else:
            from querido.cli._pipeline import maybe_capture_hint

            maybe_capture_hint(
                "context", result, connection=connection, table=ctx.table, file=sys.stderr
            )
