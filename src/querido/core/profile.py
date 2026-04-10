from __future__ import annotations

from typing import TYPE_CHECKING

from querido.core._utils import build_col_info, build_sample_source, unpack_single_row

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def get_profile(
    connector: Connector,
    table: str,
    *,
    columns: str | None = None,
    sample: int | None = None,
    no_sample: bool = False,
    exact: bool = False,
    quick: bool = False,
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
        filter_names = {c.strip().lower() for c in columns.split(",") if c.strip()}
        filtered = [c for c in col_meta if c["name"].lower() in filter_names]
        if not filtered:
            available = ", ".join(c["name"] for c in col_meta)
            raise ValueError(
                f"No matching columns found in '{table}'.\nAvailable columns: {available}"
            )
        col_meta = filtered

    col_info = build_col_info(col_meta)

    # Only run a separate count query when we need it for auto-sampling.
    # When sample is explicit or no_sample is set, skip the extra table scan;
    # the real row count will be extracted from the profile query result.
    needs_auto_sample = sample is None and not no_sample
    if needs_auto_sample:
        row_count = connector.get_row_count(table)
    elif sample is not None:
        # Explicit sample requested — use a large sentinel so
        # _build_sample_source always enables sampling.
        row_count = sample + 1
    else:
        # no_sample is True — row_count is unused for sampling decisions.
        row_count = 0

    source, sampled, sample_size = build_sample_source(
        connector, table, row_count, sample=sample, no_sample=no_sample
    )

    approx = not exact
    concurrent = getattr(connector, "supports_concurrent_queries", False)

    # For wide tables on concurrent connectors, batch columns into groups
    # and run profile queries in parallel.  Each batch produces a single
    # wide row that we unpack and merge.
    import os

    batch_size = int(os.environ.get("QDO_PROFILE_BATCH_SIZE", "25"))
    if concurrent and len(col_info) > batch_size:
        stats = _profile_batched(
            connector, col_info, source, approx, batch_size=batch_size, quick=quick
        )
    else:
        sql = render_template(
            "profile",
            connector.dialect,
            columns=col_info,
            source=source,
            approx=approx,
            quick=quick,
        )
        raw = connector.execute(sql)

        # The single-scan templates produce a single wide row; reshape it.
        if raw and len(raw) == 1 and "total_rows" in raw[0]:
            stats = unpack_single_row(raw[0], col_info)
        else:
            stats = raw

    # Always prefer the actual row count from the profile result when
    # available — it's exact, while get_row_count() may be an estimate.
    if stats and stats[0].get("total_rows") is not None:
        row_count = stats[0].get("total_rows", 0)

    sampling_note = None
    if sampled and sample_size:
        sampling_note = (
            f"Results based on a sample of {sample_size:,} rows. "
            "Use --no-sample for exact results (slower)."
        )

    return {
        "stats": stats,
        "row_count": row_count,
        "sampled": sampled,
        "sample_size": sample_size,
        "sampling_note": sampling_note,
        "source": source,
        "col_info": col_info,
        "quick": quick,
    }


def _profile_batched(
    connector: Connector,
    col_info: list[dict],
    source: str,
    approx: bool,
    *,
    batch_size: int = 25,
    quick: bool = False,
) -> list[dict]:
    """Run profile queries in parallel batches for wide tables.

    Splits *col_info* into groups of *batch_size* columns, renders a
    profile query for each batch, executes them concurrently, and merges
    the per-column stats into a single list.
    """
    from querido.sql.renderer import render_template

    batches = [col_info[i : i + batch_size] for i in range(0, len(col_info), batch_size)]

    def _run_batch(batch: list[dict]) -> list[dict]:
        sql = render_template(
            "profile", connector.dialect, columns=batch, source=source, approx=approx, quick=quick
        )
        raw = connector.execute(sql)
        if raw and len(raw) == 1 and "total_rows" in raw[0]:
            return unpack_single_row(raw[0], batch)
        return raw

    from querido.core._concurrent import run_parallel_ordered

    batch_results = run_parallel_ordered(batches, _run_batch)

    all_stats: list[dict] = []
    for batch_stats in batch_results:
        all_stats.extend(batch_stats)
    return all_stats


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
        from querido.core._concurrent import run_parallel

        return run_parallel(col_info, _fetch_one)

    return dict(_fetch_one(col) for col in col_info)
