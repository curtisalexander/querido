import typer

from querido.cli._errors import friendly_errors
from querido.cli._options import conn_opt, dbtype_opt

app = typer.Typer(help="Show the SQL definition of a view.")


@app.callback(invoke_without_command=True)
@friendly_errors
def view_def(
    view: str = typer.Option(..., "--view", help="View name to retrieve definition for."),
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
) -> None:
    """Show the SQL definition of a view."""
    from querido.cli._context import maybe_show_sql
    from querido.cli._pipeline import emit, table_command

    with table_command(table=view, connection=connection, db_type=db_type) as ctx:
        with ctx.spin(f"Retrieving definition for [bold]{ctx.table}[/bold]"):
            from querido.core.lineage import get_view_definition

            try:
                result = get_view_definition(ctx.connector, ctx.table)
            except LookupError as exc:
                raise typer.BadParameter(str(exc)) from exc

        maybe_show_sql(result["definition"])

        from querido.core.next_steps import for_view_def

        if emit(
            "view-def",
            result,
            dispatch_as="lineage",
            next_steps=lambda: for_view_def(result, connection=connection, view=ctx.table),
            connection=connection,
            table=ctx.table,
        ):
            return
