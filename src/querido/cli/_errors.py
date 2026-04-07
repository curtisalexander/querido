"""CLI error handling — friendly_errors decorator and SQL tracking."""

from __future__ import annotations

import threading
from functools import wraps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


# SQL that was most recently rendered — set by set_last_sql or directly by
# commands so that the error handler can display it on failure.
_last_sql_lock = threading.Lock()
_last_sql: str | None = None


def set_last_sql(sql: str) -> None:
    """Record the most recently executed SQL for error-reporting purposes."""
    global _last_sql
    with _last_sql_lock:
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

    When ``--format json`` is active, errors are emitted as structured JSON
    to stderr so that coding agents can parse them programmatically.
    """

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        global _last_sql
        with _last_sql_lock:
            _last_sql = None

        import typer

        try:
            return fn(*args, **kwargs)
        except (typer.Exit, typer.BadParameter, typer.Abort, SystemExit):
            raise
        except KeyboardInterrupt:
            # QueryCancelled is a subclass of KeyboardInterrupt
            raise typer.Exit(code=130) from None
        except Exception as exc:
            msg = _classify_error(exc)
            code = _error_code(exc)
            hint = _recovery_hint(exc)

            with _last_sql_lock:
                last = _last_sql

            from querido.cli._context import get_output_format

            if get_output_format() == "json":
                _emit_json_error(msg, code, hint, last if _is_db_error(exc) else None)
            else:
                _emit_rich_error(msg, exc, last)

            raise typer.Exit(code=1) from None

    return wrapper


def _emit_rich_error(msg: str, exc: Exception, last_sql: str | None) -> None:
    """Print a human-readable error to stderr with Rich markup."""
    from rich.console import Console

    console = Console(stderr=True)
    console.print(f"\n[bold red]Error:[/bold red] {msg}")

    hint = _recovery_hint(exc)
    if hint:
        console.print(f"[dim]Hint: {hint}[/dim]")

    if last_sql is not None and _is_db_error(exc):
        from querido.cli._context import print_sql

        console.print("\n[dim]The SQL that was being executed:[/dim]")
        print_sql(last_sql)


def _emit_json_error(msg: str, code: str, hint: str | None, sql: str | None) -> None:
    """Print a structured JSON error object to stderr."""
    import json
    import sys

    payload: dict = {"error": True, "code": code, "message": msg}
    if hint:
        payload["hint"] = hint
    if sql:
        payload["sql"] = sql
    print(json.dumps(payload, indent=2), file=sys.stderr)


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


def _error_code(exc: Exception) -> str:
    """Return a machine-readable error code for *exc*."""
    if _is_db_error(exc):
        msg_lower = str(exc).lower()
        if "no such table" in msg_lower or "does not exist" in msg_lower:
            return "TABLE_NOT_FOUND"
        if "no such column" in msg_lower:
            return "COLUMN_NOT_FOUND"
        if "database is locked" in msg_lower:
            return "DATABASE_LOCKED"
        if "unable to open database" in msg_lower or "could not open" in msg_lower:
            return "DATABASE_OPEN_FAILED"
        if "authentication" in msg_lower or "password" in msg_lower:
            return "AUTH_FAILED"
        return "DATABASE_ERROR"

    if isinstance(exc, FileNotFoundError):
        return "FILE_NOT_FOUND"
    if isinstance(exc, ValueError):
        return "VALIDATION_ERROR"
    if isinstance(exc, ImportError):
        return "MISSING_DEPENDENCY"
    if isinstance(exc, PermissionError):
        return "PERMISSION_DENIED"
    return "UNKNOWN_ERROR"


def _recovery_hint(exc: Exception) -> str | None:
    """Return an actionable hint for recovering from *exc*, or None."""
    if _is_db_error(exc):
        msg_lower = str(exc).lower()
        if "no such table" in msg_lower or "does not exist" in msg_lower:
            return "Try: qdo search -c <connection> -p <pattern> to find available tables"
        if "no such column" in msg_lower:
            return "Try: qdo inspect -c <connection> -t <table> to see available columns"
        if "database is locked" in msg_lower:
            return "Close other connections to this database and retry"
        if "authentication" in msg_lower or "password" in msg_lower:
            return "Check your credentials in connections.toml or re-authenticate"

    if isinstance(exc, FileNotFoundError):
        return "Check the file path and ensure it exists"
    if isinstance(exc, ImportError):
        return (
            "Install the missing extra: uv pip install 'querido[duckdb]' or 'querido[snowflake]'"
        )
    return None
