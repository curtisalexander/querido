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
    from querido.cli._validation import resolve_table
    from querido.config import resolve_connection
    from querido.connectors.base import validate_table_name
    from querido.connectors.factory import create_connector

    validate_table_name(table)
    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        from rich.console import Console

        from querido.cli._errors import set_last_connector

        console = Console(stderr=True)
        set_last_connector(connector)

        resolved_table = resolve_table(connector, table)

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
                pass
            finally:
                cache.close()

        t = threading.Thread(target=_warm, daemon=True)
        t.start()
    except Exception:
        pass


def _maybe_reraise_as_table_not_found(exc: Exception, connector: object, table: str) -> None:
    """If *exc* is a 'table not found' error, re-raise as BadParameter with suggestions."""
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
        pass


def dispatch_output(command_name: str, /, *args: Any, **kwargs: Any) -> None:
    """Three-way output dispatch based on the ``--format`` CLI flag.

    Uses naming conventions to locate the right output function:

    - ``rich``: ``querido.output.console.print_{command_name}(*args, **kwargs)``
    - ``html``: ``querido.output.html.format_{command_name}_html(*args, **kwargs)``
      → opened in the browser via ``emit_html``
    - Otherwise: ``querido.output.formats.format_{command_name}(*args, fmt, **kwargs)``
      → printed to stdout

    The *fmt* string is automatically appended to positional args for the
    text formatter.
    """
    from importlib import import_module

    from querido.cli._context import get_output_format

    fmt = get_output_format()
    if fmt == "rich":
        mod = import_module("querido.output.console")
        getattr(mod, f"print_{command_name}")(*args, **kwargs)
    elif fmt == "html":
        from querido.cli._context import emit_html

        mod = import_module("querido.output.html")
        html = getattr(mod, f"format_{command_name}_html")(*args, **kwargs)
        emit_html(html)
    else:
        mod = import_module("querido.output.formats")
        text = getattr(mod, f"format_{command_name}")(*args, fmt, **kwargs)
        print(text)
