"""qdo sql — generate SQL statements from table metadata."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors
from querido.cli._options import conn_opt, dbtype_opt, table_opt

app = typer.Typer(help="Generate SQL statements for a table.")


def _get_columns_and_dialect(
    table: str, connection: str, db_type: str | None
) -> tuple[list[dict], str, str]:
    """Validate, connect, and return (columns, dialect, resolved_table)."""
    from querido.cli._validation import resolve_table
    from querido.config import resolve_connection
    from querido.connectors.base import validate_table_name
    from querido.connectors.factory import create_connector

    validate_table_name(table)
    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        resolved = resolve_table(connector, table)
        columns = connector.get_columns(resolved)
        dialect = connector.dialect

    return columns, dialect, resolved


def _table_short_name(table: str) -> str:
    """Extract the bare table name from a possibly-qualified reference.

    ``"database.schema.table"`` → ``"table"``
    ``"schema.table"``          → ``"table"``
    ``"table"``                 → ``"table"``
    """
    return table.rsplit(".", 1)[-1]


def _render(template_name: str, dialect: str, **kwargs: object) -> None:
    """Render a generate/* template and print to stdout."""
    from querido.sql.renderer import render_template

    sql = render_template(f"generate/{template_name}", dialect, **kwargs)
    print(sql)


def _format_sql_literal(value: object) -> str:
    """Format a Python value as a SQL literal string."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # Strings, dates, datetimes, and other types — quote as string literal
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


@app.command()
@friendly_errors
def select(
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
) -> None:
    """Generate a SELECT statement with all columns."""
    columns, dialect, resolved = _get_columns_and_dialect(table, connection, db_type)
    _render("select", dialect, table=resolved, columns=columns)


@app.command()
@friendly_errors
def insert(
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
) -> None:
    """Generate an INSERT statement with named placeholders."""
    columns, dialect, resolved = _get_columns_and_dialect(table, connection, db_type)
    _render("insert", dialect, table=resolved, columns=columns)


@app.command()
@friendly_errors
def ddl(
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
) -> None:
    """Generate a CREATE TABLE DDL statement."""
    columns, dialect, resolved = _get_columns_and_dialect(table, connection, db_type)
    _render("ddl", dialect, table=resolved, columns=columns)


@app.command()
@friendly_errors
def task(
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
) -> None:
    """Generate a Snowflake task template. (Snowflake only)"""
    columns, dialect, resolved = _get_columns_and_dialect(table, connection, db_type)
    from querido.cli._validation import require_snowflake

    require_snowflake(dialect, "task")
    _render(
        "task",
        dialect,
        table=resolved,
        table_name=_table_short_name(resolved),
        columns=columns,
    )


@app.command()
@friendly_errors
def udf(
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
) -> None:
    """Generate a UDF template using table columns as parameters."""
    columns, dialect, resolved = _get_columns_and_dialect(table, connection, db_type)
    _render("udf", dialect, table=resolved, columns=columns)


@app.command()
@friendly_errors
def procedure(
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
) -> None:
    """Generate a stored procedure template. (Snowflake only)"""
    columns, dialect, resolved = _get_columns_and_dialect(table, connection, db_type)
    from querido.cli._validation import require_snowflake

    require_snowflake(dialect, "procedure")
    _render(
        "procedure",
        dialect,
        table=resolved,
        table_name=_table_short_name(resolved),
        columns=columns,
    )


@app.command()
@friendly_errors
def scratch(
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
    rows: int = typer.Option(5, "--rows", "-r", min=1, help="Number of sample rows to include."),
) -> None:
    """Generate a temp table with sample data for experimentation."""
    from querido.cli._validation import resolve_table
    from querido.config import resolve_connection
    from querido.connectors.base import validate_table_name
    from querido.connectors.factory import create_connector
    from querido.sql.renderer import render_template

    validate_table_name(table)
    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        resolved = resolve_table(connector, table)
        columns = connector.get_columns(resolved)
        preview_sql = render_template("preview", connector.dialect, table=resolved, limit=rows)
        sample_rows = connector.execute(preview_sql)
        dialect = connector.dialect

    # Format each row's values as a comma-separated SQL literal string.
    # Value formatting stays in Python (not Jinja2) because it involves
    # type inspection and SQL escaping that templates aren't suited for.
    col_names = [c["name"] for c in columns]
    formatted_rows = [
        ", ".join(_format_sql_literal(row.get(n)) for n in col_names) for row in sample_rows
    ]

    _render(
        "scratch",
        dialect,
        table=resolved,
        table_name=_table_short_name(resolved),
        columns=columns,
        rows=formatted_rows,
    )
