"""CLI pipeline helpers — shared setup and output dispatch."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

    from rich.console import Console

    from querido.connectors.base import Connector


@dataclass
class CommandContext:
    """Shared state for a CLI command's lifecycle."""

    connector: Connector
    console: Console
    table: str = ""

    def spin(self, message: str) -> contextlib.AbstractContextManager:
        """Return a query_status spinner context manager."""
        from querido.cli._progress import query_status

        return query_status(self.console, message, self.connector)


@contextlib.contextmanager
def table_command(
    *,
    table: str,
    connection: str,
    db_type: str | None = None,
) -> Generator[CommandContext]:
    """Context manager that handles the common CLI command setup.

    Validates the table name, resolves the connection, creates a connector,
    resolves the table to its canonical name, and yields a ``CommandContext``
    with the connector, console, resolved table name, and a ``spin()`` helper.

    Usage::

        with table_command(table=t, connection=c, db_type=d) as ctx:
            with ctx.spin("Loading preview"):
                data = get_preview(ctx.connector, ctx.table, limit=20)
            dispatch_output("preview", ctx.table, data, 20)
    """
    import logging

    from querido.cli._validation import resolve_table
    from querido.config import resolve_connection
    from querido.connectors.base import validate_table_name
    from querido.connectors.factory import create_connector

    log = logging.getLogger("querido.cli")

    validate_table_name(table)
    config = resolve_connection(connection, db_type)
    detail = config.get("path") or config.get("account", "")
    log.debug("Connection: type=%s %s", config.get("type", "?"), detail)

    with create_connector(config) as connector:
        from rich.console import Console

        console = Console(stderr=True)
        log.debug("Connected (%s)", connector.dialect)

        resolved_table = resolve_table(connector, table)
        log.debug("Resolved table: %s", resolved_table)

        _maybe_warm_cache(connection, config, connector)

        try:
            yield CommandContext(connector=connector, console=console, table=resolved_table)
        except Exception as exc:
            _maybe_reraise_as_table_not_found(exc, connector, resolved_table)
            raise


def _maybe_warm_cache(connection: str, config: dict, connector: object) -> None:
    """Kick off a background cache warm if the cache is empty or stale.

    Only warms for named connections (not file paths) to avoid polluting
    the cache with transient databases.  Only caches the table list (not
    columns) to keep the operation fast.
    """
    import threading

    # Only warm for named connections (file paths don't have a stable name)
    # and only for connectors that support concurrent queries (Snowflake).
    # Local databases (SQLite/DuckDB) are fast enough that caching is
    # unnecessary, and SQLite isn't safe to query from a background thread.
    if not getattr(connector, "supports_concurrent_queries", False):
        return

    from querido.config import load_connections

    connections = load_connections()
    if connection not in connections:
        return

    import logging

    log = logging.getLogger("querido.cli.cache")

    try:
        from querido.cache import MetadataCache

        cache = MetadataCache()
        if cache.is_fresh(connection):
            cache.close()
            return

        def _warm() -> None:
            try:
                cache.sync_tables_only(connection, connector)  # type: ignore[arg-type]
            except Exception:
                log.debug("Background cache warm failed", exc_info=True)
            finally:
                cache.close()

        t = threading.Thread(target=_warm, daemon=True)
        t.start()
    except Exception:
        log.debug("Failed to start cache warm", exc_info=True)


def _maybe_reraise_as_table_not_found(exc: Exception, connector: object, table: str) -> None:
    """If *exc* is a 'table not found' error, re-raise as BadParameter with suggestions."""
    from querido.connectors.base import TableNotFoundError

    is_table_error = isinstance(exc, TableNotFoundError)
    if not is_table_error:
        # Fallback: string-match for dialect-specific error messages
        msg = str(exc).lower()
        if "no such table" not in msg and "does not exist" not in msg:
            return

    import typer

    try:
        from querido.cli._validation import _format_not_found

        tables = connector.get_tables()  # type: ignore[union-attr]
        names = [t["name"] for t in tables]
        raise typer.BadParameter(_format_not_found("Table", table, names)) from exc
    except typer.BadParameter:
        raise
    except Exception:
        import logging

        logging.getLogger("querido.cli").debug(
            "Failed to build table-not-found suggestion", exc_info=True
        )


@contextlib.contextmanager
def database_command(
    *,
    connection: str,
    db_type: str | None = None,
) -> Generator[CommandContext]:
    """Context manager for CLI commands that don't target a specific table.

    Like ``table_command`` but skips table validation and resolution.
    Use for commands like ``query``, ``catalog``, ``explain``, ``assert``,
    and ``export`` that operate at the database level.

    Usage::

        with database_command(connection=c, db_type=d) as ctx:
            with ctx.spin("Executing query"):
                data = run_query(ctx.connector, sql)
            dispatch_output("query", data)
    """
    import logging

    from querido.config import resolve_connection
    from querido.connectors.factory import create_connector

    log = logging.getLogger("querido.cli")

    config = resolve_connection(connection, db_type)
    detail = config.get("path") or config.get("account", "")
    log.debug("Connection: type=%s %s", config.get("type", "?"), detail)

    with create_connector(config) as connector:
        from rich.console import Console

        console = Console(stderr=True)
        log.debug("Connected (%s)", connector.dialect)

        yield CommandContext(connector=connector, console=console)


def dispatch_output(command_name: str, /, *args: Any, **kwargs: Any) -> None:
    """Three-way output dispatch based on the ``--format`` CLI flag.

    Each output module exposes a ``REGISTRY`` dict mapping command names
    to their output functions.  This catches missing formatters at import
    time rather than failing with an opaque ``AttributeError`` at runtime.

    - ``rich``: ``querido.output.console.REGISTRY[command_name]``
    - ``html``: ``querido.output.html.REGISTRY[command_name]``
    - Otherwise: ``querido.output.formats.REGISTRY[command_name]``
    """
    from importlib import import_module
    from typing import cast

    from querido.cli._context import get_output_format

    fmt = get_output_format()
    if fmt == "rich":
        mod = import_module("querido.output.console")
        fn: Any = cast(Any, mod.REGISTRY)[command_name]
        fn(*args, **kwargs)
    elif fmt == "html":
        from querido.cli._context import emit_html

        mod = import_module("querido.output.html")
        fn = cast(Any, mod.REGISTRY)[command_name]
        html = fn(*args, **kwargs)
        emit_html(html)
    else:
        # Commands that go straight through dispatch_output (assert, pivot,
        # explain, template, lineage, …) don't build an agent envelope
        # themselves. Degrade agent → json so the output is at least
        # structured/parseable; true agent rendering lives on the
        # envelope-emitting commands (see querido.output.envelope).
        effective_fmt = "json" if fmt == "agent" else fmt
        mod = import_module("querido.output.formats")
        fn = cast(Any, mod.REGISTRY)[command_name]
        text = fn(*args, effective_fmt, **kwargs)
        print(text)
