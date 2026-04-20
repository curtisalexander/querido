"""``qdo pivot`` — aggregate data with GROUP BY from the CLI."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Pivot / aggregate table data.")


@app.callback(invoke_without_command=True)
@friendly_errors
def pivot(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    group_by: str = typer.Option(
        ..., "--group-by", "-g", help="Comma-separated columns to group by."
    ),
    agg: str = typer.Option(
        ...,
        "--agg",
        "-a",
        help="Comma-separated aggregation expressions, e.g. sum(amount),count(id).",
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
    filter_expr: str | None = typer.Option(
        None, "--filter", "-w", help="SQL WHERE clause expression."
    ),
    order_by: str | None = typer.Option(
        None, "--order-by", "-o", help="SQL ORDER BY expression (default: group-by columns)."
    ),
    limit: int | None = typer.Option(None, "--limit", "-l", min=1, help="Maximum result rows."),
) -> None:
    """Aggregate data with GROUP BY.

    Examples:

        qdo pivot -c ./my.db -t orders -g status -a "sum(amount),count(id)"
        qdo pivot -c ./my.db -t orders -g region,status -a "avg(amount)" --filter "year = 2024"
    """
    from querido.cli._context import maybe_show_sql
    from querido.cli._errors import set_last_sql
    from querido.cli._pipeline import dispatch_output, table_command

    rows_list, values_list, agg_fn = _parse_agg_spec(group_by, agg)

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        with ctx.spin(f"Pivoting [bold]{ctx.table}[/bold]"):
            from querido.core.pivot import get_pivot

            result = get_pivot(
                ctx.connector,
                ctx.table,
                rows=rows_list,
                values=values_list,
                agg=agg_fn,
                filter_expr=filter_expr,
                order_by=order_by,
                limit=limit,
            )

        maybe_show_sql(result.get("sql", ""))
        set_last_sql(result.get("sql", ""))

        from querido.output.envelope import emit_envelope, is_structured_format

        if is_structured_format():
            from querido.core.next_steps import for_pivot

            emit_envelope(
                command="pivot",
                data=result,
                next_steps=for_pivot(result, connection=connection, table=ctx.table),
                connection=connection,
                table=ctx.table,
            )
            return

        dispatch_output("pivot", result)


def _parse_agg_spec(group_by: str, agg: str) -> tuple[list[str], list[str], str]:
    """Parse --group-by and --agg into (rows, values, agg_function).

    Supports explicit aggregation expressions like sum(amount), count(id).
    All expressions must use the same aggregation function.

    For now we require all agg expressions to use the same function.
    """
    import re

    from querido.cli._options import parse_column_list

    rows_list = parse_column_list(group_by)
    if not rows_list:
        raise typer.BadParameter("--group-by must specify at least one column.")

    agg_parts = parse_column_list(agg)
    if not agg_parts:
        raise typer.BadParameter("--agg must specify at least one aggregation.")

    # Try to parse func(col) patterns
    pattern = re.compile(r"^(\w+)\((\w+|\*)\)$")
    functions = set()
    columns = []
    for part in agg_parts:
        m = pattern.match(part)
        if m:
            functions.add(m.group(1).upper())
            columns.append(m.group(2))
        else:
            # Treat as bare function name — but need columns
            raise typer.BadParameter(
                f"Invalid aggregation expression: {part!r}. "
                "Use format: func(column), e.g. sum(amount), count(id), count(*)"
            )

    if len(functions) > 1:
        raise typer.BadParameter(
            f"All aggregations must use the same function. Found: {sorted(functions)}. "
            "Use qdo query for mixed aggregations."
        )

    agg_fn = functions.pop()

    # Handle count(*) — replace * with first group-by column for the pivot API
    values_list = []
    for col in columns:
        if col == "*":
            values_list.append(rows_list[0])
        else:
            values_list.append(col)

    return rows_list, values_list, agg_fn
