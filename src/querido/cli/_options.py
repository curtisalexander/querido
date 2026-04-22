"""Shared CLI option definitions for reuse across command modules."""

from __future__ import annotations

from typing import Any

import typer

table_opt = typer.Option(..., "--table", "-t", help="Table name.")
conn_opt = typer.Option(..., "--connection", "-c", help="Named connection or file path.")
dbtype_opt = typer.Option(
    None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
)


def parse_column_list(columns: str | None) -> list[str] | None:
    """Parse a comma-separated column list into a cleaned list of names.

    Returns ``None`` if *columns* is ``None`` or empty.
    """
    if not columns:
        return None
    result = [c.strip() for c in columns.split(",") if c.strip()]
    return result or None


def resolve_sql(
    sql_option: str | None,
    file_option: str | None,
    stdin: Any,
) -> str:
    """Resolve the SQL string from --sql, --file, or stdin.

    Priority: --sql > --file > stdin.
    """
    if sql_option is not None:
        return sql_option

    if file_option is not None:
        from pathlib import Path

        path = Path(file_option)
        if not path.exists():
            raise typer.BadParameter(f"SQL file not found: {file_option}")
        return path.read_text().strip()

    # Try stdin — only if it's not a tty (i.e. something is piped in)
    if hasattr(stdin, "isatty") and not stdin.isatty():
        text = stdin.read().strip()
        if text:
            return text

    raise typer.BadParameter("No SQL provided. Use --sql, --file, or pipe SQL via stdin.")


def resolve_query_sql(
    *,
    sql_option: str | None,
    file_option: str | None,
    from_option: str | None,
    stdin: Any,
) -> tuple[str, dict[str, Any] | None]:
    """Resolve SQL for ``query`` from direct input or a prior session step."""
    if from_option:
        if sql_option is not None or file_option is not None:
            raise typer.BadParameter("Cannot use --from with --sql or --file.")

        from querido.core.session import resolve_query_step_reference

        try:
            source = resolve_query_step_reference(from_option)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from None
        return str(source["sql"]), source

    return resolve_sql(sql_option, file_option, stdin), None


def resolve_export_sql(
    *,
    table_option: str | None,
    sql_option: str | None,
    from_option: str | None,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """Resolve export source from ``--table`` / ``--sql`` or ``--from``."""
    if from_option:
        if table_option or sql_option:
            raise typer.BadParameter("Cannot use --from with --table or --sql.")

        from querido.core.session import resolve_query_step_reference

        try:
            source = resolve_query_step_reference(from_option)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from None
        return None, str(source["sql"]), source

    return table_option, sql_option, None
