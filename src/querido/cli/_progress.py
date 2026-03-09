"""Elapsed-time query status with cancellation support for the CLI."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

    from rich.console import Console

    from querido.connectors.base import Connector


class _ElapsedStatus:
    """Tracks elapsed time for a running query."""

    def __init__(self) -> None:
        self.elapsed: float = 0.0


@contextmanager
def query_status(
    console: Console,
    message: str,
    connector: Connector | None = None,
    *,
    show_elapsed_threshold: float = 1.0,
) -> Generator[_ElapsedStatus, None, None]:
    """Show a Rich spinner with elapsed time; cancel the query on Ctrl-C.

    Usage::

        with query_status(console, "Profiling orders", connector) as qs:
            data = get_profile(connector, table)
        # qs.elapsed has wall-clock seconds

    The spinner updates every second to show elapsed time, e.g.::

        ⠋ Profiling orders… (3s)

    On ``KeyboardInterrupt`` the connector's ``cancel()`` is called, a clean
    message is printed, and ``QueryCancelled`` is raised.

    After a successful return, if *elapsed* exceeds *show_elapsed_threshold*
    a timing line is printed to stderr.
    """
    from querido.core.runner import QueryCancelled

    status = _ElapsedStatus()
    t0 = time.monotonic()
    stop_event = threading.Event()

    # Use Rich Live to update the spinner text with elapsed seconds
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.text import Text

    spinner = Spinner("dots", text=Text.from_markup(f"{message}…"))
    live = Live(spinner, console=console, transient=True, refresh_per_second=4)

    def _update_loop() -> None:
        """Background thread that updates the spinner text with elapsed time."""
        while not stop_event.wait(1.0):
            elapsed = time.monotonic() - t0
            spinner.text = Text.from_markup(f"{message}… ({elapsed:.0f}s)")

    updater = threading.Thread(target=_update_loop, daemon=True)

    try:
        live.start()
        updater.start()
        yield status
    except KeyboardInterrupt:
        status.elapsed = time.monotonic() - t0
        stop_event.set()
        live.stop()
        # Cancel the in-flight query
        if connector is not None and hasattr(connector, "cancel"):
            with suppress(Exception):
                connector.cancel()
        console.print(
            f"\n[yellow]Query cancelled[/yellow] after {status.elapsed:.1f}s",
            highlight=False,
        )
        raise QueryCancelled(status.elapsed) from None
    finally:
        status.elapsed = time.monotonic() - t0
        stop_event.set()
        live.stop()

    # Print elapsed time for longer queries (only on a real terminal to avoid
    # polluting piped or captured output)
    if status.elapsed >= show_elapsed_threshold and console.is_terminal:
        console.print(
            f"[dim]Completed in {status.elapsed:.1f}s[/dim]",
            highlight=False,
        )
