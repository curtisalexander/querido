"""``next_steps`` rules for the table-scanning command family."""

from __future__ import annotations

from querido.core.context import ContextResult
from querido.core.next_steps._helpers import (
    _first_high_null_column,
    _first_low_cardinality_by_profile,
    _first_low_cardinality_string,
    _first_numeric_by_profile,
    _first_numeric_column,
    _maybe_suggest_metadata,
    _step,
)
from querido.core.quality import QualityResult
from querido.core.values import ValuesResult


def for_inspect(
    result: dict,
    *,
    connection: str,
    table: str,
    verbose: bool,
) -> list[dict]:
    """Rules for ``qdo inspect``.

    Inspect shows column metadata and row count. Natural next moves:
    - peek at rows (``preview``)
    - get richer stats + sample values (``context``)
    - profile columns in depth (``profile``)
    - if a non-trivial column list and no table comment, nudge toward
      metadata authoring
    """
    steps: list[dict] = []
    row_count = result.get("row_count") or 0
    columns = result.get("columns") or []
    has_table_comment = bool(result.get("table_comment"))

    if row_count > 0:
        steps.append(
            _step(
                ["qdo", "preview", "-c", connection, "-t", table],
                "See a handful of actual rows.",
            )
        )
        steps.append(
            _step(
                ["qdo", "context", "-c", connection, "-t", table],
                "Get column stats and sample values in one call.",
            )
        )

    if len(columns) >= 3 and row_count > 0:
        steps.append(
            _step(
                ["qdo", "profile", "-c", connection, "-t", table, "--quick"],
                "Profile all columns in one scan (quick mode).",
            )
        )

    if not verbose and (columns or has_table_comment is False):
        steps.append(
            _step(
                ["qdo", "inspect", "-c", connection, "-t", table, "--verbose"],
                "Show table and column comments.",
            )
        )

    if not has_table_comment and columns:
        steps.append(
            _step(
                ["qdo", "metadata", "init", "-c", connection, "-t", table],
                "No table description found — scaffold a metadata YAML.",
            )
        )

    pointer = _maybe_suggest_metadata(connection, table)
    if pointer:
        steps.append(pointer)

    return steps


def for_context(
    result: ContextResult,
    *,
    connection: str,
    table: str,
) -> list[dict]:
    """Rules for ``qdo context``.

    Context is the densest single call: schema + stats + sample values.
    Natural next moves are derived from what the stats reveal:
    - high null_pct column → run ``quality``
    - low-cardinality string column → run ``values`` or ``dist``
    - temporal column → encourage freshness/filter scoping (future)
    - no stored metadata yet → nudge toward metadata init
    """
    steps: list[dict] = []
    columns = result.get("columns") or []
    row_count = result.get("row_count") or 0
    has_metadata = bool(result.get("metadata"))

    high_null = _first_high_null_column(columns, threshold=50.0)
    if high_null:
        steps.append(
            _step(
                ["qdo", "quality", "-c", connection, "-t", table],
                f"'{high_null}' has high null rate — run a quality pass.",
            )
        )

    low_card_col = _first_low_cardinality_string(columns, max_distinct=20)
    if low_card_col:
        steps.append(
            _step(
                ["qdo", "values", "-c", connection, "-t", table, "--columns", low_card_col],
                f"'{low_card_col}' is low-cardinality — list distinct values.",
            )
        )

    numeric_col = _first_numeric_column(columns)
    if numeric_col and row_count > 0:
        steps.append(
            _step(
                ["qdo", "dist", "-c", connection, "-t", table, "--columns", numeric_col],
                f"Visualize distribution of numeric column '{numeric_col}'.",
            )
        )

    if not has_metadata and columns:
        steps.append(
            _step(
                ["qdo", "metadata", "init", "-c", connection, "-t", table],
                "No stored metadata — scaffold a YAML so future runs are richer.",
            )
        )

    if row_count > 0:
        steps.append(
            _step(
                ["qdo", "preview", "-c", connection, "-t", table],
                "See actual rows to sanity-check the stats.",
            )
        )

    pointer = _maybe_suggest_metadata(connection, table)
    if pointer:
        steps.append(pointer)

    return steps


def for_freshness(
    result: dict,
    *,
    connection: str,
    table: str,
) -> list[dict]:
    """Rules for ``qdo freshness``."""
    selected = result.get("selected_column")
    status = result.get("status")

    if not selected:
        return [
            _step(
                ["qdo", "inspect", "-c", connection, "-t", table],
                "Check the schema to confirm whether the table has any usable timestamp columns.",
            ),
            _step(
                ["qdo", "context", "-c", connection, "-t", table],
                "Review column types and sample values to find a better freshness signal.",
            ),
        ]

    if status == "stale":
        sql = f'select * from {table} order by "{selected}" desc limit 20'
        return [
            _step(
                ["qdo", "query", "-c", connection, "--sql", sql],
                f"Inspect the newest rows by '{selected}' to see why freshness looks stale.",
            ),
            _step(
                ["qdo", "quality", "-c", connection, "-t", table, "--columns", selected],
                f"Check nulls and anomalies in the freshness column '{selected}'.",
            ),
        ]

    return [
        _step(
            [
                "qdo",
                "query",
                "-c",
                connection,
                "--sql",
                f'select max("{selected}") as latest_ts from {table}',
            ],
            f"Verify the latest value in '{selected}' directly.",
        ),
        _step(
            ["qdo", "context", "-c", connection, "-t", table],
            "Step out to the broader table context if you need more than recency.",
        ),
    ]


def for_preview(
    rows: list[dict],
    *,
    connection: str,
    table: str,
    limit: int,
) -> list[dict]:
    """Rules for ``qdo preview``.

    Preview is a peek at raw rows. It rarely is the final stop — natural next
    moves are schema (``inspect``), rich context, or further exploration.
    """
    steps: list[dict] = []
    row_count = len(rows)

    if row_count == 0:
        steps.append(
            _step(
                ["qdo", "inspect", "-c", connection, "-t", table],
                "No rows returned — check that the table has data / your connection.",
            )
        )
        return steps

    steps.append(
        _step(
            ["qdo", "context", "-c", connection, "-t", table],
            "Get column stats and sample values in one call.",
        )
    )
    steps.append(
        _step(
            ["qdo", "inspect", "-c", connection, "-t", table],
            "See schema (types, nullability, primary keys).",
        )
    )

    if row_count >= limit:
        steps.append(
            _step(
                ["qdo", "preview", "-c", connection, "-t", table, "--rows", str(limit * 5)],
                f"Preview hit the limit ({limit}) — fetch more rows.",
            )
        )

    return steps


def for_profile(
    result: dict,
    *,
    connection: str,
    table: str,
    top: int,
) -> list[dict]:
    """Rules for ``qdo profile``.

    Profile is the heaviest scan we do — make sure follow-ups are focused.
    Target columns with high null rates (quality), low cardinality (values),
    or numeric skew (dist). Suggest top-N if not requested and row count
    makes it useful.
    """
    steps: list[dict] = []
    stats = result.get("columns") or result.get("stats") or []

    high_null = _first_high_null_column(stats, threshold=50.0, null_key="null_pct")
    if high_null:
        steps.append(
            _step(
                ["qdo", "quality", "-c", connection, "-t", table],
                f"'{high_null}' has high null rate — run a quality pass.",
            )
        )

    low_card = _first_low_cardinality_by_profile(stats, max_distinct=20)
    if low_card:
        steps.append(
            _step(
                ["qdo", "values", "-c", connection, "-t", table, "--columns", low_card],
                f"'{low_card}' is low-cardinality — list distinct values.",
            )
        )

    numeric = _first_numeric_by_profile(stats)
    if numeric:
        steps.append(
            _step(
                ["qdo", "dist", "-c", connection, "-t", table, "--columns", numeric],
                f"Visualize distribution of numeric column '{numeric}'.",
            )
        )

    if top == 0 and stats:
        steps.append(
            _step(
                ["qdo", "profile", "-c", connection, "-t", table, "--top", "10"],
                "Re-run with top-N to see the most frequent values per column.",
            )
        )

    if result.get("sampled"):
        steps.append(
            _step(
                ["qdo", "profile", "-c", connection, "-t", table, "--no-sample"],
                "Results were sampled — re-run exact (slower).",
            )
        )

    pointer = _maybe_suggest_metadata(connection, table)
    if pointer:
        steps.append(pointer)

    return steps


def for_dist(
    result: dict,
    *,
    connection: str,
    table: str,
) -> list[dict]:
    """Rules for ``qdo dist``.

    Numeric histograms and categorical frequency — drill further into the
    column (values), widen to full quality, or step back to context.
    """
    steps: list[dict] = []
    column = result.get("column") or ""
    mode = result.get("mode")

    if mode == "categorical":
        values = result.get("values") or []
        if values and len(values) >= 20:
            steps.append(
                _step(
                    ["qdo", "values", "-c", connection, "-t", table, "--columns", column],
                    f"'{column}' has many distinct values — enumerate them all.",
                )
            )

    if result.get("null_count"):
        steps.append(
            _step(
                ["qdo", "quality", "-c", connection, "-t", table, "--columns", column],
                f"'{column}' has nulls — run a quality check.",
            )
        )

    steps.append(
        _step(
            ["qdo", "context", "-c", connection, "-t", table],
            "Step back to full table context.",
        )
    )
    return steps


def for_values(
    result: ValuesResult,
    *,
    connection: str,
    table: str,
) -> list[dict]:
    """Rules for ``qdo values``.

    If truncated, suggest widening. Always offer dist for a visual cut and
    metadata authoring (valid_values can be captured from this output).
    """
    steps: list[dict] = []
    column = result.get("column") or ""
    truncated = bool(result.get("truncated"))
    distinct = result.get("distinct_count") or 0

    if truncated:
        steps.append(
            _step(
                [
                    "qdo",
                    "values",
                    "-c",
                    connection,
                    "-t",
                    table,
                    "--columns",
                    column,
                    "--max",
                    str(max(distinct, 1000) * 2),
                ],
                "Result was truncated — raise --max to see all distinct values.",
            )
        )

    steps.append(
        _step(
            ["qdo", "dist", "-c", connection, "-t", table, "--columns", column],
            f"Visualize '{column}' as a frequency distribution.",
        )
    )

    stored = result.get("stored_metadata") or {}
    already_captured = bool(stored.get("valid_values"))
    if 1 < distinct <= 20 and not already_captured:
        steps.append(
            _step(
                [
                    "qdo",
                    "values",
                    "-c",
                    connection,
                    "-t",
                    table,
                    "--columns",
                    column,
                    "--write-metadata",
                ],
                f"'{column}' looks enumerable — capture as valid_values in metadata.",
            )
        )
    return steps


def for_quality(
    result: QualityResult,
    *,
    connection: str,
    table: str,
) -> list[dict]:
    """Rules for ``qdo quality``.

    Surface columns the quality check flagged, and offer a duplicate-row
    check if it wasn't done.
    """
    steps: list[dict] = []
    columns = result.get("columns") or []

    failing = next((c for c in columns if c.get("status") in ("fail", "warn")), None)
    if failing:
        name = failing.get("name") or ""
        steps.append(
            _step(
                ["qdo", "dist", "-c", connection, "-t", table, "--columns", name],
                f"'{name}' flagged {failing.get('status')} — inspect its distribution.",
            )
        )
        steps.append(
            _step(
                ["qdo", "values", "-c", connection, "-t", table, "--columns", name],
                f"See distinct values for flagged column '{name}'.",
            )
        )

    if result.get("duplicate_rows") is None and columns:
        steps.append(
            _step(
                ["qdo", "quality", "-c", connection, "-t", table, "--check-duplicates"],
                "Also check for fully duplicate rows (slower).",
            )
        )

    if result.get("sampled"):
        steps.append(
            _step(
                ["qdo", "quality", "-c", connection, "-t", table, "--no-sample"],
                "Results were sampled — re-run exact.",
            )
        )

    pointer = _maybe_suggest_metadata(connection, table)
    if pointer:
        steps.append(pointer)

    return steps


def for_joins(
    result: dict,
    *,
    connection: str,
    source_table: str,
) -> list[dict]:
    """Rules for ``qdo joins``.

    If candidates are found, encourage running a test join via ``query``.
    Otherwise, step out to catalog to rethink the graph.
    """
    steps: list[dict] = []
    candidates = result.get("candidates") or []

    if not candidates:
        steps.append(
            _step(
                ["qdo", "catalog", "-c", connection],
                "No join candidates — review all tables in this connection.",
            )
        )
        return steps

    best = candidates[0]
    target = best.get("target_table") or ""
    keys = best.get("join_keys") or []
    if target and keys:
        key = keys[0]
        sql = (
            f"select l.*, r.* from {source_table} l "
            f"join {target} r on l.{key['source_col']} = r.{key['target_col']} limit 10"
        )
        steps.append(
            _step(
                ["qdo", "query", "-c", connection, "--sql", sql],
                f"Try the top candidate join on '{target}'.",
            )
        )

    if target:
        steps.append(
            _step(
                ["qdo", "context", "-c", connection, "-t", target],
                f"Inspect the likely join target '{target}'.",
            )
        )
    return steps


def for_pivot(
    result: dict,
    *,
    connection: str,
    table: str,
) -> list[dict]:
    """Rules for ``qdo pivot``.

    Empty result → sanity-check the source table. Normal result → offer
    to dump the underlying pivot SQL or export for downstream tooling.
    """
    steps: list[dict] = []
    rows = result.get("rows") or []
    row_count = len(rows)
    sql = result.get("sql") or ""

    if row_count == 0:
        steps.append(
            _step(
                ["qdo", "preview", "-c", connection, "-t", table],
                "Pivot returned no rows — peek at source rows to verify filters.",
            )
        )
        return steps

    if sql:
        steps.append(
            _step(
                ["qdo", "query", "-c", connection, "--sql", sql],
                "Run the underlying pivot SQL to iterate on it directly.",
            )
        )

    steps.append(
        _step(
            ["qdo", "context", "-c", connection, "-t", table],
            "Step back to full table context to compare with the pivot.",
        )
    )
    return steps
