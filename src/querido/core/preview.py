from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def get_preview(connector: Connector, table: str, limit: int = 20) -> list[dict]:
    """Return up to *limit* rows from *table*.

    Returns a list of row dicts (column-name → value).
    Uses the Arrow fast path when available.
    """
    from querido.connectors.arrow_util import arrow_to_dicts, execute_arrow_or_dicts
    from querido.sql.renderer import render_template

    sql = render_template("preview", connector.dialect, table=table, limit=limit)
    data, is_arrow = execute_arrow_or_dicts(connector, sql)
    return arrow_to_dicts(data, is_arrow)
