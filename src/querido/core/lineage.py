from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def get_view_definition(connector: Connector, view: str) -> dict:
    """Retrieve the SQL definition of a view.

    Returns::

        {"view": str, "dialect": str, "definition": str}

    Raises ``LookupError`` if *view* is not a view or does not exist.
    """
    sql_def = connector.get_view_definition(view)

    if sql_def is None:
        raise LookupError(f"'{view}' is not a view or does not exist.")

    return {
        "view": view,
        "dialect": connector.dialect,
        "definition": sql_def,
    }
