"""Snowflake semantic model builders.

``build_semantic_view_ddl`` emits ``create semantic view`` DDL — the native
successor to stage-based Cortex Analyst YAML models — and is what
``qdo snowflake semantic`` produces.  ``build_semantic_yaml`` emits the
legacy stage YAML and remains only for ``qdo template --format yaml``.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from querido.connectors.base import ConnectorError

if TYPE_CHECKING:
    from querido.connectors.base import Connector


_AGG_AVG_KEYWORDS = ("rate", "pct", "percent", "ratio", "avg", "average", "mean")


def _fetch_error_types() -> tuple[type[Exception], ...]:
    """Exception types that should trigger the sample-value fallback path.

    Connectors wrap recognized driver errors in :class:`ConnectorError`
    subclasses, but ``wrap_driver_error`` returns ``None`` for unrecognized
    messages (e.g. dialect syntax quirks) and the original driver exception
    is re-raised unwrapped — so the raw driver base errors must be caught
    too.  Driver modules are imported lazily; absent drivers can't be the
    active connector, so their error types are simply omitted.
    """
    import sqlite3

    errors: list[type[Exception]] = [
        ConnectorError,
        sqlite3.Error,
        ValueError,
        LookupError,
        OSError,
        RuntimeError,
    ]
    try:
        import duckdb

        errors.append(duckdb.Error)
    except ImportError:
        pass
    try:
        import snowflake.connector  # type: ignore[import-not-found]

        sf_error = snowflake.connector.Error
    except (ImportError, AttributeError):
        pass
    else:
        errors.append(sf_error)
    return tuple(errors)


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
        except _fetch_error_types():
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
    from querido.connectors.base import quote_qualified_name

    quoted_table = quote_qualified_name(table)
    safe_limit = int(limit)
    # Each branch is wrapped in a subquery so the per-branch limit is legal
    # on all dialects (SQLite rejects a bare "limit" before "union all").
    parts = [
        f"select * from ("
        f"select '{col_name}' as col_name, "
        f'cast("{col_name}" as varchar) as val '
        f"from {quoted_table} "
        f'where "{col_name}" is not null '
        f'group by "{col_name}" '
        f"limit {safe_limit})"
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
    from querido.connectors.base import quote_qualified_name

    quoted_table = quote_qualified_name(table)

    def _fetch_one(col_name: str) -> tuple[str, list[str]]:
        sql = (
            f'select distinct "{col_name}" as val '
            f"from {quoted_table} "
            f'where "{col_name}" is not null '
            f"limit {int(limit)}"
        )
        try:
            rows = connector.execute(sql)
            return col_name, [str(r.get("val", "")) for r in rows if r.get("val") is not None]
        except _fetch_error_types():
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


def _sql_str(value: str) -> str:
    """Render a string as a single-quoted SQL literal."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def build_semantic_view_ddl(
    table: str,
    columns: list[dict],
    table_comment: str | None,
    *,
    sample_values_per_col: dict[str, list[str]] | None = None,
) -> str:
    """Build a ``create semantic view`` DDL statement from table metadata.

    Semantic views are the native successor to stage-based Cortex Analyst
    YAML models — Snowflake's docs call the YAML path the "legacy stage
    API" and recommend semantic views for all new implementations.  Clause
    order is fixed by the syntax (tables, facts, dimensions, metrics) and
    at least one dimension or metric must be present.

    Measure columns become facts plus an auto-generated metric
    (``sum_<col>`` / ``avg_<col>`` per :func:`_infer_aggregation`);
    dimension and time-dimension columns become dimensions.  Descriptions
    and sample values travel in item comments; synonyms are deliberately
    left to a human review pass (a placeholder synonym would execute).

    Parameters mirror :func:`build_semantic_yaml`.
    """
    from querido.core._utils import classify_column_kind

    short_name = table.rsplit(".", 1)[-1]
    alias = short_name.lower()
    desc = table_comment or f"Semantic view for {table}"
    samples = sample_values_per_col or {}

    dimensions: list[dict] = []
    measures: list[dict] = []
    for col in columns:
        if classify_column_kind(col) == "measure":
            measures.append(col)
        else:
            # Semantic views have no separate time-dimension concept;
            # time dimensions are plain dimensions.
            dimensions.append(col)

    def _comment_for(col: dict) -> str | None:
        parts: list[str] = []
        comment = col.get("comment")
        if comment:
            text = str(comment)
            parts.append(text if text.endswith(".") else f"{text}.")
        col_samples = samples.get(col.get("name", ""), [])
        if col_samples:
            shown = ", ".join(str(v) for v in col_samples[:10])
            parts.append(f"Sample values: {shown}.")
        return " ".join(parts) if parts else None

    def _item(name: str, expr: str, comment: str | None) -> str:
        lines = [f"    {alias}.{name} as {expr}"]
        if comment:
            lines.append(f"      comment = {_sql_str(comment)}")
        return "\n".join(lines)

    buf = io.StringIO()
    buf.write(f"create or replace semantic view {alias}_semantic_view\n")

    buf.write("  tables (\n")
    buf.write(f"    {alias} as {table}\n")
    pk_cols = [str(c.get("name", "")) for c in columns if c.get("primary_key")]
    if pk_cols:
        buf.write(f"      primary key ({', '.join(pk_cols)})\n")
    buf.write(f"      comment = {_sql_str(desc)}\n")
    buf.write("  )\n")

    if measures:
        buf.write("  facts (\n")
        items = [
            _item(str(c.get("name", "")).lower(), str(c.get("name", "")), _comment_for(c))
            for c in measures
        ]
        buf.write(",\n".join(items) + "\n")
        buf.write("  )\n")

    if dimensions:
        buf.write("  dimensions (\n")
        items = [
            _item(str(c.get("name", "")).lower(), str(c.get("name", "")), _comment_for(c))
            for c in dimensions
        ]
        buf.write(",\n".join(items) + "\n")
        buf.write("  )\n")

    if measures:
        buf.write("  metrics (\n")
        items = []
        for col in measures:
            name = str(col.get("name", "")).lower()
            agg = _infer_aggregation(col)
            label = "Average" if agg == "avg" else "Total"
            items.append(
                _item(
                    f"{agg}_{name}",
                    f"{agg}({name})",
                    f"{label} {name} (auto-generated; review before use)",
                )
            )
        buf.write(",\n".join(items) + "\n")
        buf.write("  )\n")

    buf.write(f"  comment = {_sql_str(desc)}\n")
    buf.write(";\n")

    # Guidance for finishing the model after review.
    buf.write("\n")
    buf.write("-- Synonyms are informational aids for Cortex Analyst; add them per item\n")
    buf.write("-- after review, e.g.:\n")
    buf.write(f"--   {alias}.status as status with synonyms ('state', 'order state')\n")
    buf.write("-- Multi-table models: add entries under tables (...) and declare joins in\n")
    buf.write("-- a relationships (...) clause between tables (...) and facts (...), e.g.:\n")
    buf.write(f"--   relationships ( {alias} (dim_id) references dim_table )\n")

    return buf.getvalue()
