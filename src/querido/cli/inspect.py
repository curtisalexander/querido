import typer

from querido.cli._errors import friendly_errors
from querido.cli._options import conn_opt, dbtype_opt, table_opt

app = typer.Typer(help="Inspect table structure.")


@app.callback(invoke_without_command=True)
@friendly_errors
def inspect(
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show extended metadata (comments, descriptions)."
    ),
) -> None:
    """Show column metadata and row count for a table."""
    from querido.cli._context import maybe_show_sql
    from querido.cli._errors import set_last_sql
    from querido.cli._pipeline import emit, table_command

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        with ctx.spin(f"Inspecting [bold]{ctx.table}[/bold]"):
            from querido.core.inspect import get_inspect
            from querido.sql.renderer import render_template

            count_sql = render_template("count", ctx.connector.dialect, table=ctx.table)
            maybe_show_sql(count_sql)
            set_last_sql(count_sql)
            result = get_inspect(ctx.connector, ctx.table, verbose=verbose)

        from querido.core.next_steps import for_inspect

        envelope_data = {
            "table": ctx.table,
            "row_count": result["row_count"],
            "columns": result["columns"],
        }
        if verbose and result["table_comment"]:
            envelope_data["table_comment"] = result["table_comment"]

        if emit(
            "inspect",
            ctx.table,
            result["columns"],
            result["row_count"],
            data=envelope_data,
            next_steps=lambda: for_inspect(
                result, connection=connection, table=ctx.table, verbose=verbose
            ),
            connection=connection,
            table=ctx.table,
            verbose=verbose,
            table_comment=result["table_comment"],
        ):
            return
