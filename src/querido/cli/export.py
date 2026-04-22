"""``qdo export`` — export table or query results to a file."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Export data to a file (csv, tsv, json, jsonl).")


@app.callback(invoke_without_command=True)
@friendly_errors
def export(
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    table: str | None = typer.Option(None, "--table", "-t", help="Table to export."),
    sql: str | None = typer.Option(None, "--sql", "-s", help="SQL query to export."),
    from_step: str | None = typer.Option(
        None, "--from", help="Reuse SQL from a prior session step (<session>:<step>)."
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path."),
    export_format: str = typer.Option(
        "csv",
        "--export-format",
        "-e",
        help="Export format: csv, tsv, json, jsonl.",
    ),
    db_type: str | None = typer.Option(
        None,
        "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
    filter_expr: str | None = typer.Option(
        None, "--filter", "-w", help="SQL WHERE clause expression."
    ),
    limit: int | None = typer.Option(None, "--limit", "-l", min=1, help="Maximum rows to export."),
    columns: str | None = typer.Option(
        None,
        "--columns",
        help="Comma-separated column names to export.",
    ),
    clipboard: bool = typer.Option(
        False,
        "--clipboard",
        help="Copy TSV to clipboard (for pasting into Excel).",
    ),
    plan: bool = typer.Option(
        False,
        "--plan",
        help="Preview the export SQL and destination without executing it.",
    ),
    estimate: bool = typer.Option(
        False,
        "--estimate",
        help="Estimate export cost/shape without executing it.",
    ),
) -> None:
    """Export table or query results to a file or clipboard.

    Examples:

        qdo export -c ./my.db -t users -o users.csv
        qdo export -c ./my.db -t users -o data.tsv -e tsv
        qdo export -c ./my.db --sql "select * from users" -o out.json -e json
        qdo export -c ./my.db -t users --clipboard
    """
    import sys

    from querido.cli._pipeline import database_command, dispatch_output

    if plan and estimate:
        raise typer.BadParameter("Cannot use both --plan and --estimate.")

    valid_formats = {"csv", "tsv", "json", "jsonl"}
    if export_format not in valid_formats:
        raise typer.BadParameter(
            f"--export-format must be one of: {', '.join(sorted(valid_formats))}"
        )

    # Clipboard mode forces TSV and no output file
    if clipboard:
        export_format = "tsv"
        output = None

    from querido.cli._options import parse_column_list, resolve_export_sql

    col_list = parse_column_list(columns)
    table, sql, source = resolve_export_sql(
        table_option=table,
        sql_option=sql,
        from_option=from_step,
    )
    if not table and not sql:
        raise typer.BadParameter("Must provide --table, --sql, or --from.")

    source_meta: dict[str, object] = {}
    if source is not None:
        source_meta = {
            "source_session": source["session"],
            "source_step": source["step_index"],
            "source_command": source["source_command"],
        }
        source_connection = source.get("source_connection")
        if isinstance(source_connection, str):
            source_meta["source_connection"] = source_connection
            if source_connection != connection:
                typer.echo(
                    f"Warning: --from step was recorded against {source_connection!r}, "
                    f"running against {connection!r}.",
                    err=True,
                )

    if plan:
        from querido.core.export import build_export_query
        from querido.core.plan import build_export_plan
        from querido.output.envelope import cmd, emit_envelope, is_structured_format

        query_sql = build_export_query(
            table=table,
            sql=sql,
            limit=limit,
            filter_expr=filter_expr,
            columns=col_list,
        )
        destination = "file" if output else "clipboard" if clipboard else "stdout"
        payload = build_export_plan(
            sql=query_sql,
            fmt=export_format,
            destination=destination,
            output_path=output,
            clipboard=clipboard,
            table=table,
            columns=col_list,
            limit=limit,
            filter_expr=filter_expr,
        )

        run_cmd = ["qdo", "export", "-c", connection]
        if table:
            run_cmd += ["-t", table]
        if from_step:
            run_cmd += ["--from", from_step]
        elif sql:
            run_cmd += ["--sql", sql]
        if output:
            run_cmd += ["-o", output]
        if export_format != "csv":
            run_cmd += ["-e", export_format]
        if filter_expr:
            run_cmd += ["--filter", filter_expr]
        if limit is not None:
            run_cmd += ["--limit", str(limit)]
        if columns:
            run_cmd += ["--columns", columns]
        if clipboard:
            run_cmd.append("--clipboard")

        steps = [{"cmd": cmd(run_cmd), "why": "Run the planned export for real."}]
        if is_structured_format():
            emit_envelope(
                command="export",
                data=payload,
                next_steps=steps,
                connection=connection,
                extra_meta=source_meta or None,
            )
            return

        dispatch_output("plan", payload)
        return

    if estimate:
        from querido.core.estimate import estimate_export
        from querido.core.export import build_export_query
        from querido.output.envelope import cmd, emit_envelope, is_structured_format

        query_sql = build_export_query(
            table=table,
            sql=sql,
            limit=limit,
            filter_expr=filter_expr,
            columns=col_list,
        )
        destination = "file" if output else "clipboard" if clipboard else "stdout"
        with database_command(connection=connection, db_type=db_type) as ctx:
            payload = estimate_export(
                ctx.connector,
                sql=query_sql,
                table=table,
                fmt=export_format,
                destination=destination,
                output_path=output,
                clipboard=clipboard,
                columns=col_list,
                limit=limit,
                filter_expr=filter_expr,
            )

        run_cmd = ["qdo", "export", "-c", connection]
        if table:
            run_cmd += ["-t", table]
        if from_step:
            run_cmd += ["--from", from_step]
        elif sql:
            run_cmd += ["--sql", sql]
        if output:
            run_cmd += ["-o", output]
        if export_format != "csv":
            run_cmd += ["-e", export_format]
        if filter_expr:
            run_cmd += ["--filter", filter_expr]
        if limit is not None:
            run_cmd += ["--limit", str(limit)]
        if columns:
            run_cmd += ["--columns", columns]
        if clipboard:
            run_cmd.append("--clipboard")

        steps = [{"cmd": cmd(run_cmd), "why": "Run the estimated export for real."}]
        if is_structured_format():
            emit_envelope(
                command="export",
                data=payload,
                next_steps=steps,
                connection=connection,
                extra_meta=source_meta or None,
            )
            return

        dispatch_output("estimate", payload)
        return

    with database_command(connection=connection, db_type=db_type) as ctx:
        from querido.core.export import export_data

        with ctx.spin("Exporting data"):
            result = export_data(
                ctx.connector,
                table=table,
                sql=sql,
                output_path=output,
                fmt=export_format,
                limit=limit,
                filter_expr=filter_expr,
                columns=col_list,
            )

        if clipboard:
            from querido.core.export import copy_to_clipboard

            content = result.get("content", "")
            copy_to_clipboard(content)
            ctx.console.print(
                f"[green]Copied {result.get('rows', 0):,} rows to clipboard (TSV)[/green]",
            )
        elif output:
            ctx.console.print(
                f"[green]Exported {result.get('rows', 0):,} rows to {output}"
                f" ({result.get('size_bytes', 0):,} bytes)[/green]",
            )
        else:
            # No output file and no clipboard — print to stdout
            content = result.get("content", "")
            if content:
                print(content, end="", file=sys.stdout)
