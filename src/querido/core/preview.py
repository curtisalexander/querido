from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def get_preview(connector: Connector, table: str, limit: int = 20) -> list[dict]:
    """Return up to *limit* rows from *table*.

    Returns a list of row dicts (column-name → value).
    """
    from querido.sql.renderer import render_template

    sql = render_template("preview", connector.dialect, table=table, limit=limit)
    return connector.execute(sql)
