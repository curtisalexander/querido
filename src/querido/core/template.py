from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def get_template(connector: Connector, table: str, *, sample_values: int = 3) -> dict:
    """Generate a documentation template for *table*.

    Orchestrates inspect + profile + preview queries to build a template
    with auto-populated metadata and placeholder fields.

    Returns::

        {
            "table": str,
            "table_comment": str,
            "row_count": int,
            "columns": [{"name": ..., "type": ..., ...}, ...],
        }
    """
    from querido.connectors.base import validate_column_name
    from querido.core.profile import is_numeric_type
    from querido.sql.renderer import render_template

    columns = connector.get_columns(table)
    table_comment = connector.get_table_comment(table)

    count_sql = render_template("count", connector.dialect, table=table)
    row_count = connector.execute(count_sql)[0]["cnt"]

    col_info = [
        {
            "name": validate_column_name(c["name"]),
            "type": c["type"],
            "numeric": is_numeric_type(c["type"]),
        }
        for c in columns
    ]
    profile_sql = render_template(
        "profile", connector.dialect, columns=col_info, source=table, approx=True
    )
    profile_data = connector.execute(profile_sql)

    # Snowflake single-scan template returns one wide row; reshape it.
    if profile_data and len(profile_data) == 1 and "total_rows" in profile_data[0]:
        from querido.core.profile import _unpack_single_row

        profile_data = _unpack_single_row(profile_data[0], col_info)

    profile_by_col: dict[str, dict] = {}
    for row in profile_data:
        profile_by_col[row["column_name"]] = row

    sample_rows: list[dict] = []
    if sample_values > 0:
        preview_sql = render_template(
            "preview", connector.dialect, table=table, limit=sample_values
        )
        sample_rows = connector.execute(preview_sql)

    template_rows: list[dict] = []
    for col in columns:
        name = col["name"]
        stats = profile_by_col.get(name, {})

        samples: list[str] = []
        if sample_rows:
            for row in sample_rows:
                val = row.get(name)
                if val is not None:
                    samples.append(str(val))

        template_rows.append(
            {
                "name": name,
                "type": col["type"],
                "nullable": col["nullable"],
                "primary_key": col.get("primary_key", False),
                "comment": col.get("comment") or "",
                "distinct_count": stats.get("distinct_count"),
                "null_count": stats.get("null_count"),
                "null_pct": stats.get("null_pct"),
                "min_val": stats.get("min_val"),
                "max_val": stats.get("max_val"),
                "min_length": stats.get("min_length"),
                "max_length": stats.get("max_length"),
                "sample_values": ", ".join(samples) if samples else "",
            }
        )

    return {
        "table": table,
        "table_comment": table_comment or "",
        "row_count": row_count,
        "columns": template_rows,
    }
