"""Deterministic ``next_steps`` rules.

Each rule inspects the shape of a command's output (row counts, null rates,
distinct counts, metadata presence, etc.) and returns a list of suggested
follow-up ``qdo`` invocations as ``{"cmd": str, "why": str}`` dicts.

Rules must be deterministic — no LLM calls, no network, no randomness.
They exist to turn every command into a node in a traversable graph for
agents. Human users also see them via the ``-f rich`` path (eventually).

Each ``cmd`` string is a shell-ready ``qdo ...`` invocation so agents can
re-exec it directly. Use :func:`querido.output.envelope.cmd` to build
them — it handles quoting for identifiers with special characters.
"""

from __future__ import annotations

from querido.core.context import ContextResult
from querido.core.quality import QualityResult
from querido.core.values import ValuesResult
from querido.output.envelope import cmd


def _step(argv: list[str], why: str) -> dict:
    return {"cmd": cmd(argv), "why": why}


def _maybe_suggest_metadata(connection: str, table: str) -> dict | None:
    """If *table* has a low stored metadata score, propose ``metadata suggest``.

    Returns ``None`` when no metadata file exists (other rules handle init)
    or when the score is already healthy.
    """
    from querido.core.metadata_score import LOW_SCORE_THRESHOLD, peek_score

    score = peek_score(connection, table)
    if score is None or score >= LOW_SCORE_THRESHOLD:
        return None
    return _step(
        ["qdo", "metadata", "suggest", "-c", connection, "-t", table],
        f"Stored metadata score is {score:.2f} — propose additions from fresh scans.",
    )


# -- scanning commands --------------------------------------------------------


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


def for_catalog(
    result: dict,
    *,
    connection: str,
    enriched: bool,
) -> list[dict]:
    """Rules for ``qdo catalog``.

    Catalog lists all tables. Natural next moves:
    - drill into a specific table via ``context`` / ``inspect``
    - discover joins across the catalog
    - enrich with stored metadata if not already
    - if empty, pivot the user to check their connection
    """
    steps: list[dict] = []
    tables = result.get("tables") or []

    if not tables:
        steps.append(
            _step(
                ["qdo", "config", "test", connection],
                "No tables visible — verify the connection works.",
            )
        )
        return steps

    largest = _pick_largest_table(tables)
    if largest:
        steps.append(
            _step(
                ["qdo", "context", "-c", connection, "-t", largest],
                f"Deep-dive on '{largest}' (largest table by row count).",
            )
        )

    join_source = largest or next((t.get("name") for t in tables if t.get("name")), None)
    if len(tables) >= 2 and join_source:
        steps.append(
            _step(
                ["qdo", "joins", "-c", connection, "-t", join_source],
                "Discover likely join keys from a representative table.",
            )
        )

    if not enriched:
        steps.append(
            _step(
                ["qdo", "catalog", "-c", connection, "--enrich"],
                "Merge stored metadata (descriptions, owners) into the catalog.",
            )
        )

    return steps


def for_catalog_functions(
    result: dict,
    *,
    connection: str,
    pattern: str | None,
) -> list[dict]:
    """Rules for ``qdo catalog functions``."""
    if not result.get("supported", True):
        return [
            _step(
                ["qdo", "catalog", "-c", connection],
                "SQLite catalogs tables and views, but not backend SQL functions.",
            )
        ]

    if not result.get("functions") and pattern:
        return [
            _step(
                ["qdo", "catalog", "functions", "-c", connection],
                "No functions matched that filter; rerun without --pattern to browse everything.",
            ),
            _step(
                ["qdo", "catalog", "-c", connection],
                "Step back to tables/views if you meant data objects rather than SQL functions.",
            ),
        ]

    return [
        _step(
            ["qdo", "catalog", "-c", connection],
            "Step back to tables/views if you meant data objects rather than SQL functions.",
        )
    ]


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


def for_diff(
    result: dict,
    *,
    connection: str,
    left_table: str,
    right_table: str | None,
    target_connection: str | None = None,
) -> list[dict]:
    """Rules for ``qdo diff``.

    If schemas match, encourage data-level checks. Otherwise, offer context
    on each side so the agent can reason about why they diverged.
    """
    steps: list[dict] = []
    added = result.get("added") or []
    removed = result.get("removed") or []
    changed = result.get("changed") or []
    right_conn = target_connection or connection
    right_target = right_table or result.get("right") or left_table

    if not added and not removed and not changed:
        steps.append(
            _step(
                ["qdo", "context", "-c", connection, "-t", left_table],
                "Schemas match — compare data shape instead via context.",
            )
        )
        return steps

    steps.append(
        _step(
            ["qdo", "inspect", "-c", connection, "-t", left_table],
            f"Full schema for left side ('{left_table}').",
        )
    )
    steps.append(
        _step(
            ["qdo", "inspect", "-c", right_conn, "-t", right_target],
            f"Full schema for right side ('{right_target}').",
        )
    )
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


def for_query(
    result: dict,
    *,
    connection: str,
) -> list[dict]:
    """Rules for ``qdo query``.

    Limited results → nudge toward raising the limit or exporting. No rows
    → suggest a schema check. Rows with recognizable table-like output →
    (no action; the agent already has what it needs).
    """
    steps: list[dict] = []
    rows = result.get("rows") or []
    row_count = len(rows)
    limited = bool(result.get("limited"))

    if row_count == 0:
        steps.append(
            _step(
                ["qdo", "catalog", "-c", connection],
                "Query returned no rows — confirm the referenced tables exist.",
            )
        )
        return steps

    if limited:
        steps.append(
            _step(
                ["qdo", "export", "-c", connection, "--export-format", "csv"],
                "Results were limit-capped — use export to stream everything.",
            )
        )

    return steps


def for_assert(
    result: dict,
    *,
    connection: str,
) -> list[dict]:
    """Rules for ``qdo assert``.

    On fail: point at the underlying query so the agent can see the actual
    rows behind the counter it asserted on. On pass: no nudge — success
    rarely warrants a follow-up, and noise here costs agent tokens.
    """
    steps: list[dict] = []
    if result.get("passed", False):
        return steps

    sql = result.get("sql") or ""
    if sql:
        steps.append(
            _step(
                ["qdo", "query", "-c", connection, "--sql", sql],
                "Assertion failed — run the underlying query to see actual rows.",
            )
        )
    return steps


def for_explain(
    result: dict,
    *,
    connection: str,
) -> list[dict]:
    """Rules for ``qdo explain``.

    Natural next moves: run the query for real, or (DuckDB only) re-run
    with ``--analyze`` for runtime stats.
    """
    steps: list[dict] = []
    sql = result.get("sql") or ""
    dialect = result.get("dialect") or ""
    analyzed = bool(result.get("analyzed"))

    if sql:
        steps.append(
            _step(
                ["qdo", "query", "-c", connection, "--sql", sql],
                "Execute the query to see actual results.",
            )
        )

    if not analyzed and dialect == "duckdb" and sql:
        steps.append(
            _step(
                ["qdo", "explain", "-c", connection, "--sql", sql, "--analyze"],
                "Re-run with --analyze for actual runtime stats (DuckDB).",
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


def for_view_def(
    result: dict,
    *,
    connection: str,
    view: str,
) -> list[dict]:
    """Rules for ``qdo view-def``.

    After reading a view's SQL, the next moves are to see its shape
    (``inspect``), sample rows (``preview``), or profile its output.
    """
    steps: list[dict] = []
    if not result.get("definition"):
        return steps

    steps.append(
        _step(
            ["qdo", "inspect", "-c", connection, "-t", view],
            f"See '{view}' column types and nullability.",
        )
    )
    steps.append(
        _step(
            ["qdo", "preview", "-c", connection, "-t", view],
            f"Peek at rows produced by '{view}'.",
        )
    )
    return steps


def for_metadata_show(
    result: dict,
    *,
    connection: str,
    table: str,
) -> list[dict]:
    """Rules for ``qdo metadata show``.

    A shown metadata doc points the reader at the two natural follow-ups:
    edit the YAML (fill in human fields or correct auto-written ones), and
    refresh auto-written stats from a new scan.
    """
    steps: list[dict] = [
        _step(
            ["qdo", "metadata", "edit", "-c", connection, "-t", table],
            "Open the YAML in $EDITOR to fill in descriptions or correct stored fields.",
        ),
        _step(
            ["qdo", "metadata", "refresh", "-c", connection, "-t", table],
            "Re-run the profile scan and update auto-written stats.",
        ),
    ]

    # If any human-authored placeholders remain, nudge at them.
    placeholder = "<description>"
    has_placeholder = False
    if result.get("table_description") == placeholder:
        has_placeholder = True
    for col in result.get("columns") or []:
        if col.get("description") == placeholder:
            has_placeholder = True
            break
    if has_placeholder:
        steps.append(
            _step(
                ["qdo", "metadata", "suggest", "-c", connection, "-t", table],
                "Some placeholder fields remain — suggest deterministic auto-fill.",
            )
        )

    return steps


def for_metadata_search(
    result: dict,
    *,
    connection: str,
) -> list[dict]:
    """Rules for ``qdo metadata search``."""
    if not result.get("metadata_file_count"):
        return [
            _step(
                ["qdo", "metadata", "list", "-c", connection],
                "Check whether this connection has any stored metadata files yet.",
            ),
            _step(
                ["qdo", "catalog", "-c", connection],
                "Browse live tables, then scaffold metadata for the ones you care about.",
            ),
        ]

    matches = result.get("results") or []
    if not matches:
        return [
            _step(
                ["qdo", "metadata", "list", "-c", connection],
                "Browse the stored metadata corpus to refine the next search.",
            ),
            _step(
                ["qdo", "catalog", "-c", connection, "--enrich"],
                "Compare live schema names with the stored descriptions and owners.",
            ),
        ]

    top = matches[0]
    table = str(top.get("table") or "")
    column = top.get("column")
    if not table:
        return []

    steps = [
        _step(
            ["qdo", "metadata", "show", "-c", connection, "-t", table],
            f"Open the stored metadata for '{table}'.",
        ),
        _step(
            ["qdo", "context", "-c", connection, "-t", table],
            f"Pull live stats and sample values for '{table}'.",
        ),
    ]
    if isinstance(column, str) and column:
        steps.append(
            _step(
                [
                    "qdo",
                    "query",
                    "-c",
                    connection,
                    "--sql",
                    _preview_column_sql(table, column),
                ],
                f"Inspect recent non-null values from '{table}.{column}'.",
            )
        )
    return steps


def for_template(
    result: dict,
    *,
    connection: str,
    table: str,
) -> list[dict]:
    """Rules for ``qdo template``.

    Template is the doc-authoring entrypoint. The natural compounding move
    is to scaffold / enrich stored metadata from the same scan output.
    """
    steps: list[dict] = []
    table_comment = result.get("table_comment") or ""
    columns = result.get("columns") or []

    if not table_comment:
        steps.append(
            _step(
                ["qdo", "metadata", "init", "-c", connection, "-t", table],
                "No table description — scaffold a metadata YAML to edit.",
            )
        )

    if columns:
        steps.append(
            _step(
                ["qdo", "profile", "-c", connection, "-t", table, "--write-metadata"],
                "Capture deterministic profile inferences into the metadata YAML.",
            )
        )

    pointer = _maybe_suggest_metadata(connection, table)
    if pointer:
        steps.append(pointer)

    return steps


def _preview_column_sql(table: str, column: str) -> str:
    quoted_table = table.replace('"', '""')
    quoted_column = column.replace('"', '""')
    return (
        f'SELECT "{quoted_column}" '
        f'FROM "{quoted_table}" '
        f'WHERE "{quoted_column}" IS NOT NULL LIMIT 20'
    )


# -- errors -------------------------------------------------------------------


def for_error(
    code: str,
    *,
    connection: str | None = None,
    table: str | None = None,
) -> list[dict]:
    """Rules for ``try_next`` on structured errors.

    Connection/table may be unknown at error time (e.g. validation failed
    before they were resolved) — rules skip suggestions that need missing
    context.
    """
    steps: list[dict] = []

    if code == "TABLE_NOT_FOUND" and connection:
        argv = ["qdo", "catalog", "-c", connection]
        if table:
            argv += ["--pattern", table]
        steps.append(_step(argv, "List visible tables (optionally filtered)."))
        steps.append(
            _step(
                ["qdo", "cache", "sync", "-c", connection],
                "Refresh the metadata cache if the table was just created.",
            )
        )

    elif code == "COLUMN_NOT_FOUND" and connection and table:
        steps.append(
            _step(
                ["qdo", "inspect", "-c", connection, "-t", table],
                "See the available columns on the target table.",
            )
        )

    elif code == "DATABASE_LOCKED":
        steps.append(
            _step(
                ["qdo", "config", "list"],
                "Check which connections might be holding a lock.",
            )
        )

    elif code == "DATABASE_OPEN_FAILED" and connection:
        steps.append(
            _step(
                ["qdo", "config", "test", connection],
                "Verify the connection's path or credentials.",
            )
        )

    elif code == "AUTH_FAILED" and connection:
        steps.append(
            _step(
                ["qdo", "config", "test", connection],
                "Re-authenticate and verify the connection.",
            )
        )

    elif code == "MISSING_DEPENDENCY":
        steps.append(
            {
                "cmd": "uv pip install 'querido[duckdb]'",
                "why": "Install the DuckDB + Parquet extra.",
            }
        )
        steps.append(
            {
                "cmd": "uv pip install 'querido[snowflake]'",
                "why": "Install the Snowflake extra.",
            }
        )

    elif code == "FILE_NOT_FOUND":
        steps.append(
            _step(["qdo", "config", "list"], "List configured connections to find the right path.")
        )

    elif code == "SESSION_NOT_FOUND":
        steps.append(
            _step(
                ["qdo", "session", "list"],
                "List recorded sessions to find the right name.",
            )
        )

    elif code == "SESSION_STEP_UNSTRUCTURED":
        steps.append(
            _step(
                [
                    "QDO_SESSION=<name>",
                    "qdo",
                    "-f",
                    "json",
                    "query",
                    "-c",
                    "<connection>",
                    "--sql",
                    "<sql>",
                ],
                "Re-record the source step with -f json so --from can replay its SQL envelope.",
            )
        )
        steps.append(
            _step(
                ["qdo", "session", "show", "<session>"],
                "Inspect the session to find a step already recorded as JSON.",
            )
        )

    elif code in {
        "SESSION_STEP_NOT_FOUND",
        "SESSION_STEP_UNSUPPORTED",
        "SESSION_STEP_NO_SQL",
        "SESSION_STEP_REF_INVALID",
    }:
        steps.append(
            _step(
                ["qdo", "session", "show", "<session>"],
                "Inspect the session and pick a recorded query step reference.",
            )
        )

    elif code == "SESSION_SNAPSHOT_NOT_FOUND":
        if connection and table:
            steps.append(
                _step(
                    ["qdo", "-f", "json", "inspect", "-c", connection, "-t", table],
                    "Record a structured snapshot before diffing against a session.",
                )
            )
        steps.append(
            _step(
                ["qdo", "session", "show", "<session>"],
                "Inspect the session to confirm it captured this table in structured form.",
            )
        )

    elif code == "METADATA_NOT_FOUND" and connection and table:
        steps.append(
            _step(
                ["qdo", "metadata", "init", "-c", connection, "-t", table],
                "Create the metadata YAML before trying to read it.",
            )
        )

    elif code == "COLUMN_SET_NOT_FOUND" and connection and table:
        steps.append(
            _step(
                ["qdo", "config", "column-set", "list", "-c", connection, "-t", table],
                "List saved column sets for this table.",
            )
        )

    elif code == "SNOWFLAKE_REQUIRED":
        steps.append(
            _step(
                ["qdo", "config", "list"],
                "List configured connections and pick a Snowflake one.",
            )
        )

    elif code == "WRITE_REQUIRES_ALLOW_WRITE":
        steps.append(
            {
                "cmd": "qdo query --allow-write -c <connection> --sql '<write statement>'",
                "why": "Re-run only if you intend to mutate data.",
            }
        )
        steps.append(
            {
                "cmd": "qdo query -c <connection> --sql 'select ...'",
                "why": "Keep using the default read-only path for inspection queries.",
            }
        )

    elif code == "CONNECTION_NOT_FOUND":
        steps.append(
            _step(
                ["qdo", "config", "list"],
                "List configured connections to find the right source name.",
            )
        )

    return steps


def for_workflow_step_failed(
    *,
    workflow: str,
    step_id: str,
    step_cmd: str,
    session: str,
    timed_out: bool = False,
) -> list[dict]:
    """Rules for ``try_next`` on a workflow step failure.

    Deterministic follow-ups: stream the session to see what else happened,
    re-run with ``--verbose`` for live output, or run the failing step's
    command standalone to iterate on it outside the workflow.
    """
    steps: list[dict] = []

    if session:
        steps.append(
            _step(
                ["qdo", "session", "show", session],
                "See every step this run recorded (step-by-step stdout is saved).",
            )
        )

    if step_cmd:
        steps.append(
            {
                "cmd": step_cmd,
                "why": (
                    f"Re-run step {step_id!r} on its own to iterate "
                    "without the rest of the workflow."
                ),
            }
        )

    steps.append(
        _step(
            ["qdo", "workflow", "run", workflow, "--verbose"],
            "Re-run with --verbose to stream each step's stdout as it executes.",
        )
    )

    if timed_out:
        steps.append(
            _step(
                ["qdo", "workflow", "run", workflow, "--step-timeout", "0"],
                "Disable the step timeout for a one-off run (agents: use with care).",
            )
        )

    return steps


# -- helpers ------------------------------------------------------------------


def _pick_largest_table(tables: list[dict]) -> str | None:
    """Return the name of the table with the highest row_count (or None)."""
    best_name: str | None = None
    best_count = -1
    for t in tables:
        rc = t.get("row_count")
        if rc is None:
            continue
        if rc > best_count:
            best_count = rc
            best_name = t.get("name")
    return best_name


def _first_high_null_column(
    columns: list[dict], *, threshold: float, null_key: str = "null_pct"
) -> str | None:
    for col in columns:
        pct = col.get(null_key)
        if pct is not None and pct >= threshold:
            # Profile and context use different name keys.
            return col.get("name") or col.get("column_name")
    return None


def _first_low_cardinality_by_profile(columns: list[dict], *, max_distinct: int) -> str | None:
    """``profile`` uses ``column_name``/``column_type`` and ``min_length`` to mark
    strings."""
    for col in columns:
        distinct = col.get("distinct_count")
        is_stringy = col.get("min_length") is not None
        if is_stringy and distinct is not None and 1 < distinct <= max_distinct:
            return col.get("column_name")
    return None


def _first_numeric_by_profile(columns: list[dict]) -> str | None:
    for col in columns:
        if col.get("min_val") is not None or col.get("mean_val") is not None:
            return col.get("column_name")
    return None


def _first_low_cardinality_string(columns: list[dict], *, max_distinct: int) -> str | None:
    for col in columns:
        distinct = col.get("distinct_count")
        col_type = (col.get("type") or "").upper()
        is_stringy = any(tok in col_type for tok in ("CHAR", "TEXT", "STRING", "VARCHAR"))
        if is_stringy and distinct is not None and 1 < distinct <= max_distinct:
            return col.get("name")
    return None


def _first_numeric_column(columns: list[dict]) -> str | None:
    numeric_tokens = ("INT", "DEC", "NUM", "FLOAT", "DOUBLE", "REAL")
    for col in columns:
        col_type = (col.get("type") or "").upper()
        if any(tok in col_type for tok in numeric_tokens):
            return col.get("name")
    return None
