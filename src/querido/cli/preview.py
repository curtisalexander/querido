import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Preview rows from a table.")


@app.callback(invoke_without_command=True)
@friendly_errors
def preview(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    rows: int = typer.Option(20, "--rows", "-r", min=1, help="Number of rows to display."),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
) -> None:
    """Show a preview of rows from a table."""
    from querido.cli._context import get_output_format, maybe_show_sql
    from querido.cli._errors import set_last_sql
    from querido.cli._pipeline import dispatch_output, table_command

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        with ctx.spin(f"Loading preview of [bold]{ctx.table}[/bold]"):
            from querido.core.preview import get_preview
            from querido.sql.renderer import render_template

            sql = render_template("preview", ctx.connector.dialect, table=ctx.table, limit=rows)
            maybe_show_sql(sql)
            set_last_sql(sql)
            data = get_preview(ctx.connector, ctx.table, limit=rows)

        if get_output_format() == "json":
            from querido.core.next_steps import for_preview
            from querido.output.envelope import emit_envelope

            emit_envelope(
                command="preview",
                data={
                    "table": ctx.table,
                    "limit": rows,
                    "row_count": len(data),
                    "rows": data,
                },
                next_steps=for_preview(data, connection=connection, table=ctx.table, limit=rows),
                connection=connection,
                table=ctx.table,
            )
            return

        dispatch_output("preview", ctx.table, data, rows)
