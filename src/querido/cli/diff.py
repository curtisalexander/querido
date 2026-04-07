"""``qdo diff`` — compare schemas between two tables."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Compare schemas between two tables.")


@app.callback(invoke_without_command=True)
@friendly_errors
def diff(
    table: str = typer.Option(..., "--table", "-t", help="Left table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    target: str = typer.Option(
        ..., "--target", help="Right table name."
    ),
    target_connection: str | None = typer.Option(
        None, "--target-connection",
        help="Connection for right table (default: same as --connection).",
    ),
    db_type: str | None = typer.Option(
        None, "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
) -> None:
    """Compare column schemas between two tables.

    Same connection:
        qdo diff -c ./my.db -t users --target users_v2

    Cross-connection:
        qdo diff -c staging.db -t users --target-connection prod.db --target users
    """
    from querido.cli._pipeline import dispatch_output
    from querido.config import resolve_connection
    from querido.connectors.base import validate_table_name
    from querido.connectors.factory import create_connector
    from querido.core.diff import schema_diff

    validate_table_name(table)
    validate_table_name(target)

    config = resolve_connection(connection, db_type)

    if target_connection:
        # Cross-connection diff
        target_config = resolve_connection(target_connection, db_type)
        with create_connector(config) as left_conn:
            left_cols = left_conn.get_columns(table)
        with create_connector(target_config) as right_conn:
            right_cols = right_conn.get_columns(target)
    else:
        # Same connection
        with create_connector(config) as conn:
            left_cols = conn.get_columns(table)
            right_cols = conn.get_columns(target)

    result = schema_diff(table, left_cols, target, right_cols)
    dispatch_output("diff", result)
