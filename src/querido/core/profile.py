from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector

NUMERIC_TYPE_PREFIXES = (
    "int",
    "integer",
    "bigint",
    "smallint",
    "tinyint",
    "float",
    "double",
    "real",
    "decimal",
    "numeric",
    "number",
    "hugeint",
)


def is_numeric_type(type_str: str) -> bool:
    """Return True if the SQL type string represents a numeric type."""
    return type_str.lower().startswith(NUMERIC_TYPE_PREFIXES)


def _build_col_info(columns: list[dict]) -> list[dict]:
    """Build the column info list used by profile SQL templates."""
    from querido.connectors.base import validate_column_name

    return [
        {
            "name": validate_column_name(c["name"]),
            "type": c["type"],
            "numeric": is_numeric_type(c["type"]),
        }
        for c in columns
    ]


def _build_sample_source(
    connector: Connector,
    table: str,
    row_count: int,
    *,
    sample: int | None = None,
    no_sample: bool = False,
) -> tuple[str, bool, int | None]:
    """Determine the source expression (table or sampled subquery).

    Returns ``(source, sampled, sample_size)``.
    """
    source = table
    sampled = False
    sample_size = None

    if no_sample:
        return source, sampled, sample_size

    auto_threshold = 1_000_000
    if sample is not None:
        sample_size = sample
    elif row_count > auto_threshold:
        sample_size = 100_000

    if sample_size is not None and sample_size < row_count:
        if connector.dialect == "duckdb":
            source = f"(SELECT * FROM {table} USING SAMPLE {sample_size}) AS _sample"
        elif connector.dialect == "snowflake":
            source = f"(SELECT * FROM {table} SAMPLE ({sample_size} ROWS)) AS _sample"
        else:
            source = f"(SELECT * FROM {table} ORDER BY RANDOM() LIMIT {sample_size}) AS _sample"
        sampled = True

    return source, sampled, sample_size


def get_profile(
    connector: Connector,
    table: str,
    *,
    columns: str | None = None,
    sample: int | None = None,
    no_sample: bool = False,
) -> dict:
    """Profile table columns and return statistics.

    Returns::

        {
            "stats": [{"column_name": ..., ...}, ...],
            "row_count": int,
            "sampled": bool,
            "sample_size": int | None,
        }
    """
    from querido.sql.renderer import render_template

    col_meta = connector.get_columns(table)

    if columns:
        filter_names = {c.strip().lower() for c in columns.split(",")}
        filtered = [c for c in col_meta if c["name"].lower() in filter_names]
        if not filtered:
            available = ", ".join(c["name"] for c in col_meta)
            raise ValueError(
                f"No matching columns found in '{table}'.\nAvailable columns: {available}"
            )
        col_meta = filtered

    col_info = _build_col_info(col_meta)

    count_sql = render_template("count", connector.dialect, table=table)
    row_count = connector.execute(count_sql)[0]["cnt"]

    source, sampled, sample_size = _build_sample_source(
        connector, table, row_count, sample=sample, no_sample=no_sample
    )

    sql = render_template("profile", connector.dialect, columns=col_info, source=source)
    stats = connector.execute(sql)

    return {
        "stats": stats,
        "row_count": row_count,
        "sampled": sampled,
        "sample_size": sample_size,
        "source": source,
        "col_info": col_info,
    }


def get_frequencies(
    connector: Connector,
    source: str,
    col_info: list[dict],
    top: int,
) -> dict[str, list[dict]]:
    """Return top-N frequency counts for each column.

    *source* is a table name or sampled subquery expression.
    *col_info* is the list from ``get_profile()["col_info"]``.
    """
    from querido.sql.renderer import render_template

    freq_data: dict[str, list[dict]] = {}
    for col in col_info:
        col_name = str(col["name"])
        freq_sql = render_template(
            "frequency",
            connector.dialect,
            column=col_name,
            source=source,
            top=top,
        )
        freq_data[col_name] = connector.execute(freq_sql)
    return freq_data
