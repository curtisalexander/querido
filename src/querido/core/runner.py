"""Threaded query runner with cancellation support."""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from querido.connectors.base import Connector

T = TypeVar("T")


class QueryCancelled(KeyboardInterrupt):
    """Raised when a running query is cancelled via Ctrl-C or explicit cancel."""

    def __init__(self, elapsed: float = 0.0) -> None:
        self.elapsed = elapsed
        super().__init__(f"Query cancelled after {elapsed:.1f}s")


@dataclass
class QueryResult(dict[str, object]):
    """Thin wrapper carrying query result and elapsed time."""

    # We don't actually subclass dict — we just store result + elapsed.
    pass


def run_cancellable[T](
    fn: Callable[..., T],
    *args: object,
    connector: Connector | None = None,
    **kwargs: object,
) -> tuple[T, float]:
    """Execute *fn(*args, **kwargs)* in a background thread.

    Returns ``(result, elapsed_seconds)``.

    If the calling thread receives a ``KeyboardInterrupt`` while waiting, the
    connector's ``cancel()`` method is called (if available) to abort the
    in-flight query, and ``QueryCancelled`` is raised.
    """
    result_box: list[T] = []
    error_box: list[BaseException] = []

    def _target() -> None:
        try:
            result_box.append(fn(*args, **kwargs))
        except BaseException as exc:
            error_box.append(exc)

    t0 = time.monotonic()
    thread = threading.Thread(target=_target, daemon=True)
    thread.start()

    try:
        # Join with short timeouts so KeyboardInterrupt is deliverable
        while thread.is_alive():
            thread.join(timeout=0.1)
    except KeyboardInterrupt:
        elapsed = time.monotonic() - t0
        # Attempt to cancel the in-flight query
        if connector is not None and hasattr(connector, "cancel"):
            with contextlib.suppress(Exception):
                connector.cancel()
        # Wait briefly for the thread to finish after cancel
        thread.join(timeout=2.0)
        raise QueryCancelled(elapsed) from None

    elapsed = time.monotonic() - t0

    if error_box:
        raise error_box[0]

    return result_box[0], elapsed
