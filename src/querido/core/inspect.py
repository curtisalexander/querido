from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def get_inspect(connector: Connector, table: str, *, verbose: bool = False) -> dict:
    """Return column metadata and row count for *table*.

    Returns::

        {
            "columns": [{"name": ..., "type": ..., "nullable": ..., ...}, ...],
            "row_count": int,
            "table_comment": str | None,
        }
    """
    from querido.sql.renderer import render_template

    columns = connector.get_columns(table)

    count_sql = render_template("count", connector.dialect, table=table)
    row_count = connector.execute(count_sql)[0]["cnt"]

    table_comment = None
    if verbose:
        table_comment = connector.get_table_comment(table)

    return {
        "columns": columns,
        "row_count": row_count,
        "table_comment": table_comment,
    }
