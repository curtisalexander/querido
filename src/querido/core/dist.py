from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def get_distribution(
    connector: Connector,
    table: str,
    column: str,
    *,
    buckets: int = 20,
    top: int = 20,
) -> dict:
    """Compute distribution for a column.

    Returns a dict with keys:
      - table, column, column_type, mode ("numeric" or "categorical")
      - total_rows, null_count
      - buckets (list, numeric mode) or values (list, categorical mode)
    """
    from querido.core.profile import is_numeric_type
    from querido.sql.renderer import render_template

    col_meta = connector.get_columns(table)
    col_type = next(c["type"] for c in col_meta if c["name"] == column)
    is_num = is_numeric_type(col_type)

    null_sql = render_template("null_count", connector.dialect, column=column, table=table)
    null_result = connector.execute(null_sql)
    total_rows = null_result[0]["total"]
    null_count = null_result[0]["null_count"]

    if is_num:
        sql = render_template(
            "dist", connector.dialect, column=column, source=table, buckets=buckets
        )
        data = connector.execute(sql)
        return {
            "table": table,
            "column": column,
            "column_type": col_type,
            "mode": "numeric",
            "total_rows": total_rows,
            "null_count": null_count,
            "buckets": data,
        }
    else:
        freq_sql = render_template(
            "frequency", connector.dialect, column=column, source=table, top=top
        )
        data = connector.execute(freq_sql)
        return {
            "table": table,
            "column": column,
            "column_type": col_type,
            "mode": "categorical",
            "total_rows": total_rows,
            "null_count": null_count,
            "values": data,
        }
