"""Snowflake Cortex Analyst semantic model YAML generation.

Shared builder used by both ``qdo template --format yaml`` and
``qdo snowflake semantic``.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


_AGG_AVG_KEYWORDS = ("rate", "pct", "percent", "ratio", "avg", "average", "mean")


def _infer_aggregation(col: dict) -> str:
    """Infer a sensible default_aggregation for a measure column."""
    name = col["name"].lower()
    if any(kw in name for kw in _AGG_AVG_KEYWORDS):
        return "avg"
    return "sum"


def _parse_base_table(table: str) -> str:
    """Format the base_table YAML block.

    Qualified names (``database.schema.table``) produce the structured
    ``database`` / ``schema`` / ``table`` format that Cortex Analyst expects.
    Bare names are emitted as a flat string.
    """
    parts = table.split(".")
    if len(parts) == 3:
        db, schema, tbl = parts
        ind = "    "
        return f"\n{ind}  database: {db}\n{ind}  schema: {schema}\n{ind}  table: {tbl}"
    return f" {table}"


def get_sample_values(
    connector: Connector,
    table: str,
    columns: list[dict],
    *,
    limit: int = 25,
) -> dict[str, list[str]]:
    """Fetch distinct non-null sample values for each column.

    Returns ``{col_name: [val_str, ...]}``.

    Uses a single UNION ALL query to fetch sample values for all columns
    in one round-trip, avoiding N separate queries.  Falls back to
    per-column queries (with optional concurrency) if the batched query
    fails.
    """
    from querido.connectors.base import validate_column_name, validate_table_name

    validate_table_name(table)
    col_names = [c["name"] for c in columns]
    for name in col_names:
        validate_column_name(name)

    # --- Batched path: single UNION ALL query --------------------------------
    if col_names:
        try:
            return _fetch_batched(connector, table, col_names, limit)
        except (ValueError, LookupError, OSError, RuntimeError):
            pass  # fall through to per-column path

    # --- Fallback: per-column queries ----------------------------------------
    return _fetch_per_column(connector, table, col_names, limit)


def _fetch_batched(
    connector: Connector,
    table: str,
    col_names: list[str],
    limit: int,
) -> dict[str, list[str]]:
    """Fetch sample values for all columns in a single UNION ALL query."""
    safe_limit = int(limit)
    parts = [
        f'select \'{col_name}\' as col_name, '
        f'cast("{col_name}" as varchar) as val '
        f'from "{table}" '
        f'where "{col_name}" is not null '
        f'group by "{col_name}" '
        f"limit {safe_limit}"
        for col_name in col_names
    ]
    sql = " union all ".join(parts)
    rows = connector.execute(sql)

    result: dict[str, list[str]] = {name: [] for name in col_names}
    for row in rows:
        name = row.get("col_name", "")
        val = row.get("val")
        if name in result and val is not None:
            result[name].append(str(val))
    return result


def _fetch_per_column(
    connector: Connector,
    table: str,
    col_names: list[str],
    limit: int,
) -> dict[str, list[str]]:
    """Fetch sample values one column at a time, with optional concurrency."""

    def _fetch_one(col_name: str) -> tuple[str, list[str]]:
        sql = (
            f'select distinct "{col_name}" as val '
            f'from "{table}" '
            f'where "{col_name}" is not null '
            f"limit {int(limit)}"
        )
        try:
            rows = connector.execute(sql)
            return col_name, [str(r.get("val", "")) for r in rows if r.get("val") is not None]
        except (ValueError, LookupError, OSError, RuntimeError):
            return col_name, []

    concurrent = getattr(connector, "supports_concurrent_queries", False)

    if concurrent and len(col_names) > 1:
        from querido.core._concurrent import run_parallel

        return run_parallel(col_names, _fetch_one)

    return dict(_fetch_one(n) for n in col_names)


def build_semantic_yaml(
    table: str,
    columns: list[dict],
    table_comment: str | None,
    *,
    sample_values_per_col: dict[str, list[str]] | None = None,
) -> str:
    """Build a Cortex Analyst semantic model YAML string.

    Parameters
    ----------
    table:
        Table name (may be fully qualified as ``database.schema.table``).
    columns:
        Column metadata dicts with at least ``name`` and ``type`` keys.
    table_comment:
        Optional table-level comment/description.
    sample_values_per_col:
        Optional dict mapping column names to lists of sample value strings.
    """
    from querido.core._utils import classify_column_kind
    from querido.output.formats import yaml_escape

    buf = io.StringIO()
    ind = "  "

    short_name = table.rsplit(".", 1)[-1]
    desc = table_comment or f"Semantic model for {table}"

    buf.write(f"name: {short_name.lower()}_semantic_model\n")
    buf.write(f"description: {yaml_escape(desc)}\n")
    buf.write("\n")
    buf.write("tables:\n")
    buf.write(f"{ind}- name: {short_name}\n")
    buf.write(f"{ind}  base_table:{_parse_base_table(table)}\n")
    buf.write(f"{ind}  description: {yaml_escape(desc)}\n")

    # Classify columns
    dimensions: list[dict] = []
    time_dimensions: list[dict] = []
    measures: list[dict] = []
    for col in columns:
        kind = classify_column_kind(col)
        if kind == "time_dimension":
            time_dimensions.append(col)
        elif kind == "measure":
            measures.append(col)
        else:
            dimensions.append(col)

    samples = sample_values_per_col or {}

    def _write_col(col: dict, *, is_measure: bool = False) -> None:
        prefix = ind * 2
        col_desc = col.get("comment") or "<description>"
        buf.write(f"{prefix}- name: {col['name']}\n")
        buf.write(f"{prefix}  expr: {col['name']}\n")
        buf.write(f"{prefix}  data_type: {col['type']}\n")
        buf.write(f"{prefix}  description: {yaml_escape(col_desc)}\n")
        buf.write(f"{prefix}  synonyms:\n")
        buf.write(f"{prefix}    - <synonym>\n")
        if is_measure:
            buf.write(f"{prefix}  default_aggregation: {_infer_aggregation(col)}\n")
        col_samples = samples.get(col["name"], [])
        if col_samples:
            buf.write(f"{prefix}  sample_values:\n")
            for val in col_samples:
                buf.write(f"{prefix}    - {yaml_escape(str(val))}\n")

    if dimensions:
        buf.write(f"\n{ind}  dimensions:\n")
        for col in dimensions:
            _write_col(col)

    if time_dimensions:
        buf.write(f"\n{ind}  time_dimensions:\n")
        for col in time_dimensions:
            _write_col(col)

    if measures:
        buf.write(f"\n{ind}  measures:\n")
        for col in measures:
            _write_col(col, is_measure=True)

    # Stubs for verified_queries and filters
    buf.write("\n")
    buf.write("# verified_queries:\n")
    buf.write("#   - name: example_query\n")
    buf.write("#     question: What is the total revenue by region?\n")
    buf.write("#     sql: select region, sum(revenue) from ... group by region\n")
    buf.write("#     verified_by: <your_name>\n")
    buf.write("\n")
    buf.write("# filters:\n")
    buf.write("#   - name: recent_data\n")
    buf.write("#     description: Filter to last 12 months\n")
    buf.write("#     expr: date_column >= dateadd(month, -12, current_date())\n")

    return buf.getvalue()
