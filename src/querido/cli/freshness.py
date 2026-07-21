"""``qdo freshness`` — detect temporal columns and summarize recency."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors
from querido.cli._options import conn_opt, dbtype_opt, table_opt

app = typer.Typer(help="Detect temporal columns and summarize table freshness.")


@app.callback(invoke_without_command=True)
@friendly_errors
def freshness(
    table: str = table_opt,
    column: str | None = typer.Option(
        None,
        "--column",
        "-C",
        help="Temporal column to inspect explicitly (default: auto-detect).",
    ),
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
    stale_after: int = typer.Option(
        7,
        "--stale-after",
        min=0,
        help="Mark the table stale when the newest timestamp is older than this many days.",
    ),
) -> None:
    """Detect likely timestamp/date columns and summarize recency."""
    from querido.cli._context import maybe_show_sql
    from querido.cli._errors import set_last_sql
    from querido.cli._pipeline import emit, table_command

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        resolved_column = None
        if column is not None:
            from querido.cli._validation import resolve_column

            resolved_column = resolve_column(ctx.connector, ctx.table, column, label="column")

        with ctx.spin(f"Checking freshness of [bold]{ctx.table}[/bold]"):
            from querido.core.freshness import get_freshness

            result = get_freshness(
                ctx.connector,
                ctx.table,
                column=resolved_column,
                stale_after_days=stale_after,
            )

    rendered_sql = result.get("sql") or ""
    if rendered_sql:
        maybe_show_sql(rendered_sql)
        set_last_sql(rendered_sql)

    from querido.core.next_steps import for_freshness

    if emit(
        "freshness",
        result,
        next_steps=lambda: for_freshness(
            dict(result), connection=connection, table=result["table"]
        ),
        connection=connection,
        table=result["table"],
    ):
        return
