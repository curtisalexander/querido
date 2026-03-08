"""qdo sql — generate SQL statements from table metadata."""

from __future__ import annotations

import typer

app = typer.Typer(help="Generate SQL statements for a table.")

# ---------------------------------------------------------------------------
# Shared options
# ---------------------------------------------------------------------------

_table_opt = typer.Option(..., "--table", "-t", help="Table name.")
_conn_opt = typer.Option(..., "--connection", "-c", help="Named connection or file path.")
_dbtype_opt = typer.Option(
    None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
)


def _get_columns_and_dialect(
    table: str, connection: str, db_type: str | None
) -> tuple[list[dict], str]:
    """Validate, connect, and return (columns, dialect)."""
    from querido.config import resolve_connection
    from querido.connectors.base import validate_table_name
    from querido.connectors.factory import create_connector

    validate_table_name(table)
    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        columns = connector.get_columns(table)
        dialect = connector.dialect

    return columns, dialect


def _render(template_name: str, dialect: str, **kwargs: object) -> None:
    """Render a generate/* template and print to stdout."""
    from querido.sql.renderer import render_template

    sql = render_template(f"generate/{template_name}", dialect, **kwargs)
    print(sql)


def _require_snowflake(dialect: str, command: str) -> None:
    if dialect != "snowflake":
        raise typer.BadParameter(f"'{command}' is only supported for Snowflake connections.")


def _format_sql_literal(value: object) -> str:
    """Format a Python value as a SQL literal string."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return str(value)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


@app.command()
def select(
    table: str = _table_opt,
    connection: str = _conn_opt,
    db_type: str | None = _dbtype_opt,
) -> None:
    """Generate a SELECT statement with all columns."""
    columns, dialect = _get_columns_and_dialect(table, connection, db_type)
    _render("select", dialect, table=table, columns=columns)


@app.command()
def insert(
    table: str = _table_opt,
    connection: str = _conn_opt,
    db_type: str | None = _dbtype_opt,
) -> None:
    """Generate an INSERT statement with named placeholders."""
    columns, dialect = _get_columns_and_dialect(table, connection, db_type)
    _render("insert", dialect, table=table, columns=columns)


@app.command()
def ddl(
    table: str = _table_opt,
    connection: str = _conn_opt,
    db_type: str | None = _dbtype_opt,
) -> None:
    """Generate a CREATE TABLE DDL statement."""
    columns, dialect = _get_columns_and_dialect(table, connection, db_type)
    _render("ddl", dialect, table=table, columns=columns)


@app.command()
def task(
    table: str = _table_opt,
    connection: str = _conn_opt,
    db_type: str | None = _dbtype_opt,
) -> None:
    """Generate a Snowflake task template. (Snowflake only)"""
    columns, dialect = _get_columns_and_dialect(table, connection, db_type)
    _require_snowflake(dialect, "task")
    _render("task", dialect, table=table, columns=columns)


@app.command()
def udf(
    table: str = _table_opt,
    connection: str = _conn_opt,
    db_type: str | None = _dbtype_opt,
) -> None:
    """Generate a UDF template using table columns as parameters."""
    columns, dialect = _get_columns_and_dialect(table, connection, db_type)
    _render("udf", dialect, table=table, columns=columns)


@app.command()
def procedure(
    table: str = _table_opt,
    connection: str = _conn_opt,
    db_type: str | None = _dbtype_opt,
) -> None:
    """Generate a stored procedure template. (Snowflake only)"""
    columns, dialect = _get_columns_and_dialect(table, connection, db_type)
    _require_snowflake(dialect, "procedure")
    _render("procedure", dialect, table=table, columns=columns)


@app.command()
def scratch(
    table: str = _table_opt,
    connection: str = _conn_opt,
    db_type: str | None = _dbtype_opt,
    rows: int = typer.Option(5, "--rows", "-r", help="Number of sample rows to include."),
) -> None:
    """Generate a temp table with sample data for experimentation."""
    from querido.config import resolve_connection
    from querido.connectors.base import validate_table_name
    from querido.connectors.factory import create_connector
    from querido.sql.renderer import render_template

    validate_table_name(table)
    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        columns = connector.get_columns(table)
        preview_sql = render_template("preview", connector.dialect, table=table, limit=rows)
        sample_rows = connector.execute(preview_sql)
        dialect = connector.dialect

    # Format each row's values as a comma-separated SQL literal string.
    # Value formatting stays in Python (not Jinja2) because it involves
    # type inspection and SQL escaping that templates aren't suited for.
    col_names = [c["name"] for c in columns]
    formatted_rows = [
        ", ".join(_format_sql_literal(row.get(n)) for n in col_names) for row in sample_rows
    ]

    _render("scratch", dialect, table=table, columns=columns, rows=formatted_rows)
