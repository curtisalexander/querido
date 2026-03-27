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


_TIME_KEYWORDS = ("date", "time", "timestamp", "created", "updated", "modified")
_ID_KEYWORDS = ("_id", "_key", "_pk", "_fk", "_code", "_num")


def classify_column_kind(col: dict) -> str:
    """Classify a column as 'dimension', 'time_dimension', or 'measure'.

    Uses the column's ``type`` and ``name`` keys to infer the semantic role.
    """
    col_type = col["type"].lower()
    col_name = col["name"].lower()

    if any(kw in col_type for kw in ("date", "time", "timestamp")):
        return "time_dimension"
    if any(kw in col_name for kw in _TIME_KEYWORDS):
        return "time_dimension"

    if is_numeric_type(col_type) and not any(kw in col_name for kw in _ID_KEYWORDS):
        return "measure"

    return "dimension"


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


def _unpack_single_row(row: dict, col_info: list[dict]) -> list[dict]:
    """Reshape a single wide row into per-column stat dicts.

    The Snowflake single-scan profile template produces one row with
    prefixed column names like ``COL__null_count``.  This function
    unpacks that into the standard list-of-dicts format expected by all
    downstream consumers.
    """
    total_rows = row.get("total_rows", 0)
    stats: list[dict] = []
    for col in col_info:
        name = col["name"]
        prefix = f"{name}__".lower()
        entry: dict = {
            "column_name": name,
            "column_type": col["type"],
            "total_rows": total_rows,
            "null_count": row.get(f"{prefix}null_count"),
            "null_pct": row.get(f"{prefix}null_pct"),
            "distinct_count": row.get(f"{prefix}distinct_count"),
        }
        if col["numeric"]:
            entry["min_val"] = row.get(f"{prefix}min_val")
            entry["max_val"] = row.get(f"{prefix}max_val")
            entry["mean_val"] = row.get(f"{prefix}mean_val")
            entry["median_val"] = row.get(f"{prefix}median_val")
            entry["stddev_val"] = row.get(f"{prefix}stddev_val")
            entry["min_length"] = None
            entry["max_length"] = None
        else:
            entry["min_val"] = None
            entry["max_val"] = None
            entry["mean_val"] = None
            entry["median_val"] = None
            entry["stddev_val"] = None
            entry["min_length"] = row.get(f"{prefix}min_length")
            entry["max_length"] = row.get(f"{prefix}max_length")
        stats.append(entry)
    return stats


def get_profile(
    connector: Connector,
    table: str,
    *,
    columns: str | None = None,
    sample: int | None = None,
    no_sample: bool = False,
    exact: bool = False,
) -> dict:
    """Profile table columns and return statistics.

    When *exact* is ``False`` (the default) and the connector dialect is
    Snowflake, ``APPROX_COUNT_DISTINCT`` is used for faster cardinality
    estimation.  Pass ``exact=True`` to use exact ``COUNT(DISTINCT)``.

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

    approx = not exact
    sql = render_template(
        "profile", connector.dialect, columns=col_info, source=source, approx=approx
    )
    raw = connector.execute(sql)

    # The Snowflake template produces a single wide row; reshape it.
    if raw and len(raw) == 1 and "total_rows" in raw[0]:
        stats = _unpack_single_row(raw[0], col_info)
    else:
        stats = raw

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

    When the connector supports concurrent queries (e.g. Snowflake),
    frequency queries are executed in parallel using a thread pool.
    """
    from querido.sql.renderer import render_template

    def _fetch_one(col: dict) -> tuple[str, list[dict]]:
        col_name = str(col["name"])
        freq_sql = render_template(
            "frequency",
            connector.dialect,
            column=col_name,
            source=source,
            top=top,
        )
        return col_name, connector.execute(freq_sql)

    concurrent = getattr(connector, "supports_concurrent_queries", False)

    if concurrent and len(col_info) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        freq_data: dict[str, list[dict]] = {}
        max_workers = min(len(col_info), 4)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_fetch_one, col): col for col in col_info}
            for future in as_completed(futures):
                col_name, rows = future.result()
                freq_data[col_name] = rows
        return freq_data

    return {name: rows for name, rows in (_fetch_one(col) for col in col_info)}
