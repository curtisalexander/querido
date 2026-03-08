# qdo - Build Plan

This document tracks the incremental build plan for qdo. Each phase builds on the previous one and includes integration tests to verify correctness.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python (3.12+) | Snowflake has no official Rust driver; Python ecosystem (Rich, Textual, Jinja2) is vastly superior for data tooling |
| CLI framework | Typer | Readable, fast to develop, built on Click |
| SQL templating | Jinja2 | Industry standard (used by dbt), powerful, stores as `.sql` files |
| Config format | TOML | Safe, stdlib reader (`tomllib`), consistent with `pyproject.toml` |
| Config paths | platformdirs | Cross-platform config directory resolution (XDG on Linux, AppData on Windows, Library on macOS) |
| Output | Rich | Beautiful tables, panels, trees; Textual for TUI later |
| DB connectors | sqlite3 (stdlib), duckdb, snowflake-connector-python | Official/first-class support for each |
| Dependency mgmt | uv | Fast, modern Python package manager |
| Linting/formatting | ruff | Fast, replaces flake8/black/isort |
| Type checking | ty | Astral's type checker, pairs with ruff |
| Testing | pytest | Standard, minimal test overhead — enough to prove things work |
| Lazy imports | All heavy deps imported inside functions | Keeps CLI startup fast |

## Phase 1: Foundation

**Goal**: Bare-bones project that installs and runs `qdo --help`.

- [x] `pyproject.toml` — uv-managed, all deps, ruff/ty config, `[project.scripts]` entry point
- [x] `src/querido/__init__.py` — version string
- [x] `src/querido/cli/__init__.py` — Typer app definition
- [x] `src/querido/cli/main.py` — Entry point with `--version`, registers subcommand groups
- [x] `README.md` — Project overview with name story
- [x] `AGENTS.md` — Agent onboarding guide
- [x] `ARCHITECTURE.md` — System architecture
- [x] `.gitignore` — Python-appropriate
- [x] **Test**: `qdo --help` works, `qdo --version` prints version

## Phase 2: Connectors + Config + SQL Renderer

**Goal**: Connect to databases and render SQL templates.

- [x] `src/querido/connectors/base.py` — `Connector` Protocol (interface)
- [x] `src/querido/connectors/sqlite.py` — SQLite connector
- [x] `src/querido/connectors/duckdb.py` — DuckDB connector
- [x] `src/querido/connectors/factory.py` — Factory function to create connector from config
- [x] `src/querido/sql/renderer.py` — Jinja2 template loader/renderer
- [x] `src/querido/config.py` — TOML config loading, connection resolution, platformdirs paths
- [x] CLI flags: `--connection` (named from config OR inline path), `--db-type` (for inline paths)
- [x] `QDO_CONFIG` env var override for config directory
- [x] **Test**: Connect to in-memory SQLite/DuckDB, execute a simple query via connector
- [x] **Test**: Render a SQL template with parameters
- [x] **Test**: Load a named connection from a test TOML config

## Phase 2.5: Integration Test Infrastructure

**Goal**: Real databases with rich data for integration testing.

- [x] `scripts/init_test_data.py` — downloads CSVs, imports into SQLite + DuckDB
- [x] `scripts/init-test-data.sh` — bash wrapper
- [x] `scripts/init-test-data.ps1` — PowerShell wrapper
- [x] `data/` directory (gitignored) — CSVs + test.db + test.duckdb
- [x] Datasets: customers-1000 (strings, dates, emails) + products-1000 (numeric, categorical)
- [x] `tests/conftest.py` — integration fixtures with auto-skip when databases missing
- [x] `tests/integration/test_connectors.py` — 10 integration tests against real data
- [x] Source: [Datablist sample CSVs](https://github.com/datablist/sample-csv-files)

## Phase 3: `qdo inspect` — Table Metadata

**Goal**: Inspect a table's structure (columns, types, constraints).

- [x] `src/querido/cli/inspect.py` — `qdo inspect` subcommand (metadata via `get_columns()`, not SQL templates)
- [x] `src/querido/output/console.py` — Rich table output for metadata
- [x] Output includes: column name, data type, nullable, default value, primary key, row count
- [x] **Test**: Create test table in SQLite, run inspect, verify column info
- [x] **Test**: Create test table in DuckDB, run inspect, verify column info

## Phase 4: `qdo preview` — Quick Row Preview

**Goal**: See a handful of rows from a table.

- [x] `src/querido/sql/templates/preview/common.sql` — Simple SELECT with LIMIT (dialect-aware)
- [x] `src/querido/cli/preview.py` — `qdo preview` subcommand
- [x] `--rows` flag (default: 20)
- [x] Rich table output showing actual data
- [x] **Test**: Insert test data in SQLite/DuckDB, run preview, verify rows displayed

## Phase 4.5: Tutorial & Agent Quick Start

**Goal**: Onboarding docs for humans and agents.

- [x] `scripts/tutorial.py` — interactive step-by-step tutorial (`uv run python scripts/tutorial.py`)
- [x] `QUICKSTART.md` — concise agent-friendly reference (setup, commands, schemas, examples)
- [x] Update both as new commands are added (profile, etc.)

## Phase 5: `qdo profile` — Data Profiling

**Goal**: Statistical profile of table columns.

- [x] `src/querido/sql/templates/profile/sqlite.sql` — SQLite profiling queries
- [x] `src/querido/sql/templates/profile/duckdb.sql` — DuckDB profiling queries
- [x] `src/querido/cli/profile.py` — `qdo profile` subcommand
- [x] `--columns` optional filter to profile specific columns
- [x] `--sample <n>` flag for sampling (default: auto-sample if > 1M rows, sample size 100k)
- [x] `--no-sample` flag to force full table scan
- [x] Numeric columns: min, max, mean, median, stddev, null count, null %
- [x] String columns: min/max length, distinct count, null count, null %
- [x] All columns: total rows, null count, null %
- [x] **Test**: Profile numeric + string test data in SQLite/DuckDB, verify statistics

## Phase 6: Polish & Extend

- [x] Snowflake connector + SQL templates for all commands (mocked tests, pending real integration)
- [x] Parquet file support (via DuckDB's parquet reader — `.parquet` files auto-detected, registered as DuckDB views)
- [x] `qdo config add` / `qdo config list` commands to manage connections
- [x] Top N most frequent values in profile (`--top N` flag)
- [x] Progress spinners for long-running operations (Rich `Status` on stderr)

### Show executed SQL (`--show-sql`)

**Goal**: Let users see exactly what SQL is being run, with syntax highlighting.

- [x] Add `--show-sql` global flag to the Typer app (available on all commands)
- [x] When enabled, print the rendered SQL to stderr before executing it
- [x] Use Rich `Syntax` with `lexer="sql"` for terminal syntax highlighting
- [x] Print to stderr so stdout remains clean for piping/`--format` output

### Connection caching (Snowflake performance)

**Goal**: Avoid repeated SSO/MFA prompts when running multiple `qdo` commands in sequence.

- [x] Enable Snowflake's built-in credential caching by default (`client_store_temporary_credential=True`, `client_request_mfa_token=True`)
- [x] SSO ID tokens cached to OS keyring (macOS/Windows) or `~/.cache/snowflake/` (Linux)
- [x] MFA tokens cached to OS keyring so users aren't re-prompted
- [x] Users can disable via connection config (`client_store_temporary_credential = false`)
- [x] Tests: default-on behavior verified, opt-out verified

---

## Future Ideas (ordered by ease of implementation)

The items below are documented for future work. They are ordered from easiest to hardest, considering what we've already built (connectors, inspect, preview, profile, SQL templates, Rich output).

### F1: Copy-friendly output for coding agents ✅
**Ease: Easy** — We already produce structured data (list of dicts) in the output layer.

- [x] `--format {rich,markdown,json,csv}` global flag on all commands
- [x] `src/querido/output/formats.py` — markdown, JSON, CSV formatters for inspect/preview/profile/frequencies
- [x] `src/querido/cli/_util.py:get_output_format()` — reads format from root CLI context
- [x] All three commands (inspect, preview, profile) dispatch to format functions when `--format` != `rich`
- [x] `tests/test_format.py` — 10 tests covering all format × command combinations + invalid format

### F2: Extended metadata (comments, developer metadata) ✅
**Ease: Easy** — Small extensions to existing inspect queries.

- [x] `--verbose` / `-v` flag on `qdo inspect` to show comments/descriptions
- [x] `comment` field added to `get_columns()` dicts in all connectors (None for SQLite)
- [x] `get_table_comment()` method on all connectors (DuckDB: `duckdb_tables()`, Snowflake: `information_schema.tables`, SQLite: returns None)
- [x] DuckDB: queries `duckdb_columns()` for column comments, `duckdb_tables()` for table comments
- [x] Snowflake: queries `information_schema.columns` `COMMENT` field + `information_schema.tables`
- [x] SQLite: gracefully returns None (no native comment support)
- [x] All output formats (rich, markdown, json, csv) include comments when `--verbose`
- [x] Tests: 5 new tests covering verbose inspect with DuckDB comments, SQLite graceful fallback, and all format outputs
- Future: Parquet/Arrow metadata via `pyarrow.parquet.read_schema().metadata`

### F3: Quick SQL statement generation ✅
**Ease: Easy-Medium** — We already have Jinja2 templates and table metadata from `inspect`.

- [x] `qdo sql` command group with subcommands: `select`, `insert`, `ddl`, `task`, `udf`, `procedure`
- [x] `qdo sql select` — SELECT with all columns (all dialects)
- [x] `qdo sql insert` — INSERT with named placeholders (all dialects)
- [x] `qdo sql ddl` — CREATE TABLE DDL with types, nullability, defaults, PKs (all dialects)
- [x] `qdo sql task` — Snowflake task template (Snowflake only, errors on other dialects)
- [x] `qdo sql udf` — UDF template (SQLite: Python API guidance, DuckDB/Snowflake: SQL UDF)
- [x] `qdo sql procedure` — Stored procedure template (Snowflake only)
- [x] `qdo sql scratch` — CREATE TEMP TABLE + INSERTs with real sample data (`--rows N`, default 5)
- [x] All use `get_columns()` metadata, output plain text to stdout for copy-paste
- [x] Tests: 13 tests covering all subcommands, dialect routing, Snowflake-only guards

### F4: Metadata search with fuzzy matching
**Ease: Easy-Medium** — We have connectors and info schema access already.

Search across tables/views/columns in a database with fuzzy matching. For Snowflake, query `INFORMATION_SCHEMA.TABLES` and `INFORMATION_SCHEMA.COLUMNS`. For SQLite/DuckDB, use their respective catalog queries. Fuzzy matching can start simple (case-insensitive substring/LIKE) and optionally add edit-distance later.

- `qdo search <pattern>` command
- `--type {table,column,all}` filter
- `--schema` filter for Snowflake
- Results: table/view name, type, matching columns, schema
- Start with LIKE/ILIKE matching, consider `thefuzz` or similar lib for true fuzzy matching later

### F5: Column distribution visualization
**Ease: Medium** — We have profile (stats). Need to add histogram rendering and frequency tables.

Quickly visualize how a column's values are distributed. Numeric columns get a text-based histogram (Rich sparkline or bar chart). String/categorical columns get a frequency table with counts, percentages, and null handling. Always show null count and null percentage.

- `qdo dist <table> <column>` command (or `qdo profile --dist`)
- Numeric: bin values into N buckets (default 10-20), render as horizontal bar chart using Rich
- Categorical/string: top N values by frequency, count, percentage, cumulative %
- Always include NULL as a category
- Consider Rich's `Bar` or unicode block characters for histograms
- SQL: use `WIDTH_BUCKET` (DuckDB/Snowflake) or CASE-based binning (SQLite)

### F6: Table metadata template generation
**Ease: Medium** — Combines inspect + profile output into a structured template.

Generate a documentation template for a table that a user can fill in with business definitions. Auto-populate what we can (column name, type, nullable, distinct count, min/max, sample values) and leave placeholders for what humans must provide (business definition, data owner, SLA).

- `qdo template <table>` command
- Output formats: markdown table, CSV, or YAML
- Columns: name, type, nullable, distinct_count, min, max, sample_values, `<business_definition>`, `<data_owner>`, `<notes>`
- Runs inspect + profile queries under the hood
- Easy to copy into a wiki, spreadsheet, or docs repo

### F7: View definition / simple lineage
**Ease: Medium** — Each DB has a way to retrieve view DDL.

Retrieve the SQL definition of a view to understand what it's built from. This is the simplest form of lineage.

- `qdo lineage <view>` or `qdo view-sql <view>` command
- Snowflake: `GET_DDL('VIEW', '<name>')` or `INFORMATION_SCHEMA.VIEWS.VIEW_DEFINITION`
- DuckDB: `duckdb_views()` table function has `sql` column
- SQLite: `sqlite_master` table has `sql` column for views
- Display with syntax highlighting (Rich `Syntax` panel)

### F8: Snowflake semantic layer YAML templates
**Ease: Medium** — Generate YAML from metadata we already collect. Snowflake-specific.

Generate a starting-point YAML file for Snowflake Cortex Analyst semantic models (or the newer Semantic Views). Auto-populate table names, column names, data types, and any existing comments as descriptions. User fills in synonyms, metrics, verified queries, and business descriptions.

- `qdo snowflake semantic <table>` command
- Generates YAML following [Cortex Analyst semantic model spec](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst/semantic-model-spec)
- Structure: `name`, `tables[].name`, `tables[].base_table`, `tables[].dimensions[]`, `tables[].measures[]`
- Each dimension/measure: `name`, `expr`, `data_type`, `description` (from comments or placeholder)
- Also consider [Semantic Views YAML spec](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec) as the newer recommended approach
- Output to file or stdout

### F9: Snowflake data lineage (GET_LINEAGE)
**Ease: Medium** — Snowflake-specific, uses their built-in lineage functions. Requires Enterprise Edition.

Query Snowflake's [GET_LINEAGE](https://docs.snowflake.com/en/sql-reference/functions/get_lineage-snowflake-core) function to trace upstream and downstream dependencies for tables and columns.

- `qdo snowflake lineage <object>` command
- `--direction {upstream,downstream}` (default: downstream)
- `--domain {table,column}` — trace at table or column level
- `--depth <n>` (default: 5) — how many levels to traverse
- SQL: `SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE('<object>', '<domain>', '<direction>', <depth>))`
- Also consider `SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES` for simpler object-level deps
- Render as a Rich tree or table showing the dependency chain
- Note: requires Enterprise Edition — detect and warn gracefully

### F10: Interactive data exploration (Textual TUI)
**Ease: Medium-Hard** — Textual is designed to work with Rich, but building interactive widgets (filtering, sorting, pivoting) is substantial.

Build a terminal UI for interactive data exploration: scrollable data tables, filtering, sorting, and eventually pivot-table-like aggregation.

- `qdo explore <table>` command launches Textual app
- DataTable widget for scrollable rows with column sorting
- Filter bar: type expressions to filter rows
- Column statistics sidebar
- Future: pivot/group-by mode, plot panel
- Textual is a natural extension of Rich (same author, designed to interoperate)

**Architectural note:** This is where separation of business logic and display logic becomes critical. Query execution, data transformation, and statistics computation should live in a `core/` or `data/` layer that both CLI commands (Rich) and the TUI (Textual) can share. See architectural notes at the bottom.

### F11: Browser/HTML export & mini web app
**Ease: Medium-Hard** — Starts simple (static HTML export) but grows into a web app.

Export tables, profiles, and graphs to HTML for viewing in a browser. Start with static export (sortable HTML tables via a template), then optionally grow into a lightweight web app.

- Phase A: `--format html` on existing commands → generates standalone HTML file with sortable table (use a simple JS lib or just `<table>` with sort)
- Phase B: `qdo serve` launches a local web server (FastAPI/Starlette) showing connected tables with interactive exploration
- Phase B reuses the same core logic as CLI and TUI

**Architectural note:** Same separation concern as F10. The web layer should call into shared business logic, not reimplement queries. See architectural notes at the bottom.

### F12: Register & discover example programs
**Ease: Medium-Hard** — More of a design/workflow challenge than a technical one.

Register known-working example scripts/queries with rich descriptions and metadata. Store them locally and make them discoverable (search by description, table, tags).

- `qdo examples add <script>` — guided workflow to add metadata (description, tags, tables used, purpose)
- `qdo examples list` / `qdo examples search <query>`
- Storage: local SQLite database or TOML/YAML files in config directory
- Each example: script path, description, tags, tables referenced, last verified date
- Could auto-extract table references from SQL in the script

### F13: Embedding-based semantic search
**Ease: Hard** — Requires embedding model integration, caching, and similarity search.

Embed table/column metadata and descriptions using an embedding model (local or API-based like OpenAI), cache embeddings locally, and do cosine similarity search to find relevant tables/columns from a natural language query.

- `qdo embed build` — generate embeddings for all table/column metadata and store in local SQLite/DuckDB
- `qdo embed search "<query>"` — cosine similarity search using numpy
- Embedding sources: table names, column names, comments, business definitions (from F6 templates)
- Model options: OpenAI `text-embedding-3-small` (API), or local models via `sentence-transformers`
- Cache: store embeddings as numpy arrays in local database (BLOB) or `.npy` files
- Search: pure numpy cosine similarity — no vector DB dependency needed
- Optional dependency group: `pip install 'querido[embeddings]'`

### F14: Local LLM for SQL generation
**Ease: Hardest** — Heavy dependencies, GPU/CPU considerations. Implement last.

Use an open-weight local LLM to generate SQL from natural language, informed by table metadata, semantic descriptions, and example queries. Must work on CPU (slow) and GPU (fast).

- `qdo ai "<question>"` command
- Feed context: table schemas, column descriptions, example queries (from F12), semantic model info
- Model options: `llama-cpp-python` for CPU/GPU inference, or `mlx` on Apple Silicon
- Very heavy optional dependency: `pip install 'querido[ai]'`
- Prompt engineering: structured prompt with schema + examples → SQL
- This should be the LAST feature implemented due to dependency weight and complexity
- Consider making this a separate package (`qdo-ai`) that extends qdo via plugin

---

## Architectural Notes for Future Features

Several future features (F10 TUI, F11 web app, F5 distribution, F6 templates) point to a need for better separation between **business logic** and **presentation**. Currently, CLI commands directly call connectors and pass results to Rich output. This works fine for a CLI-only tool but breaks down when the same logic needs to drive a TUI, web app, and export formats.

### Recommended refactor (before F10/F11)

Introduce a `src/querido/core/` layer:

```
src/querido/core/
├── inspect.py      # get_table_metadata(connector, table) → structured result
├── preview.py      # get_preview(connector, table, limit) → rows
├── profile.py      # get_profile(connector, table, columns, sample) → stats
├── search.py       # search_metadata(connector, pattern, type) → matches
├── distribution.py # get_distribution(connector, table, column) → bins/freqs
└── lineage.py      # get_lineage(connector, object, direction) → tree
```

Each core function returns a typed dataclass/dict — no Rich imports, no display logic. Then:
- `cli/*.py` calls core functions → passes results to `output/console.py` (Rich)
- `tui/*.py` calls core functions → passes results to Textual widgets
- `web/*.py` calls core functions → passes results to HTML templates or JSON API

This refactor is **not needed now** — the current structure is fine for CLI-only phases. But it should happen before F10/F11 to avoid duplicating query logic across presentation layers.

### Optional dependency groups (projected)

```toml
[project.optional-dependencies]
duckdb = ["duckdb>=1.0"]
snowflake = ["snowflake-connector-python>=3.0"]
tui = ["textual>=0.50"]
web = ["fastapi", "uvicorn", "jinja2"]  # jinja2 already a dep
embeddings = ["numpy", "openai"]  # or sentence-transformers for local
ai = ["llama-cpp-python"]  # or separate package entirely
```
