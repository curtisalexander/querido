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
- [x] `AGENTS.md` — agent onboarding guide (consolidated from earlier QUICKSTART.md)
- [x] Update docs as new commands are added (profile, etc.)

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

## Phase 7: Core Layer Refactor

**Goal**: Extract business logic from CLI commands into a reusable `src/querido/core/` layer. Each core function accepts a `Connector` and returns plain data (dicts/lists) — no Rich imports, no CLI concerns, no display logic. This enables the TUI (F10), web app (F11), and any future presentation layer to share the same query logic.

**Why now**: The CLI commands currently mix input validation, query execution, and output rendering in one function. Before building the Textual TUI (F10), we need to separate "get the data" from "display the data" so both CLI and TUI can call the same core functions.

### Core modules to create

- [x] `src/querido/core/__init__.py` — package marker
- [x] `src/querido/core/preview.py` — `get_preview(connector, table, limit) → list[dict]`
  - Renders preview template, executes, returns rows
- [x] `src/querido/core/inspect.py` — `get_inspect(connector, table, verbose=False) → dict`
  - Returns `{"columns": [...], "row_count": int, "table_comment": str | None}`
  - Calls `get_columns()`, count template, optional `get_table_comment()`
- [x] `src/querido/core/profile.py` — `get_profile(connector, table, columns=None, sample=None, no_sample=False) → dict`
  - Returns `{"stats": [...], "row_count": int, "sampled": bool, "sample_size": int | None}`
  - Encapsulates sampling logic (auto-sample >1M rows, dialect-specific sample syntax)
  - `get_frequencies(connector, table_or_source, columns, top) → dict[str, list[dict]]`
- [x] `src/querido/core/search.py` — `search_metadata(connector, pattern, search_type, schema=None) → list[dict]`
  - Move `_search_metadata()` from `cli/search.py`
  - `try_cached_search(connection_name, pattern, search_type) → list[dict] | None`
- [x] `src/querido/core/dist.py` — `get_distribution(connector, table, column, buckets=20, top=20) → dict`
  - Returns `{"mode": "numeric"|"categorical", "total_rows": int, "null_count": int, "buckets"|"values": [...]}`
  - Handles numeric vs categorical branching, null counting
- [x] `src/querido/core/lineage.py` — `get_view_definition(connector, view) → dict`
  - Returns `{"view": str, "dialect": str, "definition": str}`
- [x] `src/querido/core/template.py` — `get_template(connector, table, sample_values=3) → dict`
  - Orchestrates inspect + profile + preview to build documentation template

### CLI refactor

- [x] Refactor `cli/preview.py` to call `core.preview.get_preview()` then dispatch to output
- [x] Refactor `cli/inspect.py` to call `core.inspect.get_inspect()` then dispatch to output
- [x] Refactor `cli/profile.py` to call `core.profile.get_profile()` + `get_frequencies()` then dispatch to output
- [x] Refactor `cli/search.py` to call `core.search.search_metadata()` then dispatch to output
- [x] Refactor `cli/dist.py` to call `core.dist.get_distribution()` then dispatch to output
- [x] Refactor `cli/lineage.py` to call `core.lineage.get_view_definition()` then dispatch to output
- [x] Refactor `cli/template.py` to call `core.template.get_template()` then dispatch to output

### Design rules for core/

1. **No Rich, no Typer, no CLI imports** — core/ is pure business logic
2. **Lazy imports** still apply — `jinja2`, `duckdb`, etc. imported inside functions
3. **Accept a `Connector`** — never resolve connections; that's the caller's job
4. **Return plain dicts/lists** — no dataclasses yet (keeps it simple, matches existing output functions)
5. **Raise plain exceptions** — `ValueError`, `LookupError`; callers translate to `typer.BadParameter` or TUI error panels
6. **`maybe_show_sql()` and `set_last_sql()`** remain in CLI layer — core functions can optionally return the rendered SQL for callers to log/display

### Tests

- [x] `tests/test_core.py` — 26 unit tests for each core function (SQLite + DuckDB)
- [x] Existing CLI tests still pass (261 total, 24 skipped)

---

## Phase 8: `qdo explore` — Interactive TUI (F10)

**Goal**: Launch a Textual terminal UI for interactive data exploration — scrollable data tables, column sorting, row filtering, and a metadata sidebar.

### New dependency

- [x] Add `textual` to `[project.optional-dependencies]`: `tui = ["textual>=0.50"]`
- [x] Add `textual-dev` to dev dependencies for testing/debugging
- [x] Lazy import in `cli/explore.py` with helpful install message if missing

### CLI entry point

- [x] `src/querido/cli/explore.py` — `qdo explore -t <table> -c <connection> [--db-type]`
  - Resolves connection, creates connector
  - Launches Textual app, passing connector + table name
  - Register in `cli/main.py`

### TUI module structure

```
src/querido/tui/
├── __init__.py
├── app.py           # ExploreApp(App) — main Textual application
├── screens/
│   ├── __init__.py
│   ├── table.py     # TableScreen — primary data exploration screen
│   └── inspect.py   # InspectScreen — column metadata overlay
└── widgets/
    ├── __init__.py
    ├── filter_bar.py  # FilterBar — input widget for row filtering
    ├── status_bar.py  # StatusBar — connection info, row count, filter status
    └── sidebar.py     # MetadataSidebar — column stats panel
```

### Core screens and widgets

- [x] **ExploreApp** (`tui/app.py`)
  - Accepts connector + table name
  - DataTable with sortable columns (click header to cycle asc/desc/none)
  - Key bindings: `q` quit, `?` help, `i` inspect, `m` sidebar, `/` filter, `Escape` clear filter, `r` refresh
  - CSS styling for layout (header, filter bar, data table, sidebar, status bar)

- [x] **FilterBar** (`tui/widgets/filter_bar.py`)
  - Text input at top of screen
  - Supports SQL WHERE expressions: `column = value`, `column > N`, `column LIKE '%pattern%'`
  - Translates filter to SQL WHERE clause, re-queries via `core/`
  - Shows filtered status in status bar

- [x] **MetadataSidebar** (`tui/widgets/sidebar.py`)
  - Toggle with `m` key
  - Shows column metadata (name, type, nullable, PK, comments)
  - Uses `core.inspect.get_inspect()` for column metadata

- [x] **StatusBar** (`tui/widgets/status_bar.py`)
  - Shows: table name, row count (displayed/total), filter status, current sort column + direction

- [x] **InspectScreen** (`tui/screens/inspect.py`)
  - Modal/overlay showing full column metadata (like `qdo inspect -v`)
  - Uses `core.inspect.get_inspect(verbose=True)`
  - Dismiss with `Escape` or `q`

- [x] **HelpScreen** (`tui/screens/help.py`)
  - Modal overlay showing all key bindings
  - Dismiss with `Escape`, `q`, or `?`

### Key bindings

| Key | Action |
|-----|--------|
| `q` | Quit |
| `?` | Show help overlay |
| `i` | Toggle inspect panel |
| `m` | Toggle metadata sidebar |
| `/` | Focus filter bar |
| `Escape` | Clear filter / close overlay |
| `r` | Refresh data |

### Tests

- [x] `tests/test_explore.py` — 5 tests: CLI help, missing args, invalid table name, nonexistent table
- [x] `tests/test_tui.py` — 14 tests using Textual's `pilot` testing framework
  - App launches with test data (SQLite + DuckDB)
  - DataTable populates with correct rows and columns
  - Max rows limit respected
  - Inspect screen opens and dismisses via action
  - Help screen opens and dismisses via action
  - Sidebar toggles via action
  - Status bar shows table name, row count, filter/sort indicators
  - Filter bar receives focus via action
  - Column metadata loaded on mount

### Phased delivery

Build incrementally within this phase:
1. **P8a**: ExploreApp + TableScreen with DataTable (view-only, scrollable, sortable)
2. **P8b**: FilterBar + StatusBar (filter rows by expression)
3. **P8c**: MetadataSidebar + InspectScreen (column stats on demand)

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

### F4: Metadata search with fuzzy matching ✅
**Ease: Easy-Medium** — We have connectors and info schema access already.

- [x] `qdo search` command with `--pattern` / `-p` for case-insensitive substring matching
- [x] `--type {table,column,all}` filter (default: `all`)
- [x] `--schema` filter for Snowflake
- [x] `get_tables()` method added to Connector Protocol and all connectors (SQLite, DuckDB, Snowflake)
- [x] Results: table/view name, type, match type (table/column), column name, column type
- [x] All output formats supported (rich, markdown, json, csv)
- [x] Detects views vs tables
- [x] Tests: 13 tests covering table/column search, type filter, view detection, DuckDB, all output formats
- Future: consider `thefuzz` or edit-distance for true fuzzy matching

### F5: Column distribution visualization ✅
**Ease: Medium** — We have profile (stats). Need to add histogram rendering and frequency tables.

- [x] `qdo dist` command with `--table`, `--column`, `--connection` options
- [x] Numeric columns: bin values into N buckets (`--buckets`, default 20), render as horizontal bar chart with unicode block characters
- [x] Categorical/string columns: top N values by frequency (`--top`, default 20), count, percentage
- [x] NULL count always shown
- [x] SQL templates: `WIDTH_BUCKET` (DuckDB), `FLOOR`-based binning (DuckDB), CASE-based binning (SQLite), Snowflake `WIDTH_BUCKET`
- [x] All output formats supported (rich, markdown, json, csv)
- [x] Tests: 15 tests covering numeric/categorical, SQLite/DuckDB, all formats, edge cases (empty table, single value, top flag)

### F6: Table metadata template generation ✅
**Ease: Medium** — Combines inspect + profile output into a structured template.

- [x] `qdo template` command — generates a documentation template for a table
- [x] Auto-populates: column name, type, nullable, distinct count, null count/%, min/max, sample values
- [x] Leaves placeholder fields: `<business_definition>`, `<data_owner>`, `<notes>`
- [x] `--sample-values N` flag (default 3, 0 to skip) — controls how many sample values per column
- [x] Runs inspect + profile + preview queries under the hood
- [x] Includes table/column comments when available (DuckDB, Snowflake)
- [x] All output formats: rich, markdown, json, csv
- [x] Tests: 10 tests covering SQLite, DuckDB, all formats, comments, error handling

### F7: View definition / simple lineage ✅
**Ease: Medium** — Each DB has a way to retrieve view DDL.

- [x] `qdo lineage` command with `--view`, `--connection` options
- [x] `get_view_definition()` method added to Connector Protocol and all connectors
- [x] SQLite: queries `sqlite_master WHERE type='view'` for the `sql` column
- [x] DuckDB: queries `duckdb_views()` for the `sql` column
- [x] Snowflake: queries `information_schema.views` for `VIEW_DEFINITION`
- [x] Rich output: syntax-highlighted SQL in a Rich Panel with line numbers
- [x] All output formats supported (rich, markdown, json, csv)
- [x] Graceful errors: table-not-view, nonexistent view, invalid name
- [x] Tests: 11 tests covering SQLite/DuckDB, all formats, error cases, connector methods

### F8: Snowflake semantic layer YAML templates ✅
**Ease: Medium** — Generate YAML from metadata we already collect. Snowflake-specific.

- [x] `qdo snowflake semantic --table <table> --connection <conn>` command
- [x] Generates YAML following Cortex Analyst semantic model spec
- [x] Structure: `name`, `tables[].name`, `tables[].base_table`, `tables[].dimensions[]`, `tables[].time_dimensions[]`, `tables[].measures[]`
- [x] Auto-classifies columns: IDs/keys → dimensions, dates/timestamps → time_dimensions, numerics → measures
- [x] Each dimension/measure: `name`, `expr`, `data_type`, `description` (from comments or `<description>` placeholder), `synonyms`
- [x] Measures include `default_aggregation: sum`
- [x] `--output / -o` flag to write YAML to file instead of stdout
- [x] Errors gracefully on non-Snowflake connections
- [x] Tests: 10 unit tests (YAML generation, column classification) + 2 CLI rejection tests

### F9: Snowflake data lineage (GET_LINEAGE) ✅
**Ease: Medium** — Snowflake-specific, uses their built-in lineage functions. Requires Enterprise Edition.

- [x] `qdo snowflake lineage --object <fqn> --connection <conn>` command
- [x] `--direction {upstream,downstream}` (default: downstream)
- [x] `--domain {table,column}` — trace at table or column level
- [x] `--depth <n>` (default: 5) — how many levels to traverse
- [x] SQL: `SELECT * FROM TABLE(SNOWFLAKE.CORE.GET_LINEAGE(...))`
- [x] All output formats supported (rich, markdown, json, csv)
- [x] Rich output: table with dynamic columns from GET_LINEAGE results
- [x] Errors gracefully on non-Snowflake connections with clear message
- [x] Input validation for direction and domain parameters
- [x] Tests: 3 CLI rejection/validation tests + 6 output format unit tests

### F10: Interactive data exploration (Textual TUI) — see Phase 7 + Phase 8
**Ease: Medium-Hard** — Textual is designed to work with Rich, but building interactive widgets (filtering, sorting, pivoting) is substantial.

Promoted to Phase 7 (core refactor) + Phase 8 (TUI implementation). See above for detailed plan.

- Future extensions (post-Phase 8): pivot/group-by mode, plot panel, multi-table joins

### F11: Browser/HTML export & mini web app
**Ease: Medium-Hard** — Starts simple (static HTML export) but grows into a web app.

Export tables, profiles, and graphs to HTML for viewing in a browser. Start with static export (sortable HTML tables via a template), then optionally grow into a lightweight web app.

#### Phase A: `--format html` (standalone HTML export) ✅

- [x] `src/querido/output/html.py` — HTML rendering module with shared `_html_page()` shell
  - `_html_page()` builds a complete standalone HTML document (reusable for Phase B web app layout)
  - `_build_table()` generates `<table>` with `<thead>`/`<tbody>` and `data-idx` attributes for stable sort
  - Embedded CSS: light/dark mode (`prefers-color-scheme`), sticky headers, hover highlights, responsive layout
  - Embedded JS: column sorting (click header to cycle asc/desc/none, numeric-aware), row filtering (text input), copy to clipboard (tab-separated), CSV export (download), toast notifications
  - `open_html()` writes to temp file and opens in default browser via `webbrowser.open()`
- [x] `--format html` added to valid formats in `cli/main.py`
- [x] `emit_html()` helper in `cli/_util.py` — writes temp file, opens browser, prints path to stderr
- [x] All commands dispatch to HTML format: inspect, preview, profile, search, dist, template, lineage, snowflake lineage, frequencies
- [x] HTML format functions: `format_inspect_html()`, `format_preview_html()`, `format_profile_html()`, `format_search_html()`, `format_dist_html()`, `format_template_html()`, `format_lineage_html()`, `format_snowflake_lineage_html()`, `format_frequencies_html()`
- [x] Tables in the browser support: click-to-sort columns, filter rows by text, copy visible rows to clipboard, export visible rows as CSV download
- [x] **Tests**: `tests/test_html_format.py` — 10 tests covering all commands, interactive JS presence, dark mode, export buttons

#### Phase B: `qdo serve` (local web app) ✅

- [x] `web = ["fastapi>=0.115", "uvicorn[standard]>=0.34", "python-multipart>=0.0.18"]` optional dependency group
- [x] `src/querido/web/__init__.py` — FastAPI app factory (`create_app(connector, connection_name)`)
- [x] `src/querido/web/routes/pages.py` — Full-page routes: landing (`/`), table detail (`/table/{name}`)
- [x] `src/querido/web/routes/fragments.py` — HTMX fragment endpoints: inspect, preview, profile, dist, template, lineage, search
- [x] `src/querido/web/routes/pivot.py` — Pivot builder page + POST execution endpoint
- [x] `src/querido/web/static/style.css` — Extended Phase A CSS (nav, sidebar, cards, tabs, dist bars, pivot form, light/dark mode)
- [x] `src/querido/web/static/app.js` — Sort/filter/copy/export JS + keyboard shortcuts (`?` help, `/` search, `Esc` close)
- [x] `src/querido/web/templates/` — Jinja2 templates: base layout, landing, table detail, pivot builder, 7 partials
- [x] `src/querido/core/pivot.py` — `build_pivot_query()` + `get_pivot()` for ad-hoc GROUP BY summarization
- [x] `src/querido/cli/serve.py` — `qdo serve --connection <name> --port 8888 --host 127.0.0.1`
- [x] Frontend: server-rendered Jinja2 + HTMX for dynamic tab loading + Alpine.js for UI state — no Node/npm build step
- [x] HTMX interaction: tabs load fragments into `#tab-content`, search debounces with 300ms delay, column names click for distribution
- [x] Error handling: `ValueError` → 400, `LookupError` → 404, user-friendly HTML error messages
- [x] SQLite `check_same_thread=False` for async web server compatibility
- [x] `tests/test_web.py` — 27 tests via FastAPI `TestClient` (landing, table detail, all fragments, search, pivot, input validation, pivot query builder)

#### Phase C: `qdo serve` polish — future

- SQL workspace tab with CodeMirror editor (deferred from Phase B)
- WebSocket for live query execution progress
- Multiple connection switching (dropdown in nav)
- Saved pivot queries / bookmarks
- Chart rendering for distributions (e.g., Chart.js or Observable Plot)

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
- Optional dependency group: `uv pip install 'querido[embeddings]'`

### F14: Local LLM for SQL generation
**Ease: Hardest** — Heavy dependencies, GPU/CPU considerations. Implement last.

Use an open-weight local LLM to generate SQL from natural language, informed by table metadata, semantic descriptions, and example queries. Must work on CPU (slow) and GPU (fast).

- `qdo ai "<question>"` command
- Feed context: table schemas, column descriptions, example queries (from F12), semantic model info
- Model options: `llama-cpp-python` for CPU/GPU inference, or `mlx` on Apple Silicon
- Very heavy optional dependency: `uv pip install 'querido[ai]'`
- Prompt engineering: structured prompt with schema + examples → SQL
- This should be the LAST feature implemented due to dependency weight and complexity
- Consider making this a separate package (`qdo-ai`) that extends qdo via plugin

### F15: Fuzzy table/column name suggestions in error messages ✅
**Ease: Easy-Medium** — Small addition to the existing error handling infrastructure.

- [x] `_fuzzy_suggestions()` helper using `difflib.get_close_matches()` (stdlib, zero deps)
- [x] `_format_not_found()` shared helper for building "not found" messages with suggestions
- [x] `resolve_table()` shows "Did you mean: ..." with top 3 matches
- [x] `resolve_column()` shows "Did you mean: ..." with top 3 matches and table context
- [x] Full "Available tables/columns:" list shown for small counts (≤30), omitted for large databases
- [x] Original casing preserved in suggestions (handles case-insensitive matching)
- [x] Tests: 11 tests covering table/column fuzzy suggestions, large lists, casing, unit tests
- Future: consider `thefuzz` (optional dependency) for higher-quality fuzzy matching

### F16: Local metadata cache for fast search and suggestions ✅
**Ease: Medium** — Requires cache invalidation strategy and schema change detection.

- [x] `qdo cache sync --connection <name>` — fetch all table/column metadata and store locally
- [x] `qdo cache status` — show cache age, table count, staleness (all output formats)
- [x] `qdo cache clear` — remove cached metadata (all connections or specific)
- [x] `src/querido/cache.py` — `MetadataCache` class with SQLite-backed storage
- [x] Storage: local SQLite database in the config directory (`~/.config/qdo/cache.db`)
  - Tables: `cached_tables(connection, table_name, table_type, cached_at)`
  - Columns: `cached_columns(connection, table_name, column_name, column_type, nullable, comment, cached_at)`
- [x] Automatic staleness detection: cache expires after configurable TTL (default: 24h)
- [x] `qdo search` checks cache first, falls back to live query
- [x] `--no-cache` flag on `qdo search` to bypass cache
- [x] Tests: 14 tests covering sync, status, clear, freshness, re-sync, CLI commands, search integration, DuckDB
- Future: background cache refresh, incremental sync via `information_schema.tables.last_altered`
- Future: use DuckDB instead of SQLite for cache to enable analytics on cached metadata

---

## Phase 9: Agent-Ready Data Interface

**Goal**: Transform qdo from a set of canned reports into a general-purpose data interface that a coding agent can use to explore, query, and validate data on behalf of a data analyst. Every new command returns structured output (JSON/CSV/markdown) suitable for agent consumption, and follows the existing `table_command` → `core/` → `dispatch_output` pattern.

### F17: Ad-hoc SQL execution (`qdo query`) ✨ **Highest priority**

**Ease: Easy** — Connectors already have `execute()`, output layer already handles `list[dict]`. This is mostly wiring.

**Why**: Without this, the agent is limited to canned commands. With it, the agent can ask any question about the data.

- [ ] `src/querido/cli/query.py` — `qdo query --connection <name> --sql "select ..." [--format json]`
- [ ] `src/querido/core/query.py` — `run_query(connector, sql) → dict` returning `{"columns": [...], "rows": [...], "row_count": int}`
- [ ] Three SQL input modes:
  - `--sql "select ..."` — inline SQL string
  - `--file query.sql` — read SQL from a file
  - stdin — `echo "select ..." | qdo query -c mydb` (detect with `sys.stdin.isatty()`)
  - Priority: `--sql` > `--file` > stdin; error if none provided and stdin is a tty
- [ ] **No table name validation** — the user provides arbitrary SQL, so we skip `validate_table_name()` but still use parameterized execution where possible
- [ ] `--limit N` flag (default: 1000) — append `LIMIT N` as a safety net (agent can override with `--limit 0` for no limit)
- [ ] Use `run_cancellable()` from `core/runner.py` for cancellation support
- [ ] Spinner via `query_status` on stderr
- [ ] `--show-sql` works as expected (echoes the SQL to stderr)
- [ ] All output formats: rich, markdown, json, csv, html
- [ ] `output/console.py:print_query()` — Rich table with dynamic columns from result set
- [ ] `output/formats.py:format_query()` — JSON/CSV/markdown formatters
- [ ] `output/html.py:format_query_html()` — HTML with interactive table
- [ ] Register in `cli/main.py`
- [ ] Tests: inline SQL, file input, stdin input, limit flag, empty result set, SQL error handling, all output formats

**Design note**: This command intentionally does NOT validate or parse the SQL. The connector's `execute()` handles errors, and we surface them via `friendly_errors`. The `--limit` safety net is appended naively — if the user's SQL already has a LIMIT, theirs wins (we wrap in a subquery or just document the behavior).

### F18: Full catalog export (`qdo catalog`)

**Ease: Easy** — Cache already stores all metadata. `get_tables()` + `get_columns()` exist on every connector.

**Why**: An agent needs to see the entire database schema in one call to plan queries. Running `inspect` per table is N+1 queries.

- [ ] `src/querido/cli/catalog.py` — `qdo catalog --connection <name> [--format json]`
- [ ] `src/querido/core/catalog.py` — `get_catalog(connector) → dict`
  - Returns `{"tables": [{"name": str, "type": "table"|"view", "row_count": int, "columns": [{"name", "type", "nullable", "comment"}]}]}`
  - Calls `get_tables()` once, then `get_columns()` per table (parallelized for concurrent connectors)
  - Row counts via count template per table (parallelized)
- [ ] **Cache-first by default** — prefer cached metadata when fresh, fall back to live query
  - Default: use cache if fresh (within TTL), else query live
  - `--live` flag to bypass cache and force live queries
  - `--cache-ttl N` override (seconds) for staleness threshold
- [ ] `--tables-only` flag — skip columns and row counts, just list tables with types
- [ ] `--schema` filter for Snowflake
- [ ] All output formats (JSON is the primary agent-facing format)
- [ ] Tests: full catalog, tables-only, cache mode, DuckDB + SQLite, all formats

**Design note**: For large Snowflake databases (hundreds of tables), full catalog with row counts could be slow. The `--use-cache` flag + `--tables-only` flag give the agent escape hatches. Consider adding `--include-counts / --no-counts` to skip row counts specifically.

### F19: Distinct value enumeration (`qdo values`)

**Ease: Easy** — Simple `select distinct` query with cardinality guard.

**Why**: When an agent needs to write a WHERE clause filtering on `status` or `region`, it needs to know the valid values. `dist --top N` shows frequencies but not *all* values. This fills that gap.

- [ ] `src/querido/cli/values.py` — `qdo values --connection <name> --table <table> --column <col>`
- [ ] `src/querido/core/values.py` — `get_distinct_values(connector, table, column, max_values=1000) → dict`
  - Returns `{"column": str, "distinct_count": int, "values": [...], "truncated": bool, "total_rows": int}`
  - First queries `count(distinct col)` — if > `max_values`, returns truncated=True with top N by frequency
  - If ≤ `max_values`, returns all distinct values sorted
- [ ] `--max N` flag (default: 1000) — maximum distinct values to return
- [ ] `--sort {value,frequency}` flag (default: value) — sort alphabetically or by count
- [ ] SQL template: `sql/templates/values/common.sql` — `select distinct "col" from "table" order by 1`
- [ ] All output formats
- [ ] Tests: low cardinality (all values), high cardinality (truncated), sort modes, null handling, all formats

### F20: Pivot / aggregate as CLI command (`qdo pivot`)

**Ease: Easy** — `core/pivot.py` already exists and works. Just needs a CLI entry point.

**Why**: Quick aggregations without writing raw SQL. The agent can answer "what's the total revenue by region?" without composing SQL.

- [ ] `src/querido/cli/pivot.py` — `qdo pivot --connection <name> --table <table> --group-by col1,col2 --agg "sum(amount),count(*)" [--filter "status = 'active'"]`
- [ ] Wire existing `core.pivot.get_pivot()` to CLI with spinner + output dispatch
- [ ] `--group-by` accepts comma-separated column names
- [ ] `--agg` accepts comma-separated aggregation expressions (count, sum, avg, min, max)
- [ ] `--filter` optional WHERE clause (passed through, not validated — like the TUI filter bar)
- [ ] `--order-by` optional ORDER BY (default: group-by columns)
- [ ] `--limit N` optional row limit on result
- [ ] All output formats
- [ ] Tests: basic pivot, multiple group-by, multiple aggs, filter, all formats

**Design note**: May need to extend `core/pivot.py` to support `--filter` and `--order-by` — currently it only takes rows/values/agg.

### F21: Row freshness / staleness (`qdo freshness`)

**Ease: Easy-Medium** — Needs timestamp column auto-detection heuristic.

**Why**: "Is this table still being loaded?" is one of the most common analyst questions. The agent needs to answer it without the analyst knowing the column names.

- [ ] `src/querido/cli/freshness.py` — `qdo freshness --connection <name> --table <table> [--column updated_at]`
- [ ] `src/querido/core/freshness.py` — `get_freshness(connector, table, column=None) → dict`
  - Returns `{"table": str, "column": str, "min": str, "max": str, "now": str, "staleness_hours": float, "row_count": int}`
  - If `--column` not specified, auto-detect: scan `get_columns()` for date/timestamp types, prefer names matching `updated_at`, `modified_at`, `created_at`, `loaded_at`, `_date`, `_timestamp`, `_at` patterns
  - Error if no timestamp column found and none specified
- [ ] `--threshold` optional — exit code 1 if staleness exceeds N hours (agent can use for assertions)
- [ ] All output formats
- [ ] Tests: explicit column, auto-detect, threshold exit code, no timestamp column error, all formats

### F22: Assertion / test framework (`qdo assert`)

**Ease: Easy** — Thin wrapper around `qdo query` with exit code semantics.

**Why**: Lets the agent verify assumptions programmatically. "Are there negative amounts?" → run assertion → exit code 0/1. No output parsing needed.

- [ ] `src/querido/cli/assert_cmd.py` — `qdo assert --connection <name> --sql "select count(*) from orders where amount < 0" --expect 0`
- [ ] `src/querido/core/assert_check.py` — `run_assertion(connector, sql, operator, expected) → dict`
  - Returns `{"passed": bool, "actual": value, "expected": value, "operator": str, "sql": str}`
- [ ] Comparison operators: `--expect N` (equals), `--expect-gt N`, `--expect-lt N`, `--expect-gte N`, `--expect-lte N`, `--expect-between N M`
  - Compares the first column of the first row of the result
- [ ] `--name "descriptive name"` optional — included in output for human readability
- [ ] Exit code: 0 = passed, 1 = failed, 2 = SQL error
- [ ] All output formats (JSON is most useful: `{"passed": true, "actual": 0, "expected": 0}`)
- [ ] `--quiet` flag — no output, just exit code (for scripting)
- [ ] Tests: pass/fail for each operator, SQL error, quiet mode, all formats

### F23: Data quality summary (`qdo quality`)

**Ease: Medium** — Multiple checks, each a separate SQL query. Parallelizable.

**Why**: Quick health check on a table. Agent can scan for problems without writing bespoke queries per column.

- [ ] `src/querido/cli/quality.py` — `qdo quality --connection <name> --table <table> [--columns col1,col2]`
- [ ] `src/querido/core/quality.py` — `get_quality(connector, table, columns=None) → dict`
  - Returns per-column quality metrics:
    ```
    {"table": str, "row_count": int, "columns": [
      {"name": str, "type": str,
       "null_count": int, "null_pct": float,
       "distinct_count": int, "uniqueness_pct": float,
       "duplicate_count": int,
       "min": value, "max": value,
       "status": "ok"|"warn"|"fail",
       "issues": ["52% null", "0% unique"]}
    ]}
    ```
  - Status logic: fail if >90% null or 0 distinct; warn if >20% null or uniqueness <1% (configurable?)
  - **No referential integrity checks** — FK relationships are out of scope; keep this focused on per-column basics
- [ ] `--check-duplicates` flag — check for fully duplicate rows (expensive, off by default)
  - SQL: `select count(*) - count(distinct *) from table` (DuckDB) or hash-based for SQLite
- [ ] SQL templates per dialect: `sql/templates/quality/{sqlite,duckdb,snowflake}.sql`
  - Single query per column: null count, distinct count, min, max — combine in one pass
  - Or one query for all columns if the dialect supports it efficiently
- [ ] Parallel execution for concurrent connectors (reuse `_concurrent.py`)
- [ ] All output formats
- [ ] Tests: clean table, table with nulls, table with duplicates, column filter, all formats

### F24: Join key discovery (`qdo joins`)

**Ease: Medium** — Name/type matching is easy; value overlap sampling is harder.

**Why**: Agent asks "how do orders relate to customers?" — needs join keys to write correct SQL.

- [ ] `src/querido/cli/joins.py` — `qdo joins --connection <name> --table orders [--target customers]`
- [ ] `src/querido/core/joins.py` — `discover_joins(connector, table, target=None) → dict`
  - Returns `{"source": str, "candidates": [{"target_table": str, "join_keys": [{"source_col": str, "target_col": str, "match_type": "exact_name"|"convention"|"name+type", "confidence": float}]}]}`
  - **Name + type matching only** (no value sampling — analyst provides more context if needed):
    - Exact column name match across tables (e.g., `customer_id` in both)
    - Convention-based: `table_id` pattern (e.g., `customers.id` ↔ `orders.customer_id`)
    - Type compatibility check (int↔int, not int↔varchar)
    - Confidence scoring: exact name + same type = high, convention match = medium, name-only = low
  - Uses cache for column metadata when available (fast scan across many tables)
- [ ] `--target` optional — if omitted, check against all tables
- [ ] All output formats
- [ ] Tests: exact name match, convention match, type mismatch rejection, multi-table scan

### F25: Schema diff (`qdo diff`)

**Ease: Medium** — Cross-connection support makes this interesting.

**Why**: "What changed between staging and prod?" or "How do these two tables differ?"

- [ ] `src/querido/cli/diff.py` — `qdo diff --connection <name> --table A --target B` (same connection) or `qdo diff --connection conn1 --table A --target-connection conn2 --target B`
- [ ] `src/querido/core/diff.py` — `schema_diff(left_columns, right_columns) → dict`
  - Returns `{"added": [...], "removed": [...], "changed": [...], "unchanged_count": int}`
  - Changed: same column name, different type/nullable/default
  - Compares `get_columns()` output from each side
- [ ] Cross-connection: resolves two separate connectors
- [ ] `--data-sample` flag — also compare N sample rows (show differences in actual data)
- [ ] All output formats
- [ ] Tests: identical tables, added/removed columns, type changes, cross-connection, all formats

### F26: Query plan / EXPLAIN (`qdo explain`)

**Ease: Easy** — Thin wrapper around each dialect's EXPLAIN syntax.

**Why**: Agent diagnosing slow queries needs to see the plan.

- [ ] `src/querido/cli/explain.py` — `qdo explain --connection <name> --sql "select ..."`
- [ ] `src/querido/core/explain.py` — `get_explain(connector, sql) → dict`
  - SQLite: `explain query plan <sql>`
  - DuckDB: `explain <sql>`
  - Snowflake: `explain using text <sql>` (or JSON with `explain using json`)
- [ ] Accept SQL via same three modes as `qdo query` (--sql, --file, stdin)
- [ ] `--analyze` flag — run `explain analyze` where supported (DuckDB, Snowflake) for actual execution stats
- [ ] All output formats (rich output uses syntax highlighting for the plan text)
- [ ] Tests: SQLite plan, DuckDB plan, analyze flag, all formats

### F27: Sample export (`qdo export`)

**Ease: Easy-Medium** — File writing with format selection.

**Why**: Agent extracts a subset to hand off to pandas, another tool, or the analyst.

- [ ] `src/querido/cli/export.py` — `qdo export --connection <name> --table <table> --output data.csv [--filter "status = 'active'"] [--limit 10000]`
- [ ] `src/querido/core/export.py` — `export_data(connector, table_or_sql, output_path, format, limit, filter) → dict`
  - Returns `{"path": str, "rows": int, "format": str, "size_bytes": int}`
- [ ] Output formats: `csv`, `json`, `parquet` (requires DuckDB/pyarrow)
  - CSV: Python csv module
  - JSON: json.dumps with newline-delimited option (`--jsonl`)
  - Parquet: via DuckDB `COPY ... TO` or pyarrow writer
- [ ] `--sql` as alternative to `--table` — export arbitrary query results
- [ ] `--filter` optional WHERE clause
- [ ] `--limit N` (default: no limit — exports full table/result)
- [ ] `--columns col1,col2` — select specific columns
- [ ] Streaming for large exports (don't load entire table into memory)
- [ ] Progress reporting on stderr (row count as it writes)
- [ ] Tests: CSV export, JSON export, filter, limit, columns, large dataset streaming

---

## Phase 10: Agent Ergonomics & Metadata Workflow

**Goal**: Make qdo seamlessly usable by coding agents, and provide a workflow for enriching raw schema with business context that agents can consume.

### F28: Agent mode via `QDO_FORMAT` environment variable

**Ease: Easy** — Small change to format resolution in `_context.py`.

**Why**: An agent (or its harness) sets `QDO_FORMAT=json` once, and every qdo command returns structured JSON without `--format json` on each call. The human default stays Rich.

- [ ] `cli/_context.py:get_output_format()` checks `QDO_FORMAT` env var when `--format` not explicitly passed
  - Priority: explicit `--format` flag > `QDO_FORMAT` env var > default (`rich`)
- [ ] Valid values: `rich`, `json`, `csv`, `markdown`, `html`, `yaml`
- [ ] Document in README, AGENTS.md, and `qdo overview` output
- [ ] Agent setup instructions: "Set `export QDO_FORMAT=json` in your agent's environment"
- [ ] Tests: env var sets default, explicit flag overrides env var, invalid env var ignored

### F29: Structured error output

**Ease: Easy** — Extend `_errors.py` to emit JSON errors when format is JSON.

**Why**: Agents need machine-parseable errors, not Rich-formatted tracebacks.

- [ ] When output format is `json`, errors emit `{"error": true, "type": "TableNotFound", "message": "...", "suggestions": [...]}`
- [ ] Exit codes remain consistent (1 = user error, 2 = SQL error)
- [ ] `friendly_errors` decorator checks output format before rendering

### F30: Metadata store — create, fill, read back (`qdo metadata`)

**Ease: Medium** — New command group with file-based storage. The key design challenge is the workflow, not the code.

**Why**: Schema alone doesn't tell an agent what a column *means*. `qdo template` generates documentation scaffolding, but there's no way to store the filled-out result and read it back. This feature closes the loop: generate → fill out → store → read → feed to agent context.

**Workflow**:
1. `qdo metadata init -c mydb -t users` — generates template, writes to metadata store
2. Analyst fills in business definitions, data owner, notes (edits the file)
3. `qdo metadata show -c mydb -t users` — reads enriched metadata back (all output formats)
4. `qdo catalog -c mydb --enrich` — merges cached schema with stored metadata for full context
5. Agent reads `qdo metadata show -c mydb -t users -f json` to get business context before writing queries

**Storage**:
- [ ] Default location: `.qdo/metadata/<connection>/<table>.yaml` in project directory
  - Project-local so metadata travels with the repo and is version-controlled
  - `.qdo/` directory (not `~/.config/qdo/`) — per-project, not global
- [ ] Alternative: `QDO_METADATA_DIR` env var or `metadata_dir` in connections.toml for override
- [ ] YAML format — human-editable, structured enough for machine reading
  - Reuses the template output shape but with filled-in fields

**Commands**:
- [ ] `qdo metadata init -c <conn> -t <table> [--force]`
  - Runs `core.template.get_template()` to generate scaffolding
  - Writes YAML with placeholder fields: `description: <business_definition>`, `owner: <data_owner>`, `notes: <notes>`
  - `--force` overwrites existing file (default: error if exists)
  - Prints path to created file
- [ ] `qdo metadata show -c <conn> -t <table> [--format json]`
  - Reads stored YAML, returns as structured data
  - If no stored metadata, falls back to live `get_template()` output with a warning
- [ ] `qdo metadata list -c <conn>`
  - Lists all tables with stored metadata for a connection
  - Shows: table name, last modified, completeness (% of fields filled vs placeholders)
- [ ] `qdo metadata edit -c <conn> -t <table>`
  - Opens the YAML file in `$EDITOR` (convenience shortcut)
- [ ] `qdo metadata refresh -c <conn> -t <table>`
  - Re-runs inspect/profile to update auto-populated fields (row counts, types, sample values) while preserving human-written fields (description, owner, notes)
  - Smart merge: overwrite machine fields, keep human fields

**YAML schema**:
```yaml
# .qdo/metadata/mydb/users.yaml
table: users
connection: mydb
row_count: 50000
table_description: "Core user accounts table — one row per registered user"
data_owner: "Identity team (identity@company.com)"
update_frequency: "Real-time via CDC"
notes: |
  PII columns: email, first_name, last_name
  Soft-deleted rows have status='inactive'
columns:
  - name: id
    type: INTEGER
    nullable: false
    primary_key: true
    description: "Auto-increment user ID, used as FK in orders/events"
    distinct_count: 50000
    null_count: 0
    sample_values: "1, 2, 3"
  - name: email
    type: TEXT
    nullable: false
    description: "User email — unique, used for login"
    pii: true
    distinct_count: 50000
    null_count: 0
    sample_values: "alice@example.com, bob@example.com"
  - name: status
    type: TEXT
    nullable: false
    description: "Account status"
    valid_values: ["active", "inactive", "suspended"]
    distinct_count: 3
    null_count: 0
```

**Integration with catalog (F18)**:
- [ ] `qdo catalog -c mydb --enrich` flag merges stored metadata descriptions into catalog output
  - Each column in the catalog gains `"description"` and `"notes"` from stored metadata
  - Tables gain `"table_description"`, `"data_owner"`, `"update_frequency"`
  - Agent gets full context in one call: schema + types + business definitions

**Integration with overview**:
- [ ] Add `metadata` command to `qdo overview` (both markdown and JSON output)
- [ ] JSON output shape documented for agent consumption

**Tests**:
- [ ] Init creates YAML with correct structure
- [ ] Show reads back stored metadata
- [ ] List reports completeness
- [ ] Refresh preserves human fields while updating machine fields
- [ ] Enrich flag on catalog merges correctly
- [ ] Missing metadata falls back gracefully

### F31: Update `qdo overview` for all new commands

**Ease: Easy** — Mechanical update to `cli/overview.py`.

**Why**: The overview is the agent's entry point to discovering qdo capabilities. Every new command must be documented there with its options and output shape.

- [ ] Add to `_print_fallback()` markdown table: query, catalog, values, pivot, freshness, assert, quality, joins, diff, explain, export, metadata
- [ ] Add to `_print_json()` commands list: full option specs and output shapes for each new command
- [ ] Add `metadata_workflow` section to JSON output explaining the init → fill → show workflow
- [ ] Add `agent_setup` section to JSON output: `QDO_FORMAT=json`, recommended command sequence
- [ ] Update `docs/cli-reference.md` if it exists

---

## Architectural Notes for Future Features

The `core/` refactor (Phase 7) addresses the separation between **business logic** and **presentation** that was identified early in the project. Once Phase 7 is complete, all presentation layers share the same data-fetching logic:

- `cli/*.py` calls core functions → passes results to `output/console.py` (Rich)
- `tui/*.py` calls core functions → passes results to Textual widgets
- `web/*.py` (future F11) calls core functions → passes results to HTML templates or JSON API

### Optional dependency groups

```toml
[project.optional-dependencies]
duckdb = ["duckdb>=1"]
snowflake = ["snowflake-connector-python>=3.6", "pyarrow>=14"]
tui = ["textual>=0.50"]
web = ["fastapi>=0.115", "uvicorn[standard]>=0.34", "python-multipart>=0.0.18"]
embeddings = ["numpy", "openai"]  # or sentence-transformers for local — future
ai = ["llama-cpp-python"]  # or separate package entirely — future
```
