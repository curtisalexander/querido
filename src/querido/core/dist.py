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
    column_type: str | None = None,
) -> dict:
    """Compute distribution for a column.

    Returns a dict with keys:
      - table, column, column_type, mode ("numeric" or "categorical")
      - total_rows, null_count
      - buckets (list, numeric mode) or values (list, categorical mode)

    When *column_type* is provided, the ``get_columns()`` lookup is skipped.
    """
    from querido.core.profile import is_numeric_type
    from querido.sql.renderer import render_template

    col_type = column_type
    if col_type is None:
        col_meta = connector.get_columns(table)
        col_type = next((c["type"] for c in col_meta if c["name"].lower() == column.lower()), None)
        if col_type is None:
            available = ", ".join(c["name"] for c in col_meta)
            raise ValueError(
                f"Column '{column}' not found in table '{table}'. Available columns: {available}"
            )
    is_num = is_numeric_type(col_type)

    if is_num:
        sql = render_template(
            "dist", connector.dialect, column=column, source=table, buckets=buckets
        )
        data = connector.execute(sql)
        # Dist templates now include total_rows and null_count in each row
        total_rows = data[0]["total_rows"] if data else 0
        null_count = data[0]["null_count"] if data else 0
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
        null_sql = render_template("null_count", connector.dialect, column=column, table=table)
        null_result = connector.execute(null_sql)
        total_rows = null_result[0]["total"]
        null_count = null_result[0]["null_count"]

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
