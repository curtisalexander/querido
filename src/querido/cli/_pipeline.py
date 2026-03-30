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
    check_exists: bool = True,
) -> Generator[CommandContext]:
    """Context manager that handles the common CLI command setup.

    Validates the table name, resolves the connection, creates a connector,
    optionally checks that the table exists, and yields a ``CommandContext``
    with the connector, console, and a ``spin()`` helper for query spinners.

    Usage::

        with table_command(table=t, connection=c, db_type=d) as ctx:
            with ctx.spin("Loading preview"):
                data = get_preview(ctx.connector, t, limit=20)
            dispatch_output("preview", t, data, 20)
    """
    from querido.cli._validation import check_table_exists as _check
    from querido.config import resolve_connection
    from querido.connectors.base import validate_table_name
    from querido.connectors.factory import create_connector

    validate_table_name(table)
    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        from rich.console import Console

        console = Console(stderr=True)

        if check_exists:
            _check(connector, table)

        yield CommandContext(connector=connector, console=console)


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
