from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def get_columns_and_count(
    connector: Connector, table: str
) -> tuple[list[dict], str | None, int, list[dict]]:
    """Fetch column metadata and row count for *table*.

    Returns ``(columns, table_comment, row_count, col_info)``.
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

    return columns, table_comment, row_count, col_info


def get_profile_stats(
    connector: Connector, table: str, col_info: list[dict], row_count: int
) -> list[dict]:
    """Run the profile query and return per-column statistics."""
    from querido.core.profile import _build_sample_source
    from querido.sql.renderer import render_template

    source, _sampled, _sample_size = _build_sample_source(connector, table, row_count)

    profile_sql = render_template(
        "profile", connector.dialect, columns=col_info, source=source, approx=True
    )
    profile_data = connector.execute(profile_sql)

    # Snowflake single-scan template returns one wide row; reshape it.
    if profile_data and len(profile_data) == 1 and "total_rows" in profile_data[0]:
        from querido.core.profile import _unpack_single_row

        profile_data = _unpack_single_row(profile_data[0], col_info)

    return profile_data


def get_sample_rows(connector: Connector, table: str, sample_values: int) -> list[dict]:
    """Fetch sample rows for *table*."""
    from querido.sql.renderer import render_template

    if sample_values <= 0:
        return []
    preview_sql = render_template("preview", connector.dialect, table=table, limit=sample_values)
    return connector.execute(preview_sql)


def assemble_template(
    columns: list[dict],
    table: str,
    table_comment: str | None,
    row_count: int,
    profile_data: list[dict],
    sample_rows: list[dict],
) -> dict:
    """Assemble the final template dict from pre-fetched data."""
    profile_by_col: dict[str, dict] = {}
    for row in profile_data:
        profile_by_col[row["column_name"]] = row

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


def get_template(connector: Connector, table: str, *, sample_values: int = 3) -> dict:
    """Generate a documentation template for *table*.

    Orchestrates inspect + profile + preview queries to build a template
    with auto-populated metadata and placeholder fields.  When the
    connector supports concurrent queries, the profile and sample queries
    run in parallel.

    Returns::

        {
            "table": str,
            "table_comment": str,
            "row_count": int,
            "columns": [{"name": ..., "type": ..., ...}, ...],
        }
    """
    columns, table_comment, row_count, col_info = get_columns_and_count(connector, table)

    concurrent = getattr(connector, "supports_concurrent_queries", False)
    if concurrent:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=2) as pool:
            profile_future = pool.submit(get_profile_stats, connector, table, col_info, row_count)
            sample_future = pool.submit(get_sample_rows, connector, table, sample_values)
            profile_data = profile_future.result()
            sample_rows = sample_future.result()
    else:
        profile_data = get_profile_stats(connector, table, col_info, row_count)
        sample_rows = get_sample_rows(connector, table, sample_values)

    return assemble_template(columns, table, table_comment, row_count, profile_data, sample_rows)
