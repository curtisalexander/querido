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
    target: str | None = typer.Option(None, "--target", help="Right table name."),
    since: str | None = typer.Option(
        None,
        "--since",
        help="Compare the live table to the latest structured snapshot in a session.",
    ),
    target_connection: str | None = typer.Option(
        None,
        "--target-connection",
        help="Connection for right table (default: same as --connection).",
    ),
    db_type: str | None = typer.Option(
        None,
        "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
) -> None:
    """Compare column schemas between two tables.

    Same connection:
        qdo diff -c ./my.db -t users --target users_v2

    Cross-connection:
        qdo diff -c staging.db -t users --target-connection prod.db --target users

    Against a prior session snapshot:
        qdo diff -c ./my.db -t users --since migration-audit
    """
    from querido.cli._pipeline import dispatch_output
    from querido.cli._validation import resolve_table
    from querido.config import resolve_connection
    from querido.connectors.base import validate_table_name
    from querido.connectors.factory import create_connector
    from querido.core.diff import schema_diff, session_schema_diff
    from querido.core.session import find_latest_table_snapshot, session_dir

    if since and target:
        raise typer.BadParameter("Cannot use both --target and --since.")
    if since and target_connection:
        raise typer.BadParameter("Cannot use --target-connection with --since.")
    if not since and not target:
        raise typer.BadParameter("Must provide either --target or --since.")

    validate_table_name(table)
    if target:
        validate_table_name(target)

    config = resolve_connection(connection, db_type)
    target_table = target

    if since:
        session_path = session_dir(since)
        if not session_path.is_dir():
            raise typer.BadParameter(f"Session not found: {since}")

        with create_connector(config) as conn:
            resolved_table = resolve_table(conn, table)
            current_cols = conn.get_columns(resolved_table)
            current_row_count = conn.get_row_count(resolved_table)

        snapshot = find_latest_table_snapshot(since, connection=connection, table=resolved_table)
        if snapshot is None:
            raise typer.BadParameter(
                f"No structured inspect/context snapshot found for table '{resolved_table}' "
                f"in session '{since}'."
            )

        result = session_schema_diff(
            table=resolved_table,
            current_columns=current_cols,
            current_row_count=current_row_count,
            snapshot=snapshot,
        )
    elif target_connection:
        assert target_table is not None
        # Cross-connection diff
        target_config = resolve_connection(target_connection, db_type)
        with create_connector(config) as left_conn:
            left_cols = left_conn.get_columns(table)
        with create_connector(target_config) as right_conn:
            right_cols = right_conn.get_columns(target_table)
        result = schema_diff(table, left_cols, target_table, right_cols)
    else:
        assert target_table is not None
        # Same connection
        with create_connector(config) as conn:
            left_cols = conn.get_columns(table)
            right_cols = conn.get_columns(target_table)
        result = schema_diff(table, left_cols, target_table, right_cols)

    from querido.output.envelope import emit_envelope, is_structured_format

    if is_structured_format():
        from querido.core.next_steps import for_diff

        emit_envelope(
            command="diff",
            data=result,
            next_steps=for_diff(
                result,
                connection=connection,
                left_table=table,
                right_table=target_table,
                target_connection=target_connection,
            ),
            connection=connection,
            table=table,
        )
        return

    dispatch_output("diff", result)
