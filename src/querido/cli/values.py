"""``qdo values`` — enumerate distinct values for a column."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Show distinct values for a column.")


@app.callback(invoke_without_command=True)
@friendly_errors
def values(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    columns: str = typer.Option(
        ...,
        "--columns",
        "--column",
        "-C",
        help="Column to enumerate (exactly one). `--column` is an alias.",
    ),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
    max_values: int = typer.Option(
        1000, "--max", "-m", min=1, help="Maximum distinct values to return."
    ),
    sort: str = typer.Option(
        "value", "--sort", "-s", help="Sort order: value (alphabetical) or frequency (count desc)."
    ),
    write_metadata: bool = typer.Option(
        False,
        "--write-metadata",
        help=(
            "Write low-cardinality string results as candidate valid_values to "
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
    """Show all distinct values for a column.

    For low-cardinality columns, returns every distinct value. For
    high-cardinality columns (> --max), returns the top values by frequency.
    """
    from querido.cli._options import parse_column_list
    from querido.cli._pipeline import dispatch_output, table_command

    valid_sorts = {"value", "frequency"}
    if sort not in valid_sorts:
        raise typer.BadParameter(f"--sort must be one of: {', '.join(sorted(valid_sorts))}")
    if plan and not write_metadata:
        raise typer.BadParameter("--plan requires --write-metadata.")

    col_names = parse_column_list(columns) or []
    if len(col_names) != 1:
        raise typer.BadParameter(
            "--columns must name exactly one column for 'qdo values' "
            f"(got {len(col_names)}: {', '.join(col_names) or '(none)'})"
        )
    column = col_names[0]

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        from querido.cli._validation import resolve_column

        resolved_column = resolve_column(ctx.connector, ctx.table, column)

        with ctx.spin(f"Loading values for [bold]{ctx.table}.{resolved_column}[/bold]"):
            from querido.core.values import get_distinct_values

            result = get_distinct_values(
                ctx.connector,
                ctx.table,
                resolved_column,
                max_values=max_values,
                sort=sort,
                connection=connection,
            )

        metadata_write_summary = None
        if write_metadata:
            from querido.core.metadata_write import preview_from_values, write_from_values

            if plan:
                metadata_write_summary = preview_from_values(
                    ctx.connector, connection, ctx.table, result, force=force
                )
            else:
                metadata_write_summary = write_from_values(
                    ctx.connector, connection, ctx.table, result, force=force
                )

        from querido.output.envelope import emit_envelope, is_structured_format

        if is_structured_format():
            from querido.core.next_steps import for_values

            envelope_data: dict = dict(result)
            if metadata_write_summary is not None:
                envelope_data["metadata_write"] = metadata_write_summary

            emit_envelope(
                command="values",
                data=envelope_data,
                next_steps=for_values(result, connection=connection, table=ctx.table),
                connection=connection,
                table=ctx.table,
            )
            return

        dispatch_output("values", result)

        if metadata_write_summary is not None:
            import sys

            from querido.core.metadata_write import format_write_note

            print(format_write_note(metadata_write_summary), file=sys.stderr)
