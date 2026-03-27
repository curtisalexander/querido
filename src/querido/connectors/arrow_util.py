"""Utilities for working with Arrow-capable connectors.

These helpers let core functions opportunistically use Arrow tables
without requiring every connector to implement ``execute_arrow()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def execute_arrow_or_dicts(
    connector: Connector,
    sql: str,
    params: dict | tuple | None = None,
) -> tuple[Any, bool]:
    """Try the Arrow path, fall back to ``execute()``.

    Returns ``(data, is_arrow)`` where *data* is either a PyArrow Table
    or a ``list[dict]``.
    """
    execute_arrow = getattr(connector, "execute_arrow", None)
    if execute_arrow is not None:
        try:
            table = execute_arrow(sql, params)
            return table, True
        except (ImportError, NotImplementedError, RuntimeError):
            pass
    return connector.execute(sql, params), False


def arrow_to_dicts(data: Any, is_arrow: bool) -> list[dict]:
    """Convert *data* to ``list[dict]`` if it came from the Arrow path."""
    if is_arrow:
        return data.to_pylist()
    return data
