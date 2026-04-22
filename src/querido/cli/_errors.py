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
    """Turn a database driver exception into a user-friendly message.

    Expects *exc* to already be a :class:`ConnectorError` subclass; raw
    driver exceptions (sqlite3.Error, duckdb.Error, snowflake.Error) that
    slip past the connector wrappers fall through to a generic label.
    """
    from querido.connectors.base import (
        AuthenticationError,
        ColumnNotFoundError,
        DatabaseLockedError,
        DatabaseOpenError,
        TableNotFoundError,
    )

    msg = str(exc).strip()

    if isinstance(exc, TableNotFoundError):
        return f"Table not found: {msg}"
    if isinstance(exc, ColumnNotFoundError):
        return f"Column not found: {msg}"
    if isinstance(exc, DatabaseLockedError):
        return f"Database is locked — another process may be using it. {msg}"
    if isinstance(exc, DatabaseOpenError):
        return f"Cannot open database file: {msg}"
    if isinstance(exc, AuthenticationError):
        return f"Authentication failed: {msg}"

    return f"Database error ({type(exc).__name__}): {msg}"


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

        from querido.cli._context import get_output_format

        try:
            return fn(*args, **kwargs)
        except typer.BadParameter as exc:
            fmt = get_output_format()
            if fmt not in ("json", "agent"):
                raise

            msg = str(exc)
            code = _bad_parameter_code(msg)
            try_next = _try_next_for(code)
            _emit_structured_error(msg, code, None, None, try_next, fmt)
            raise typer.Exit(code=1) from None
        except (typer.Exit, typer.Abort, SystemExit):
            raise
        except KeyboardInterrupt:
            # QueryCancelled is a subclass of KeyboardInterrupt
            raise typer.Exit(code=130) from None
        except Exception as exc:
            msg = _classify_error(exc)
            code = _error_code(exc)
            hint = _recovery_hint(exc)
            try_next = _try_next_for(code)

            with _last_sql_lock:
                last = _last_sql

            fmt = get_output_format()
            if fmt in ("json", "agent"):
                _emit_structured_error(
                    msg, code, hint, last if _is_db_error(exc) else None, try_next, fmt
                )
            else:
                _emit_rich_error(msg, exc, last, try_next)

            raise typer.Exit(code=1) from None

    return wrapper


def _emit_rich_error(msg: str, exc: Exception, last_sql: str | None, try_next: list[dict]) -> None:
    """Print a human-readable error to stderr with Rich markup."""
    from rich.console import Console

    console = Console(stderr=True)
    console.print(f"\n[bold red]Error:[/bold red] {msg}")

    hint = _recovery_hint(exc)
    if hint:
        console.print(f"[dim]Hint: {hint}[/dim]")

    for step in try_next:
        console.print(f"[dim]Try:[/dim] {step['cmd']}  [dim]— {step['why']}[/dim]")

    if last_sql is not None and _is_db_error(exc):
        from querido.cli._context import print_sql

        console.print("\n[dim]The SQL that was being executed:[/dim]")
        print_sql(last_sql)


def _emit_structured_error(
    msg: str,
    code: str,
    hint: str | None,
    sql: str | None,
    try_next: list[dict],
    fmt: str,
) -> None:
    """Print a structured error object to stderr in JSON or agent format."""
    import sys

    payload: dict = {"error": True, "code": code, "message": msg}
    if hint:
        payload["hint"] = hint
    if sql:
        payload["sql"] = sql
    if try_next:
        payload["try_next"] = try_next

    if fmt == "agent":
        from querido.output.envelope import render_agent

        print(render_agent(payload), file=sys.stderr)
    else:
        import json

        print(json.dumps(payload, indent=2), file=sys.stderr)


def _try_next_for(code: str) -> list[dict]:
    """Build ``try_next`` entries from the active CLI params (best-effort)."""
    import click

    from querido.core.next_steps import for_error

    connection: str | None = None
    table: str | None = None
    try:
        ctx = click.get_current_context(silent=True)
        while ctx is not None:
            params = ctx.params or {}
            connection = connection or params.get("connection")
            table = table or params.get("table")
            ctx = ctx.parent
    except (AttributeError, LookupError):
        pass

    return for_error(code, connection=connection, table=table)


def _is_db_error(exc: Exception) -> bool:
    """Return True if *exc* originated from the DB layer.

    Matches both :class:`ConnectorError` (normal path — connectors wrap
    driver errors in ``execute()``/``__init__``) and raw driver exceptions
    that slip past the wrapper (detected by module name).
    """
    import sqlite3

    from querido.connectors.base import ConnectorError

    if isinstance(exc, ConnectorError):
        return True
    if isinstance(exc, sqlite3.Error):
        return True
    module = type(exc).__module__ or ""
    return "duckdb" in module or "snowflake" in module


def _bad_parameter_code(msg: str) -> str:
    """Infer a structured error code from a ``typer.BadParameter`` message."""
    lower = msg.lower()
    if lower.startswith("table '") and " not found" in lower:
        return "TABLE_NOT_FOUND"
    if lower.startswith("column '") and " not found" in lower:
        return "COLUMN_NOT_FOUND"
    if lower.startswith("session not found:"):
        return "SESSION_NOT_FOUND"
    if lower.startswith("session step not found:"):
        return "SESSION_STEP_NOT_FOUND"
    if lower.startswith("session step is not structured:"):
        return "SESSION_STEP_UNSTRUCTURED"
    if lower.startswith("session step is unsupported for --from:"):
        return "SESSION_STEP_UNSUPPORTED"
    if lower.startswith("session step has no reusable sql:"):
        return "SESSION_STEP_NO_SQL"
    if lower.startswith("no structured inspect/context snapshot found for table '"):
        return "SESSION_SNAPSHOT_NOT_FOUND"
    if lower.startswith("no session specified."):
        return "SESSION_REQUIRED"
    if lower.startswith("no metadata found"):
        return "METADATA_NOT_FOUND"
    if lower.startswith("column set '") and " not found " in lower:
        return "COLUMN_SET_NOT_FOUND"
    if lower.startswith("sql file not found:"):
        return "SQL_FILE_NOT_FOUND"
    if lower.startswith("no sql provided."):
        return "SQL_REQUIRED"
    if lower.startswith("write queries require --allow-write."):
        return "WRITE_REQUIRES_ALLOW_WRITE"
    if "requires a snowflake connection" in lower:
        return "SNOWFLAKE_REQUIRED"
    if lower.startswith("unknown shell:"):
        return "SHELL_INVALID"
    if lower.startswith("unsupported db type:"):
        return "DB_TYPE_INVALID"
    if lower.startswith("connection '") and " already exists." in lower:
        return "CONNECTION_EXISTS"
    if lower.startswith("source connection '") and " not found." in lower:
        return "CONNECTION_NOT_FOUND"
    if lower.startswith("--path is required for "):
        return "PATH_REQUIRED"
    if lower.startswith("must provide --table or --sql."):
        return "TABLE_OR_SQL_REQUIRED"
    if lower.startswith("must provide --table, --sql, or --from."):
        return "TABLE_OR_SQL_REQUIRED"
    if lower.startswith("--export-format must be one of:"):
        return "EXPORT_FORMAT_INVALID"
    if lower.startswith("--direction must be one of:"):
        return "LINEAGE_DIRECTION_INVALID"
    if lower.startswith("--domain must be one of:"):
        return "LINEAGE_DOMAIN_INVALID"
    if lower.startswith("--sort must be one of:"):
        return "SORT_INVALID"
    if lower.startswith("must provide one of: --expect"):
        return "ASSERT_COMPARISON_REQUIRED"
    if lower.startswith("only one comparison allowed, got:"):
        return "ASSERT_COMPARISON_CONFLICT"
    if lower.startswith("cannot use both --columns and --column-set."):
        return "MUTUALLY_EXCLUSIVE_OPTIONS"
    if lower.startswith("cannot use --from with --sql or --file."):
        return "MUTUALLY_EXCLUSIVE_OPTIONS"
    if lower.startswith("cannot use --from with --table or --sql."):
        return "MUTUALLY_EXCLUSIVE_OPTIONS"
    if lower.startswith("invalid session step reference:"):
        return "SESSION_STEP_REF_INVALID"
    if lower.startswith("--group-by must specify at least one column."):
        return "GROUP_BY_REQUIRED"
    if lower.startswith("--agg must specify at least one aggregation."):
        return "AGG_REQUIRED"
    if lower.startswith("invalid aggregation expression:"):
        return "AGG_INVALID"
    if lower.startswith("all aggregations must use the same function."):
        return "AGG_MIXED_FUNCTIONS"
    return "VALIDATION_ERROR"


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
    from querido.connectors.base import (
        AuthenticationError,
        ColumnNotFoundError,
        DatabaseLockedError,
        DatabaseOpenError,
        TableNotFoundError,
    )

    if isinstance(exc, TableNotFoundError):
        return "TABLE_NOT_FOUND"
    if isinstance(exc, ColumnNotFoundError):
        return "COLUMN_NOT_FOUND"
    if isinstance(exc, DatabaseLockedError):
        return "DATABASE_LOCKED"
    if isinstance(exc, DatabaseOpenError):
        return "DATABASE_OPEN_FAILED"
    if isinstance(exc, AuthenticationError):
        return "AUTH_FAILED"
    if _is_db_error(exc):
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
    from querido.connectors.base import (
        AuthenticationError,
        ColumnNotFoundError,
        DatabaseLockedError,
        TableNotFoundError,
    )

    if isinstance(exc, TableNotFoundError):
        return "Try: qdo catalog -c <connection> --pattern <name> to find available tables"
    if isinstance(exc, ColumnNotFoundError):
        return "Try: qdo inspect -c <connection> -t <table> to see available columns"
    if isinstance(exc, DatabaseLockedError):
        return "Close other connections to this database and retry"
    if isinstance(exc, AuthenticationError):
        return "Check your credentials in connections.toml or re-authenticate"

    if isinstance(exc, FileNotFoundError):
        return "Check the file path and ensure it exists"
    if isinstance(exc, ImportError):
        return (
            "Install the missing extra: uv pip install 'querido[duckdb]' or 'querido[snowflake]'"
        )
    return None
