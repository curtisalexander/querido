import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Profile table data.")


@app.callback(invoke_without_command=True)
@friendly_errors
def profile(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    columns: str | None = typer.Option(
        None, "--columns", help="Comma-separated column names to profile."
    ),
    column_set: str | None = typer.Option(
        None, "--column-set", help="Use a saved column set (see: qdo config column-set list)."
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
    exact: bool = typer.Option(
        False,
        "--exact",
        help="Use exact COUNT(DISTINCT) instead of approximate counts (Snowflake only).",
    ),
    quick: bool | None = typer.Option(
        None,
        "--quick/--no-quick",
        help="Quick mode: only null counts and distinct counts (auto-engages at 50+ columns).",
    ),
    classify: bool = typer.Option(
        False,
        "--classify",
        help="Classify columns by category (implies --quick). Agent-friendly with --format json.",
    ),
    db_type: str | None = typer.Option(
        None,
        "--db-type",
        help="Database type (sqlite/duckdb/snowflake). Inferred from path if omitted.",
    ),
) -> None:
    """Statistical profile of table columns."""
    from querido.cli._context import maybe_show_sql
    from querido.cli._errors import set_last_sql
    from querido.cli._pipeline import dispatch_output, table_command

    if columns and column_set:
        raise typer.BadParameter("Cannot use both --columns and --column-set.")

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        # Resolve --column-set to a comma-separated column string.
        if column_set and not columns:
            from querido.config import load_column_set

            col_list = load_column_set(connection, ctx.table, column_set)
            if col_list is None:
                raise typer.BadParameter(
                    f"Column set '{column_set}' not found for {connection}.{ctx.table}. "
                    "Run: qdo config column-set list"
                )
            columns = ",".join(col_list)

        with ctx.spin(f"Profiling [bold]{ctx.table}[/bold]"):
            from querido.core.profile import get_profile
            from querido.sql.renderer import render_template

            count_sql = render_template("count", ctx.connector.dialect, table=ctx.table)
            maybe_show_sql(count_sql)
            set_last_sql(count_sql)

            # --classify implies --quick
            import os

            resolved_quick = quick
            if classify:
                resolved_quick = True
            if resolved_quick is None:
                quick_threshold = int(os.environ.get("QDO_QUICK_THRESHOLD", "50"))
                col_meta = ctx.connector.get_columns(ctx.table)
                if columns:
                    filter_names = {c.strip().lower() for c in columns.split(",") if c.strip()}
                    col_count = len(
                        [c for c in col_meta if c.get("name", "").lower() in filter_names]
                    )
                else:
                    col_count = len(col_meta)
                resolved_quick = col_count >= quick_threshold

            try:
                result = get_profile(
                    ctx.connector,
                    ctx.table,
                    columns=columns,
                    sample=sample,
                    no_sample=no_sample,
                    exact=exact,
                    quick=resolved_quick,
                )
            except ValueError as exc:
                raise typer.BadParameter(str(exc)) from exc

            profile_sql = render_template(
                "profile",
                ctx.connector.dialect,
                columns=result["col_info"],
                source=result["source"],
                approx=not exact,
                quick=resolved_quick,
            )
            maybe_show_sql(profile_sql)
            set_last_sql(profile_sql)

        if classify:
            from querido.core._utils import classify_columns

            classification = classify_columns(
                result["stats"], result["col_info"], result["row_count"]
            )
            dispatch_output(
                "classify",
                ctx.table,
                classification,
                result["stats"],
                result["row_count"],
                result["sampled"],
                result["sample_size"],
            )
        else:
            dispatch_output(
                "profile",
                ctx.table,
                result["stats"],
                result["row_count"],
                result["sampled"],
                result["sample_size"],
            )

        if top > 0:
            with ctx.spin(f"Computing top {top} values"):
                from querido.core.profile import get_frequencies

                freq_data = get_frequencies(
                    ctx.connector,
                    result["source"],
                    result["col_info"],
                    top,
                )

            dispatch_output("frequencies", ctx.table, freq_data, result["row_count"])
