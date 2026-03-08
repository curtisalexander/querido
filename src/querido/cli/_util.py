from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from querido.connectors.base import Connector


NUMERIC_TYPE_PREFIXES = (
    "int",
    "integer",
    "bigint",
    "smallint",
    "tinyint",
    "float",
    "double",
    "real",
    "decimal",
    "numeric",
    "number",
    "hugeint",
)


def is_numeric_type(type_str: str) -> bool:
    """Return True if the SQL type string represents a numeric type."""
    return type_str.lower().startswith(NUMERIC_TYPE_PREFIXES)


def _get_root_obj() -> dict:
    """Walk up the Click context chain and return the root context's obj dict."""
    import click

    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return {}

    root = ctx
    while root.parent is not None:
        root = root.parent

    return root.obj or {}


def get_output_format() -> str:
    """Return the --format value from the root CLI context, defaulting to 'rich'."""
    return _get_root_obj().get("format", "rich")


def emit_html(html_content: str, prefix: str = "qdo-") -> None:
    """Write *html_content* to a temp file, open it in the browser, and print the path."""
    from querido.output.html import open_html

    path = open_html(html_content, prefix=prefix)
    import sys

    print(f"Opened {path}", file=sys.stderr)


def maybe_show_sql(sql: str) -> None:
    """Print SQL to stderr if --show-sql was passed."""
    if not _get_root_obj().get("show_sql"):
        return

    _print_sql(sql)


def _print_sql(sql: str) -> None:
    """Print SQL to stderr with syntax highlighting."""
    from rich.console import Console
    from rich.syntax import Syntax

    console = Console(stderr=True)
    console.print()
    console.print(Syntax(sql.strip(), "sql", theme="monokai", line_numbers=False))
    console.print()


# ---------------------------------------------------------------------------
# Table / column existence helpers
# ---------------------------------------------------------------------------


def _fuzzy_suggestions(name: str, candidates: list[str], *, n: int = 3) -> list[str]:
    """Return up to *n* close matches for *name* from *candidates* using difflib."""
    from difflib import get_close_matches

    return get_close_matches(name.lower(), [c.lower() for c in candidates], n=n, cutoff=0.4)


def _format_not_found(
    kind: str,
    name: str,
    candidates: list[str],
    *,
    context: str = "",
    max_available: int = 30,
) -> str:
    """Build a 'not found' message with fuzzy suggestions.

    For small candidate lists, the full list is always shown.  For large lists
    (e.g. thousands of Snowflake tables) only fuzzy matches are shown.
    """
    msg = f"{kind} '{name}' not found"
    if context:
        msg += f" in {context}"
    msg += "."

    suggestions = _fuzzy_suggestions(name, candidates)
    if suggestions:
        # Map back to original casing
        lower_to_orig: dict[str, str] = {}
        for c in candidates:
            lower_to_orig.setdefault(c.lower(), c)
        originals = [lower_to_orig[s] for s in suggestions]
        msg += f"\nDid you mean: {', '.join(originals)}?"

    if candidates and len(candidates) <= max_available:
        msg += f"\nAvailable {kind.lower()}s: {', '.join(sorted(candidates))}"

    return msg


def check_table_exists(connector: Connector, table: str) -> None:
    """Raise typer.BadParameter if *table* does not exist in the database."""
    import typer

    tables = connector.get_tables()
    table_names = [t["name"] for t in tables]

    if not any(t.lower() == table.lower() for t in table_names):
        raise typer.BadParameter(_format_not_found("Table", table, table_names))


def resolve_column(connector: Connector, table: str, column: str, *, label: str = "column") -> str:
    """Return the canonical column name (as stored in the database).

    Uses case-insensitive matching so users don't need to worry about casing.
    Raises typer.BadParameter with fuzzy suggestions on mismatch.
    """
    import typer

    col_meta = connector.get_columns(table)
    col_names = [c["name"] for c in col_meta]

    for name in col_names:
        if name.lower() == column.lower():
            return name

    raise typer.BadParameter(
        _format_not_found("Column", column, col_names, context=f"table '{table}'")
    )


# ---------------------------------------------------------------------------
# CLI error handler
# ---------------------------------------------------------------------------


# SQL that was most recently rendered — set by maybe_show_sql or directly by
# commands so that the error handler can display it on failure.
_last_sql: str | None = None


def set_last_sql(sql: str) -> None:
    """Record the most recently executed SQL for error-reporting purposes."""
    global _last_sql
    _last_sql = sql


def _format_db_error(exc: Exception) -> str:
    """Turn a database driver exception into a user-friendly message."""
    msg = str(exc).strip()
    cls = type(exc).__name__

    # Classify common errors
    msg_lower = msg.lower()
    if "no such table" in msg_lower or "does not exist" in msg_lower:
        return f"Table not found: {msg}"
    if "no such column" in msg_lower:
        return f"Column not found: {msg}"
    if "database is locked" in msg_lower:
        return f"Database is locked — another process may be using it. {msg}"
    if "unable to open database" in msg_lower or "could not open" in msg_lower:
        return f"Cannot open database file: {msg}"
    if "authentication" in msg_lower or "password" in msg_lower:
        return f"Authentication failed: {msg}"

    return f"Database error ({cls}): {msg}"


def friendly_errors[T, **P](fn: Callable[P, T]) -> Callable[P, T]:
    """Decorator that catches common exceptions and prints clean CLI messages.

    Database errors, ValueErrors from validation, file-not-found errors, and
    import errors are all turned into one-line messages on stderr.  When a
    database error occurs, the last rendered SQL is automatically printed to
    help with debugging.
    """

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        global _last_sql
        _last_sql = None

        import typer

        try:
            return fn(*args, **kwargs)
        except (typer.Exit, typer.BadParameter, typer.Abort, SystemExit):
            raise
        except Exception as exc:
            from rich.console import Console

            console = Console(stderr=True)
            msg = _classify_error(exc)
            console.print(f"\n[bold red]Error:[/bold red] {msg}")

            if _last_sql is not None and _is_db_error(exc):
                console.print("\n[dim]The SQL that was being executed:[/dim]")
                _print_sql(_last_sql)

            raise typer.Exit(code=1) from None

    return wrapper


def _is_db_error(exc: Exception) -> bool:
    """Return True if *exc* looks like a database driver error."""
    import sqlite3

    if isinstance(exc, sqlite3.Error):
        return True

    module = type(exc).__module__ or ""
    return "duckdb" in module or "snowflake" in module


def _classify_error(exc: Exception) -> str:
    """Produce a human-readable message for *exc*."""
    if _is_db_error(exc):
        return _format_db_error(exc)

    if isinstance(exc, FileNotFoundError):
        return f"File not found: {exc}"

    if isinstance(exc, ValueError):
        return str(exc)

    if isinstance(exc, ImportError):
        return str(exc)

    if isinstance(exc, PermissionError):
        return f"Permission denied: {exc}"

    return f"{type(exc).__name__}: {exc}"
