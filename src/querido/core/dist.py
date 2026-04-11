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
    sample: int | None = None,
    no_sample: bool = False,
) -> dict:
    """Compute distribution for a column.

    Returns a dict with keys:
      - table, column, column_type, mode ("numeric" or "categorical")
      - total_rows, null_count
      - sampled, sample_size
      - buckets (list, numeric mode) or values (list, categorical mode)

    When *column_type* is provided, the ``get_columns()`` lookup is skipped.

    Sampling is applied automatically for tables over 1M rows (same
    threshold as ``profile``).  Use *sample* to set an explicit sample
    size, or *no_sample* to force a full scan.
    """
    from querido.core._utils import (
        build_sample_source,
        is_numeric_type,
        resolve_row_count_for_sampling,
    )
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

    # Determine source (raw table or sampled subquery).
    row_count = resolve_row_count_for_sampling(
        connector, table, sample=sample, no_sample=no_sample
    )
    source, sampled, sample_size = build_sample_source(
        connector, table, row_count, sample=sample, no_sample=no_sample
    )

    if is_num:
        sql = render_template(
            "dist", connector.dialect, column=column, source=source, buckets=buckets
        )
        data = connector.execute(sql)
        total_rows = data[0]["total_rows"] if data else 0
        null_count = data[0]["null_count"] if data else 0
        return {
            "table": table,
            "column": column,
            "column_type": col_type,
            "mode": "numeric",
            "total_rows": total_rows,
            "null_count": null_count,
            "sampled": sampled,
            "sample_size": sample_size,
            "buckets": data,
        }
    else:
        freq_sql = render_template(
            "frequency", connector.dialect, column=column, source=source, top=top
        )
        data = connector.execute(freq_sql)
        total_rows = data[0]["total_rows"] if data else 0
        null_count = data[0]["null_count"] if data else 0
        _strip = {"total_rows", "null_count"}
        values = [{k: v for k, v in row.items() if k not in _strip} for row in data]
        return {
            "table": table,
            "column": column,
            "column_type": col_type,
            "mode": "categorical",
            "total_rows": total_rows,
            "null_count": null_count,
            "sampled": sampled,
            "sample_size": sample_size,
            "values": values,
        }
