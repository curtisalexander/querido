"""Table context — schema, stats, sample values, and metadata in one call.

For DuckDB and Snowflake, stats and sample values are fetched in a single
SQL scan using approx_top_k.  For SQLite, the profile query (one scan) is
followed by per-column frequency queries.

Stored metadata (.qdo/metadata/) is loaded from disk concurrently with the
database queries using a background thread.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector

# Dialects that support approx_top_k in one scan
_TOP_K_DIALECTS = frozenset({"duckdb", "snowflake"})


def get_context(
    connector: Connector,
    table: str,
    connection: str,
    *,
    sample_values: int = 5,
    no_sample: bool = False,
    sample: int | None = None,
    exact: bool = False,
) -> dict:
    """Return rich context for a table: schema, stats, sample values, metadata.

    Performance strategy
    --------------------
    * DuckDB / Snowflake: a single SQL scan computes all column stats **and**
      top-K sample values via ``approx_top_k``.  Zero extra queries.
    * SQLite: one profile scan (all stats) + per-column frequency queries if
      ``sample_values > 0``.  Frequencies are run sequentially (SQLite is
      single-writer).
    * Stored metadata is loaded from disk in a background thread so it never
      adds to query latency.

    Returns
    -------
    dict with keys:
        table, dialect, connection, row_count, sampled, sample_size,
        table_comment, table_description, columns (list), metadata (dict|None)

    Stored metadata is read best-effort: unreadable YAML, permission errors,
    or a missing file all degrade silently to ``metadata=None`` / empty
    per-column overlays rather than failing the command. Agents relying on
    the metadata merge should tolerate its absence.
    """
    from querido.connectors.base import validate_table_name
    from querido.core._utils import (
        build_col_info,
        build_sample_source,
        resolve_row_count_for_sampling,
    )

    validate_table_name(table)

    col_meta = connector.get_columns(table)
    col_info = build_col_info(col_meta)

    # --- Determine sampling --------------------------------------------------
    row_count_for_sample = resolve_row_count_for_sampling(
        connector, table, sample=sample, no_sample=no_sample
    )
    source, sampled, sample_size = build_sample_source(
        connector, table, row_count_for_sample, sample=sample, no_sample=no_sample
    )

    # --- Start metadata load in background -----------------------------------
    # Loaded twice: the raw YAML for table-level fields, and the per-column
    # surfaceable map that unwraps provenance to plain values.
    meta_future = None
    col_meta_future = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        meta_future = executor.submit(_load_metadata, connection, table)
        col_meta_future = executor.submit(_load_column_metadata, connection, table)

        # --- Fetch stats (and optionally top-K) from DB ----------------------
        stats_by_col, row_count, top_values_by_col, primary_sql = _fetch_stats(
            connector, col_info, source, sample_values=sample_values, approx=not exact
        )

        stored_metadata = meta_future.result()
        stored_column_metadata = col_meta_future.result()

    # --- Load table comment --------------------------------------------------
    table_comment = connector.get_table_comment(table)

    # --- Merge everything into column dicts ----------------------------------
    columns = []
    for col in col_meta:
        name = col["name"]
        stats = stats_by_col.get(name, {})
        top_vals = top_values_by_col.get(name)

        col_entry: dict = {
            "name": name,
            "type": col.get("type", ""),
            "nullable": col.get("nullable", True),
            "primary_key": col.get("primary_key", False),
            "comment": col.get("comment"),
            "null_count": stats.get("null_count"),
            "null_pct": stats.get("null_pct"),
            "distinct_count": stats.get("distinct_count"),
        }

        from querido.core._utils import is_numeric_type

        is_numeric = is_numeric_type(col.get("type", ""))
        if is_numeric:
            col_entry["min"] = stats.get("min_val")
            col_entry["max"] = stats.get("max_val")
            col_entry["mean"] = stats.get("mean_val")
            col_entry["median"] = stats.get("median_val")
            col_entry["sample_values"] = None
        else:
            col_entry["min"] = stats.get("min_val")
            col_entry["max"] = stats.get("max_val")
            col_entry["sample_values"] = top_vals

        # Merge stored metadata (human-authored + auto-written with
        # provenance unwrapped) if available.
        col_docs = stored_column_metadata.get(name)
        if col_docs:
            col_entry.update(col_docs)

        columns.append(col_entry)

    # Table-level human fields from metadata
    table_description = None
    data_owner = None
    if stored_metadata:
        table_description = stored_metadata.get("table_description")
        data_owner = stored_metadata.get("data_owner")

    sampling_note = None
    if sampled and sample_size:
        sampling_note = (
            f"Results based on a sample of {sample_size:,} rows. "
            "Use --no-sample for exact results (slower)."
        )

    return {
        "table": table,
        "dialect": connector.dialect,
        "connection": connection,
        "row_count": row_count,
        "sampled": sampled,
        "sample_size": sample_size,
        "sampling_note": sampling_note,
        "table_comment": table_comment,
        "table_description": table_description,
        "data_owner": data_owner,
        "columns": columns,
        "metadata": stored_metadata,
        "sql": primary_sql,
    }


def _fetch_stats(
    connector: Connector,
    col_info: list[dict],
    source: str,
    *,
    sample_values: int,
    approx: bool,
) -> tuple[dict[str, dict], int, dict[str, list[str] | None], str]:
    """Run the stats query and return per-column stats and sample values.

    Returns ``(stats_by_col, row_count, top_values_by_col, primary_sql)``.
    ``primary_sql`` is the main scan template — the one worth surfacing via
    ``--show-sql``. On SQLite, per-column frequency queries also run but
    they're repetitive boilerplate; showing the profile scan is the useful
    signal.

    For dialects with approx_top_k, everything is fetched in one scan.
    For SQLite, runs profile + sequential frequency queries.
    """
    from querido.sql.renderer import render_template

    if connector.dialect in _TOP_K_DIALECTS:
        sql = render_template(
            "context",
            connector.dialect,
            columns=col_info,
            source=source,
            approx=approx,
            sample_values=sample_values,
        )
        raw = connector.execute(sql)
        row = raw[0] if raw else {}
        row_count = int(row.get("total_rows", 0) or 0)

        from querido.core._utils import unpack_single_row

        stats_list = unpack_single_row(row, col_info)
        stats_by_col = {s["column_name"]: s for s in stats_list}

        # Extract approx_top_k results for non-numeric columns
        top_values_by_col: dict[str, list[str] | None] = {}
        for col in col_info:
            name = col["name"]
            if col["numeric"] or sample_values == 0:
                top_values_by_col[name] = None
                continue
            raw_top = row.get(f"{name}__top_values")
            if raw_top:
                top_values_by_col[name] = _extract_top_k_values(raw_top)
            else:
                top_values_by_col[name] = None

    else:
        # SQLite path: profile scan + frequency queries
        sql = render_template(
            "profile",
            connector.dialect,
            columns=col_info,
            source=source,
            approx=approx,
        )
        raw = connector.execute(sql)
        row = raw[0] if raw else {}
        row_count = int(row.get("total_rows", 0) or 0)

        from querido.core._utils import unpack_single_row

        stats_list = unpack_single_row(row, col_info)
        stats_by_col = {s["column_name"]: s for s in stats_list}

        top_values_by_col: dict[str, list[str] | None] = {}
        if sample_values > 0:
            from querido.core.profile import get_frequencies

            non_numeric = [c for c in col_info if not c["numeric"]]
            if non_numeric:
                freqs = get_frequencies(connector, source, non_numeric, top=sample_values)
                for col in col_info:
                    name = col["name"]
                    if col["numeric"]:
                        top_values_by_col[name] = None
                    else:
                        freq_rows = freqs.get(name, [])
                        top_values_by_col[name] = (
                            [str(r["value"]) for r in freq_rows if r.get("value") is not None]
                            if freq_rows
                            else None
                        )
            else:
                top_values_by_col = {c["name"]: None for c in col_info}
        else:
            top_values_by_col = {c["name"]: None for c in col_info}

    return stats_by_col, row_count, top_values_by_col, sql


def _extract_top_k_values(raw_top: list) -> list[str]:
    """Extract string values from an approx_top_k result.

    Shape varies by dialect:
    * DuckDB ``approx_top_k(value, k)`` returns a list of the top-K values
      themselves — e.g. ``["Rosa", "Xander", ...]`` for strings or
      ``[datetime.date(2024, 6, 6), ...]`` for DATE columns.
    * Snowflake ``APPROX_TOP_K`` returns ``[[value, count], ...]`` arrays.
    * Older DuckDB / driver versions have returned dict-shaped
      ``[{"value": ..., "count": ...}]``.

    Handle all three by checking type before indexing; convert the value
    to ``str`` for uniform downstream rendering.
    """
    if not raw_top:
        return []
    values: list[str] = []
    for item in raw_top:
        if item is None:
            continue
        if isinstance(item, dict):
            val = item.get("value")
        elif isinstance(item, (list, tuple)):
            val = item[0] if item else None
        else:
            # Primitive (str, int, float, datetime.date, …) — DuckDB's
            # modern approx_top_k returns values directly.
            val = item
        if val is not None:
            values.append(str(val))
    return values


def _load_metadata(connection: str, table: str) -> dict | None:
    """Load stored metadata for a table from disk.  Returns None if not found."""
    try:
        from querido.core.metadata import get_metadata_dir

        meta_path = get_metadata_dir(connection) / f"{table}.yaml"
        if not meta_path.exists():
            return None
        import yaml

        return yaml.safe_load(meta_path.read_text(encoding="utf-8")) or None
    except Exception:
        return None


def _load_column_metadata(connection: str, table: str) -> dict[str, dict]:
    """Load the per-column surfaceable metadata map.  Returns ``{}`` if none."""
    try:
        from querido.core.metadata import load_column_metadata

        return load_column_metadata(connection, table)
    except Exception:
        return {}
