"""Shared helpers for core analysis modules.

Extracted from ``profile.py`` to break the tight coupling where every other
core module depended on profile internals.
"""

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
    col_type = col.get("type", "").lower()
    col_name = col.get("name", "").lower()

    if any(kw in col_type for kw in ("date", "time", "timestamp")):
        return "time_dimension"
    if any(kw in col_name for kw in _TIME_KEYWORDS):
        return "time_dimension"

    if is_numeric_type(col_type) and not any(kw in col_name for kw in _ID_KEYWORDS):
        return "measure"

    return "dimension"


def classify_columns(
    stats: list[dict],
    col_info: list[dict],
    row_count: int,
) -> dict:
    """Classify profiled columns into categories based on Tier 1 stats.

    Returns a dict with:
    - ``categories``: ``{category_name: [col_name, ...]}``
    - ``column_category``: ``{col_name: category_name}``

    Categories (evaluated in priority order, first match wins):
    constant, sparse, high_cardinality, time, measure, low_cardinality, other.
    """
    # Build lookup: col_name -> stats row
    stats_by_name: dict[str, dict] = {}
    for s in stats:
        stats_by_name[s.get("column_name", "")] = s

    # Build lookup: col_name -> col_info entry
    info_by_name: dict[str, dict] = {}
    for c in col_info:
        info_by_name[c.get("name", "")] = c

    categories: dict[str, list[str]] = {
        "constant": [],
        "sparse": [],
        "high_cardinality": [],
        "time": [],
        "measure": [],
        "low_cardinality": [],
        "other": [],
    }
    column_category: dict[str, str] = {}

    for col in col_info:
        name = col.get("name", "")
        s = stats_by_name.get(name, {})
        distinct = s.get("distinct_count") or 0
        null_pct = s.get("null_pct") or 0

        # Priority order: first match wins
        if distinct == 1:
            cat = "constant"
        elif null_pct > 90:
            cat = "sparse"
        elif row_count > 0 and distinct / row_count > 0.95:
            cat = "high_cardinality"
        elif classify_column_kind(col) == "time_dimension":
            cat = "time"
        elif classify_column_kind(col) == "measure":
            cat = "measure"
        elif distinct < 50:
            cat = "low_cardinality"
        else:
            cat = "other"

        categories[cat].append(name)
        column_category[name] = cat

    # Remove empty categories
    categories = {k: v for k, v in categories.items() if v}

    return {"categories": categories, "column_category": column_category}


def build_col_info(columns: list[dict]) -> list[dict]:
    """Build the column info list used by profile SQL templates."""
    from querido.connectors.base import validate_column_name

    return [
        {
            "name": validate_column_name(c.get("name", "")),
            "type": c.get("type", ""),
            "numeric": is_numeric_type(c.get("type", "")),
        }
        for c in columns
    ]


def build_sample_source(
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

    import os

    auto_threshold = int(os.environ.get("QDO_SAMPLE_THRESHOLD", "1000000"))
    if sample is not None:
        sample_size = sample
    elif row_count > auto_threshold:
        sample_size = 100_000

    if sample_size is not None and sample_size < row_count:
        source = connector.sample_source(table, sample_size, row_count=row_count)
        sampled = True

    return source, sampled, sample_size


def unpack_single_row(row: dict, col_info: list[dict]) -> list[dict]:
    """Reshape a single wide row into per-column stat dicts.

    The Snowflake single-scan profile template produces one row with
    prefixed column names like ``COL__null_count``.  This function
    unpacks that into the standard list-of-dicts format expected by all
    downstream consumers.
    """
    total_rows = row.get("total_rows", 0)
    stats: list[dict] = []
    for col in col_info:
        name = col.get("name", "")
        prefix = f"{name}__".lower()
        entry: dict = {
            "column_name": name,
            "column_type": col.get("type", ""),
            "total_rows": total_rows,
            "null_count": row.get(f"{prefix}null_count"),
            "null_pct": row.get(f"{prefix}null_pct"),
            "distinct_count": row.get(f"{prefix}distinct_count"),
        }
        if col.get("numeric"):
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
