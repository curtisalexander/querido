"""CLI pipeline helpers — shared setup and output dispatch."""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
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


def _maybe_warm_cache(connection: str, config: dict, connector: Connector) -> object | None:
    """Kick off a background cache warm if the cache is empty or stale.

    Only warms for named connections (not file paths) to avoid polluting
    the cache with transient databases.  Only caches the table list (not
    columns) to keep the operation fast.

    The worker owns both its connector and cache handle. Neither object may
    cross a thread boundary or outlive the context manager that created it.
    The returned daemon thread is intentionally ignored by production callers;
    it exists so tests can wait for persistence without timing assumptions.
    """
    import threading

    # Only warm for named connections (file paths don't have a stable name)
    # and only for connectors that support concurrent queries (Snowflake).
    # Local databases (SQLite/DuckDB) are fast enough that caching is
    # unnecessary, and SQLite isn't safe to query from a background thread.
    if not getattr(connector, "supports_concurrent_queries", False):
        return None

    from querido.config import load_connections

    connections = load_connections()
    if connection not in connections:
        return None

    import logging

    log = logging.getLogger("querido.cli.cache")

    try:
        from querido.cache import MetadataCache

        with MetadataCache() as cache:
            if cache.is_fresh(connection):
                return None

        def _warm() -> None:
            try:
                from querido.connectors.factory import create_connector

                with create_connector(dict(config)) as warm_connector, MetadataCache() as cache:
                    cache.sync_tables_only(connection, warm_connector)
            except Exception:
                log.debug("Background cache warm failed", exc_info=True)

        t = threading.Thread(target=_warm, daemon=True)
        t.start()
        return t
    except Exception:
        log.debug("Failed to start cache warm", exc_info=True)
        return None


def _maybe_reraise_as_table_not_found(exc: Exception, connector: Connector, table: str) -> None:
    """If *exc* is a 'table not found' error, re-raise as BadParameter with suggestions."""
    from querido.connectors.base import ConnectorError, TableNotFoundError

    if not isinstance(exc, TableNotFoundError):
        return

    import typer

    try:
        from querido.cli._validation import _format_not_found

        tables = connector.get_tables()
        names = [t["name"] for t in tables]
        raise typer.BadParameter(_format_not_found("Table", table, names)) from exc
    except typer.BadParameter:
        raise
    except ConnectorError:
        import logging

        logging.getLogger("querido.cli").debug(
            "Failed to build table-not-found suggestion", exc_info=True
        )


@contextlib.contextmanager
def database_command(
    *,
    connection: str,
    db_type: str | None = None,
    read_only: bool = True,
) -> Generator[CommandContext]:
    """Context manager for CLI commands that don't target a specific table.

    Like ``table_command`` but skips table validation and resolution.
    Use for commands like ``query``, ``catalog``, ``explain``, ``assert``,
    and ``export`` that operate at the database level.

    *read_only* defaults to True; ``qdo query --allow-write`` passes False
    so file-backed local databases get a writable connection.

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

    with create_connector(config, read_only=read_only) as connector:
        from rich.console import Console

        console = Console(stderr=True)
        log.debug("Connected (%s)", connector.dialect)

        yield CommandContext(connector=connector, console=console)


def maybe_capture_hint(
    command_name: str,
    result: Mapping[str, Any],
    *,
    connection: str,
    table: str,
    file: Any,
) -> None:
    """Print a one-line dim capture hint when a scan computed uncaptured facts.

    Mirrors the agent-facing ``next_steps`` nudge: when ``context``/``quality``
    derive deterministic fields the stored metadata doesn't yet hold, the
    human-facing (rich) output ends with the exact ``--write-metadata`` command.
    Stays silent when there is nothing uncaptured to write so it never nags a
    table whose metadata is already complete.
    """
    from querido.cli._context import get_output_format

    # Only nudge on the human-facing rich path; structured formats carry the
    # same signal through next_steps / metadata_write in the envelope.
    if get_output_format() != "rich":
        return

    from querido.core.metadata_write import (
        _is_human_field,
        derive_from_context,
        derive_from_quality,
    )

    if command_name == "context":
        updates = derive_from_context(result)
    elif command_name == "quality":
        updates = derive_from_quality(result)  # type: ignore[arg-type]
    else:
        return

    if not _has_uncaptured_updates(result, updates, _is_human_field):
        return

    from querido.output.envelope import cmd

    capture = cmd(["qdo", command_name, "-c", connection, "-t", table, "--write-metadata"])
    print(f"\n  Capture: {capture}", file=file)


def _has_uncaptured_updates(
    result: Mapping[str, Any],
    updates: list[Any],
    is_human_field: Any,
) -> bool:
    """Return True if any derived update targets a field not already captured.

    A field counts as already captured when stored metadata holds a non-empty
    value for it (human-authored or a prior auto-write) — re-deriving the same
    fact is not worth a nudge.
    """
    if not updates:
        return False

    cols_by_name: dict[str, dict] = {}
    for col in result.get("columns") or []:
        name = col.get("name")
        if isinstance(name, str):
            cols_by_name[name] = col

    for upd in updates:
        target = result if upd.column is None else cols_by_name.get(upd.column)
        if target is None:
            continue
        existing = target.get(upd.field)
        # Stored metadata is merged onto the result; treat any non-empty value
        # for the derived field as "already captured".
        if existing is None or existing == [] or existing == "":
            return True
        if not is_human_field(existing):
            # A placeholder / low-value entry still counts as uncaptured.
            return True
    return False


def _lookup_formatter(module_path: str, command_name: str) -> Any:
    """Fetch ``command_name`` from a formatter module's ``REGISTRY``.

    A missing key is a programming error (a command wired to dispatch_output
    without a matching formatter), not user input — so raise a structured
    ``RuntimeError`` with a clear internal-error message instead of letting a
    raw ``KeyError`` bubble up and surface as an opaque ``UNKNOWN_ERROR``.
    """
    from importlib import import_module
    from typing import cast

    registry = cast(Any, import_module(module_path)).REGISTRY
    try:
        return registry[command_name]
    except KeyError:
        raise RuntimeError(
            f"internal error: no '{command_name}' formatter registered in "
            f"{module_path}.REGISTRY — this is a qdo bug, please open an issue."
        ) from None


def dispatch_output(command_name: str, /, *args: Any, **kwargs: Any) -> None:
    """Three-way output dispatch based on the ``--format`` CLI flag.

    Each output module exposes a ``REGISTRY`` dict mapping command names to
    their output functions. A missing formatter raises a runtime ``KeyError``
    when the command dispatches; ``_lookup_formatter`` traps that and re-raises
    a clear internal-error ``RuntimeError`` so the failure is diagnosable rather
    than surfacing as an opaque ``UNKNOWN_ERROR``.

    - ``rich``: ``querido.output.console.REGISTRY[command_name]``
    - ``html``: ``querido.output.html.REGISTRY[command_name]``
    - Otherwise: ``querido.output.formats.REGISTRY[command_name]``
    """
    from querido.cli._context import get_output_format

    fmt = get_output_format()
    if fmt == "rich":
        fn: Any = _lookup_formatter("querido.output.console", command_name)
        fn(*args, **kwargs)
    elif fmt == "html":
        from querido.cli._context import emit_html

        fn = _lookup_formatter("querido.output.html", command_name)
        html = fn(*args, **kwargs)
        emit_html(html)
    else:
        # Envelope-emitting commands short-circuit in the CLI layer before
        # reaching dispatch_output for json (see for_<cmd> rules in
        # querido.core.next_steps).
        fn = _lookup_formatter("querido.output.formats", command_name)
        text = fn(*args, fmt, **kwargs)
        print(text)
