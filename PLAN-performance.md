# Performance Optimization Plan

## Overview

Systematic improvements to query speed, round-trip reduction, and caching across all backends (SQLite, DuckDB, Snowflake). Ordered by value × effort.

---

## P0 — Critical / Quick Wins

### P0-1: DuckDB profile — single-scan aggregation
- **Problem**: `profile/duckdb.sql` generates one `SELECT ... FROM source` per column via UNION ALL. A 50-column table = 50 full table scans.
- **Solution**: Port the Snowflake single-scan pattern — all aggregations in one wide row, unpacked in Python via `_unpack_single_row()`. Also added `approx` parameter for `APPROX_COUNT_DISTINCT`.
- **Files**: `src/querido/sql/templates/profile/duckdb.sql`
- **Impact**: 10-50x faster profiling on DuckDB for wide tables
- **Status**: [x] Done

### P0-2: Remove default `check_exists=True` — lazy existence checking
- **Problem**: Every command calls `get_tables()` before doing anything. On Snowflake this queries `information_schema.tables` (1-3s) just to produce a nicer error message.
- **Solution**: Changed `table_command()` default to `check_exists=False`. Added `_maybe_reraise_as_table_not_found()` in `_pipeline.py` to catch table-not-found errors while the connector is still open, re-raising as `typer.BadParameter` with fuzzy suggestions.
- **Files**: `src/querido/cli/_pipeline.py`, `src/querido/cli/lineage.py`
- **Impact**: 1-3s saved per Snowflake command invocation
- **Status**: [x] Done

---

## P1 — High Value / Low-Medium Effort

### P1-1: DuckDB dist — CROSS JOIN bounds pattern
- **Problem**: `dist/duckdb.sql` uses repeated scalar subqueries. DuckDB v1.4.x does not have `WIDTH_BUCKET`.
- **Solution**: Rewrote to use `CROSS JOIN bounds` to materialize bounds once instead of repeated scalar subqueries. Kept FLOOR-based binning since WIDTH_BUCKET is not available.
- **Files**: `src/querido/sql/templates/dist/duckdb.sql`
- **Impact**: Eliminates redundant subquery evaluation, cleaner SQL
- **Status**: [x] Done

### P1-2: SQLite profile — single-scan aggregation
- **Problem**: Same UNION ALL per-column pattern as DuckDB. N scans instead of 1.
- **Solution**: Single-scan with all aggregations in one wide row. Uses `SUM(CASE)` instead of `COUNT_IF`, omits `MEDIAN`/`STDDEV` (SQLite limitation).
- **Files**: `src/querido/sql/templates/profile/sqlite.sql`
- **Impact**: 10-50x faster profiling on SQLite for wide tables
- **Status**: [x] Done

### P1-3: Memoize `get_columns()` on connector instances
- **Problem**: Multiple calls to `get_columns(table)` within a single command. Each call is a separate database round-trip.
- **Solution**: Added `_columns_cache` dict to all three connectors (SQLite, DuckDB, Snowflake). Cache keyed by normalized table name.
- **Files**: `src/querido/connectors/sqlite.py`, `src/querido/connectors/duckdb.py`, `src/querido/connectors/snowflake.py`
- **Impact**: Eliminates 1-2 duplicate round-trips per command
- **Status**: [x] Done

---

## P2 — Medium Value / Low-Medium Effort

### P2-1: Cache-backed existence checks
- **Problem**: Some paths (explore TUI, error recovery) still call `resolve_table()` which hits the database.
- **Solution**: Added `MetadataCache.has_table()`, `get_cached_columns()`, and `get_cached_tables()` methods. Available for integration into `resolve_table()`.
- **Files**: `src/querido/cache.py`
- **Impact**: Instant existence checks for Snowflake users with a warm cache
- **Status**: [x] Cache methods added; integration into validation deferred (P1-3 memoization covers most cases)

### P2-2: Dist templates — CROSS JOIN bounds pattern
- **Problem**: All three dist templates use repeated scalar subqueries.
- **Solution**: Rewrote all three dist templates (DuckDB, Snowflake, SQLite) to use `CROSS JOIN bounds`.
- **Files**: `src/querido/sql/templates/dist/duckdb.sql`, `src/querido/sql/templates/dist/snowflake.sql`, `src/querido/sql/templates/dist/sqlite.sql`
- **Impact**: More predictable performance, cleaner SQL
- **Status**: [x] Done

### P2-3: Dist — eliminate redundant `get_columns()` calls
- **Problem**: `get_distribution()` calls `get_columns()` even when the caller already has the column type.
- **Solution**: Added optional `column_type` parameter to `get_distribution()`. When provided, skips the `get_columns()` lookup. Also covered by P1-3 memoization.
- **Files**: `src/querido/core/dist.py`
- **Impact**: 1 fewer round-trip per dist command (also covered by memoization)
- **Status**: [x] Done

### P2-4: Snowflake RESULT_SCAN for chained queries
- **Problem**: Commands like `template` run count → profile → sample sequentially. Each re-scans the table.
- **Solution**: Research in progress. See findings below.
- **Files**: TBD
- **Impact**: Potentially significant for Snowflake
- **Status**: [ ] Research phase

---

## P3 — Medium Value / Low Effort

### P3-1: Parallelize `cache sync` column fetches
- **Problem**: `cache.sync()` calls `get_columns()` sequentially for each table.
- **Solution**: Added ThreadPoolExecutor-based parallel fetching when connector supports concurrent queries (max 4 workers).
- **Files**: `src/querido/cache.py`
- **Impact**: N sequential round-trips → ~N/4 with 4 workers for Snowflake
- **Status**: [x] Done

### P3-2: DuckDB `APPROX_COUNT_DISTINCT` in profile
- **Problem**: DuckDB profile uses exact `COUNT(DISTINCT)` which is expensive on large tables.
- **Solution**: Added `approx` parameter support to DuckDB profile template (included in P0-1 rewrite). Uses `APPROX_COUNT_DISTINCT` when `approx=True`.
- **Files**: `src/querido/sql/templates/profile/duckdb.sql`
- **Impact**: Faster cardinality estimation on large DuckDB tables
- **Status**: [x] Done (included in P0-1)

### P3-3: Parallelize `template` queries for concurrent connectors
- **Problem**: `get_template()` runs count, profile, and sample queries sequentially.
- **Solution**: When `connector.supports_concurrent_queries` is True, profile and sample queries run in parallel via ThreadPoolExecutor.
- **Files**: `src/querido/core/template.py`
- **Impact**: 2 sequential queries → 1 wall-clock round for Snowflake
- **Status**: [x] Done

---

## P4 — Lower Priority / Medium Effort

### P4-1: Cache-backed column resolution
- **Problem**: `resolve_column()` queries the database for column metadata just to do case-insensitive name matching.
- **Solution**: Check MetadataCache first for column names. Fall back to live query if cache is stale or missing.
- **Files**: `src/querido/cli/_validation.py`, `src/querido/cache.py`
- **Impact**: Instant column resolution for Snowflake with warm cache
- **Status**: [ ] Deferred — P1-3 memoization covers within-session case

### P4-2: Auto-warm cache on first command
- **Problem**: Users must manually run `qdo cache sync` to benefit from caching.
- **Solution**: Added `sync_tables_only()` to `MetadataCache` — a lightweight sync that caches only table names (not columns). Added `_maybe_warm_cache()` in `_pipeline.py` that triggers a background thread to populate the cache on the first command against a named Snowflake connection. Only fires when `supports_concurrent_queries` is True (Snowflake) and the connection is a named connection (not a file path). Daemon thread ensures it doesn't block command execution or prevent exit.
- **Files**: `src/querido/cache.py`, `src/querido/cli/_pipeline.py`
- **Impact**: After the first command, subsequent commands benefit from cached table lists for fuzzy suggestions and existence checks — without the user needing to run `qdo cache sync`
- **Status**: [x] Done

---

## P5 — Large Table Optimizations

### P5-1: SQLite — Bernoulli sampling instead of ORDER BY RANDOM
- **Problem**: `ORDER BY RANDOM() LIMIT N` requires a full scan + sort of the entire table — O(n log n). For a 1M row table sampling 100K rows, this took ~370ms.
- **Solution**: Replaced with Bernoulli-style filter: `WHERE ABS(RANDOM()) % (total/sample) = 0 LIMIT N`. Avoids the sort entirely — O(n) scan with early exit via LIMIT.
- **Files**: `src/querido/connectors/sqlite.py`
- **Impact**: ~7x faster sampling at 1M rows, grows with table size
- **Status**: [x] Done

### P5-2: SQLite — read-performance PRAGMAs
- **Problem**: Default SQLite settings leave performance on the table for read-heavy profiling.
- **Solution**: Set `PRAGMA journal_mode=WAL` (concurrent reads), `PRAGMA cache_size=-65536` (64MB page cache vs 2MB default), `PRAGMA mmap_size=268435456` (256MB memory-mapped I/O).
- **Files**: `src/querido/connectors/sqlite.py`
- **Impact**: Significant for large SQLite databases, especially on repeated queries within a session
- **Status**: [x] Done

### P5-3: Snowflake — APPROX_TOP_K for frequency queries
- **Problem**: Frequency queries use `GROUP BY + ORDER BY count DESC + LIMIT N`, which requires a full hash aggregate + sort. For high-cardinality columns on billions of rows, this is expensive.
- **Solution**: Added Snowflake-specific frequency template using `APPROX_TOP_K(col, N)` — a streaming Space-Saving algorithm (single pass, bounded memory, no sort). Result is FLATTENed from the ARRAY return format.
- **Files**: `src/querido/sql/templates/frequency/snowflake.sql`
- **Impact**: 2-5x faster frequency on high-cardinality Snowflake tables
- **Status**: [x] Done

### P5-4: Snowflake/DuckDB — block sampling for very large tables
- **Problem**: Current sampling uses row-level sampling. Block/system sampling skips entire storage blocks (5-10x faster) but only accepts percentages, not row counts.
- **Solution**: Added optional `row_count` kwarg to `sample_source()` on all connectors. When `row_count > 10M`, Snowflake uses `SAMPLE SYSTEM(pct)` (micropartition-level) and DuckDB uses `USING SAMPLE pct PERCENT (SYSTEM)` (row-group-level). `_build_sample_source` passes `row_count` through. Falls back to row sampling for smaller tables where exactness matters more.
- **Files**: `src/querido/connectors/base.py`, `src/querido/connectors/sqlite.py`, `src/querido/connectors/duckdb.py`, `src/querido/connectors/snowflake.py`, `src/querido/core/profile.py`
- **Impact**: 5-10x faster sampling on tables with billions of rows
- **Status**: [x] Done

### P5-5: Column batching for very wide tables
- **Problem**: For 100+ column tables, the single-scan profile query generates enormous SQL with hundreds of aggregation expressions. On Snowflake, this can be slow due to query compilation and execution overhead.
- **Solution**: Added `_profile_batched()` in `core/profile.py`. When `supports_concurrent_queries` is True and the table has >25 columns, splits `col_info` into batches of 25, renders a profile query per batch, executes them via ThreadPoolExecutor (max 4 workers), unpacks each batch's single wide row, and merges results in original column order.
- **Files**: `src/querido/core/profile.py`
- **Impact**: Better parallelism and reduced per-query overhead on 100+ column Snowflake tables
- **Status**: [x] Done

---

## Additional Optimizations (implemented after initial plan)

### Approximate median functions
- **DuckDB**: Uses `APPROX_QUANTILE(col, 0.5)` instead of `MEDIAN()` when `approx=True`
- **Snowflake**: Uses `APPROX_PERCENTILE(col, 0.5)` instead of `MEDIAN()` when `approx=True`
- **Files**: `src/querido/sql/templates/profile/duckdb.sql`, `src/querido/sql/templates/profile/snowflake.sql`
- **Status**: [x] Done

### Fold null_count into numeric dist queries
- **Problem**: Numeric dist command ran a separate `null_count` query (extra table scan) before the distribution query.
- **Solution**: Merged the `bounds` CTE into a `stats` CTE that computes MIN/MAX, total_rows, and null_count in a single pass. Distribution results now include `total_rows` and `null_count` columns. `get_distribution()` extracts these from the dist result instead of making a separate query.
- **Files**: `src/querido/sql/templates/dist/duckdb.sql`, `src/querido/sql/templates/dist/snowflake.sql`, `src/querido/sql/templates/dist/sqlite.sql`, `src/querido/core/dist.py`, `src/querido/cli/dist.py`
- **Impact**: Eliminates 1 round-trip for numeric distributions (the most common case)
- **Status**: [x] Done

---

## RESULT_SCAN Research Findings

### Summary
**RESULT_SCAN is not the right optimization for qdo's query patterns.**

### What RESULT_SCAN does
- `SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))` reads the materialized result of a prior query
- Session-scoped (same connection), results available for 24 hours
- Consumes minimal warehouse compute (reads cached result, not source table)
- Works with Arrow fetch, supports filtering/aggregation over the result
- Python access: `cursor.sfqid` gives the query ID after execution

### Why it doesn't help qdo
qdo's redundancy is "scanning the same table with different aggregations" — RESULT_SCAN only re-reads a prior *result set*, not the source data. Each command runs fundamentally different queries (count, profile, distribution, frequency) that produce different shapes.

### What Snowflake already does for free
- **Query result cache**: Identical SQL text against unchanged data returns instantly with zero warehouse compute (24h TTL). This means qdo's `COUNT(*)` queries are effectively free on repeat.
- **Micropartition metadata**: `COUNT(*)`, `MIN()`, `MAX()` can be answered from metadata alone without scanning data — automatic and free.

### Better alternatives (implemented above)
1. **Query consolidation**: Merged COUNT into profile (`total_rows`), merged null_count into dist templates
2. **Single-scan profiling**: All stats in one query pass (P0-1, P1-2)
3. **Parallelization**: Template + frequency queries run concurrently for Snowflake (P3-3)

### Potential future use
- `cursor.sfqid` could be captured for cost tracking / debugging / linking to Snowflake query history
- `APPROX_TOP_K(col, k)` could replace frequency queries for approximate top-N values
