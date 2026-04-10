# Ideas

Unimplemented ideas from earlier planning. Not committed to — just possibilities.

## qdo freshness — row freshness / staleness

"Is this table still being loaded?" is one of the most common analyst questions. The agent needs to answer it without the analyst knowing the column names.

- `qdo freshness -c CONN -t TABLE [--column updated_at]`
- Auto-detect timestamp column if not specified: scan columns for date/timestamp types, prefer names matching `updated_at`, `modified_at`, `created_at`, `loaded_at`, `_date`, `_timestamp`, `_at`
- Returns table, column, min, max, now, staleness_hours, row_count
- `--threshold N` — exit code 1 if staleness exceeds N hours (agent can use for assertions)

## Snowflake RESULT_SCAN for chained queries

Commands like `template` run count → profile → sample sequentially, each re-scanning the table. Snowflake's `RESULT_SCAN()` could let later steps reuse earlier result sets. Needs research into whether the connector can hold session state across calls.

## Embedding-based semantic search across metadata

Embed table/column metadata and descriptions using an embedding model, cache embeddings locally, and do cosine similarity search to find relevant tables/columns from a natural language query.

- `qdo embed build` — generate embeddings for all table/column metadata and store in local SQLite/DuckDB
- `qdo embed search "<query>"` — cosine similarity search using numpy
- Embedding sources: table names, column names, comments, business definitions (from metadata)
- Model options: OpenAI `text-embedding-3-small` (API), or local models via `sentence-transformers`
- Cache: store embeddings as numpy arrays in local database (BLOB) or `.npy` files
- Search: pure numpy cosine similarity — no vector DB dependency needed
- Optional dependency group: `uv pip install 'querido[embeddings]'`

## Local LLM for SQL generation

Use an open-weight local LLM to generate SQL from natural language, informed by table metadata, semantic descriptions, and example queries. Must work on CPU (slow) and GPU (fast).

- `qdo ai "<question>"` command
- Feed context: table schemas, column descriptions, example queries, semantic model info
- Model options: `llama-cpp-python` for CPU/GPU inference, or `mlx` on Apple Silicon
- Optional dependency group: `uv pip install 'querido[ai]'`

## Cache-backed column resolution

`resolve_column()` queries the database for column metadata just to do case-insensitive name matching. Could check MetadataCache first and fall back to a live query if stale. Deferred because within-session memoization already covers most cases.

## Web UI polish

- SQL workspace tab with CodeMirror editor
- WebSocket for live query execution progress
- Multiple connection switching (dropdown in nav)
- Saved pivot queries / bookmarks
- Chart rendering for distributions (e.g., Chart.js or Observable Plot)

## TUI enhancements

- Pivot/group-by mode
- Plot panel
- Multi-table joins
- Column selector: pattern filtering (glob/regex) in addition to checkbox selection
- Column selector: persist default pre-selection per table

## Fuzzy matching improvements

- Use `thefuzz` or edit-distance for higher-quality fuzzy matching in search and column resolution
- Optional dependency to avoid adding weight for basic usage

## Parquet/Arrow metadata

- Read Parquet/Arrow file-level metadata via `pyarrow.parquet.read_schema().metadata`
- Surface in `qdo inspect --verbose` for Parquet files

## Cache improvements

- Background cache refresh
- Incremental sync via `information_schema.tables.last_altered`
- Use DuckDB instead of SQLite for cache to enable analytics on cached metadata
