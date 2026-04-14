# qdo - Architecture

## Overview

qdo is a CLI data analysis toolkit for running common analytics tasks against database sources (SQLite, DuckDB, Snowflake) and Parquet files. It uses SQL templates to query databases and renders results as rich terminal output.

## Project Structure

```
querido/
├── pyproject.toml                  # All dependencies, build config, ruff/ty config
├── LICENSE                         # MIT license
├── AGENTS.md                       # Agent onboarding guide
├── ARCHITECTURE.md                 # This file
├── IDEAS.md                        # Unimplemented feature ideas
├── README.md
├── docs/
│   ├── cli-reference.md            # Auto-generated CLI reference
│   └── qdo-cheatsheet.html         # Visual cheatsheet
├── integrations/
│   ├── agent-workflow-example.md    # Example agent workflow with metadata
│   ├── skills/SKILL.md             # Claude Code skill file
│   ├── skills/WORKFLOW_AUTHORING.md # Agent-authoring guide for qdo workflows
│   ├── skills/WORKFLOW_EXAMPLES.md  # Annotated reference to bundled workflow examples
│   └── continue/qdo.md             # Continue.dev rule
├── scripts/
│   ├── init_test_data.py           # Generate synthetic data → data/test.db + data/test.duckdb
│   ├── init_tutorial_data.py       # Generate tutorial National Parks DB
│   ├── check_deps.py              # Dependency checker with supply-chain quarantine
│   ├── benchmark.py               # Performance benchmarks (generates large DuckDB, times operations)
│   ├── eval_workflow_authoring.py # Self-hosting eval: claude -p round-trips WORKFLOW_AUTHORING.md (Phase 4.6)
│   └── retag.sh                   # Move release tag to current commit
├── src/
│   └── querido/
│       ├── __init__.py             # Version string (__version__)
│       ├── py.typed                # PEP 561 marker for typed package
│       ├── cache.py                # Local metadata cache (SQLite-backed)
│       ├── config.py               # TOML config loading, connection resolution, column sets
│       ├── cli/
│       │   ├── __init__.py         # Package marker
│       │   ├── _context.py         # Output format, SQL display, HTML emission
│       │   ├── _errors.py          # friendly_errors decorator, error classification
│       │   ├── _pipeline.py        # table_command/database_command context managers, dispatch_output
│       │   ├── _progress.py        # Elapsed-time query spinner with cancellation
│       │   ├── _options.py         # Shared Typer option definitions (--connection, --db-type, etc.)
│       │   ├── _validation.py      # Table/column existence checks, fuzzy suggestions, destructive SQL guard
│       │   ├── main.py             # Entry point, Typer app, lazy subcommand loading
│       │   ├── assert_cmd.py       # `qdo assert` — assert conditions on query results (CI-friendly)
│       │   ├── bundle.py           # `qdo bundle export/import/inspect/diff` — portable knowledge bundles
│       │   ├── cache.py            # `qdo cache sync/status/clear` — metadata cache management
│       │   ├── catalog.py          # `qdo catalog` — full database catalog (tables, columns, row counts)
│       │   ├── completion.py       # `qdo completion show` — shell completion scripts
│       │   ├── config.py           # `qdo config add/list/clone/test/column-set` — connection management
│       │   ├── context.py          # `qdo context` — schema + stats + sample values in one call
│       │   ├── diff.py             # `qdo diff` — compare schemas between two tables
│       │   ├── dist.py             # `qdo dist` — column distribution visualization
│       │   ├── explain.py          # `qdo explain` — query execution plan (EXPLAIN)
│       │   ├── explore.py          # `qdo explore` — interactive TUI launcher
│       │   ├── export.py           # `qdo export` — export data to file (csv, tsv, json, jsonl)
│       │   ├── inspect.py          # `qdo inspect` — table metadata
│       │   ├── joins.py            # `qdo joins` — discover likely join keys
│       │   ├── metadata.py         # `qdo metadata init/edit/show/list/refresh` — enriched metadata
│       │   ├── overview.py         # `qdo overview` — CLI reference markdown generation
│       │   ├── pivot.py            # `qdo pivot` — pivot / aggregate table data
│       │   ├── preview.py          # `qdo preview` — row preview
│       │   ├── profile.py          # `qdo profile` — data profiling (quick, classify, column sets)
│       │   ├── quality.py          # `qdo quality` — data quality summary (nulls, uniqueness, anomalies)
│       │   ├── query.py            # `qdo query` — execute ad-hoc SQL
│       │   ├── report.py           # `qdo report table` — single-file HTML report
│       │   ├── serve.py            # `qdo serve` — FastAPI web UI launcher
│       │   ├── session.py          # `qdo session start/list/show` — agent-workflow session logs
│       │   ├── snowflake.py        # `qdo snowflake` — Snowflake-specific commands (semantic, lineage)
│       │   ├── sql.py              # `qdo sql` — SQL generation (select, insert, ddl, scratch, task, udf, procedure)
│       │   ├── template.py         # `qdo template` — documentation template generation
│       │   ├── tutorial.py         # `qdo tutorial` — interactive tutorial launcher
│       │   ├── values.py           # `qdo values` — distinct values for a column
│       │   ├── view_def.py         # `qdo view-def` — view SQL definition retrieval
│       │   └── workflow.py         # `qdo workflow spec/run/lint/list/show/from-session` — declarative workflows
│       ├── connectors/
│       │   ├── __init__.py         # Package marker
│       │   ├── base.py             # Connector Protocol, table name validation, error hierarchy
│       │   ├── arrow_util.py       # Arrow-aware execution helpers (execute_arrow_or_dicts)
│       │   ├── factory.py          # Creates connector from config/args
│       │   ├── sqlite.py           # SQLite connector (stdlib, always available)
│       │   ├── duckdb.py           # DuckDB connector (optional install, also handles Parquet)
│       │   └── snowflake.py        # Snowflake connector (optional install)
│       ├── core/
│       │   ├── __init__.py         # Package marker
│       │   ├── _concurrent.py      # Parallel query execution helper (thread pool)
│       │   ├── _utils.py           # Shared helpers: type detection, classification, sampling
│       │   ├── assert_check.py     # Assert condition checking logic
│       │   ├── bundle.py           # Knowledge bundle export/import/diff logic + schema fingerprint
│       │   ├── catalog.py          # Full database catalog logic (live, cached, enriched, filtered)
│       │   ├── context.py          # Context logic (schema + stats + sample values, single scan)
│       │   ├── diff.py             # Schema diff logic
│       │   ├── dist.py             # Distribution computation logic
│       │   ├── explain.py          # Query plan logic
│       │   ├── export.py           # Data export logic
│       │   ├── inspect.py          # Inspect metadata logic
│       │   ├── joins.py            # Join key discovery logic
│       │   ├── lineage.py          # View definition retrieval logic (used by view-def command)
│       │   ├── metadata.py         # Enriched metadata (init, show, list, refresh)
│       │   ├── pivot.py            # Pivot query builder and executor
│       │   ├── preview.py          # Row preview logic
│       │   ├── profile.py          # Data profiling (stats, frequencies, quick mode, batching)
│       │   ├── quality.py          # Data quality analysis logic
│       │   ├── query.py            # Ad-hoc SQL execution with limit wrapping
│       │   ├── report.py           # Table report data builder (fans out to context/quality/joins/metadata)
│       │   ├── runner.py           # Threaded query execution with cancellation support
│       │   ├── semantic.py         # Snowflake Cortex Analyst semantic model YAML builder
│       │   ├── session.py          # Session recorder (QDO_SESSION) — JSONL step log
│       │   ├── next_steps.py       # Deterministic next_steps/try_next suggestions
│       │   ├── template.py         # Documentation template generation logic
│       │   ├── values.py           # Distinct values logic
│       │   └── workflow/
│       │       ├── __init__.py       # load_examples helper + re-exports
│       │       ├── spec.py           # Authoritative workflow JSON Schema
│       │       ├── expr.py           # Tiny restricted ${ref} / when evaluator
│       │       ├── loader.py         # Workflow file discovery (project/user/bundled)
│       │       ├── lint.py           # Structural + semantic lint
│       │       ├── runner.py         # Subprocess-based workflow runner
│       │       ├── from_session.py   # Draft workflow synthesis from a session log
│       │       └── examples/         # Bundled example workflow YAMLs
│       ├── sql/
│       │   ├── __init__.py         # Package marker
│       │   ├── renderer.py         # Jinja2 template loading and rendering
│       │   └── templates/          # .sql files organized by command and dialect
│       │       ├── context/
│       │       │   ├── duckdb.sql      # stats + approx_top_k (one scan)
│       │       │   └── snowflake.sql   # stats + APPROX_TOP_K (one scan)
│       │       ├── count/
│       │       │   └── common.sql
│       │       ├── dist/
│       │       │   ├── sqlite.sql      # CASE-based binning
│       │       │   ├── duckdb.sql      # FLOOR-based binning
│       │       │   └── snowflake.sql   # WIDTH_BUCKET binning
│       │       ├── frequency/
│       │       │   ├── common.sql      # Top-N frequent values query
│       │       │   └── snowflake.sql   # approx_top_k variant
│       │       ├── null_count/
│       │       │   ├── common.sql      # NULL count + total rows for a column
│       │       │   ├── duckdb.sql      # count_if variant
│       │       │   └── snowflake.sql   # count_if variant
│       │       ├── generate/           # SQL generation templates (qdo sql)
│       │       │   ├── select/common.sql
│       │       │   ├── insert/common.sql
│       │       │   ├── ddl/common.sql
│       │       │   ├── scratch/common.sql
│       │       │   ├── scratch/snowflake.sql
│       │       │   ├── task/snowflake.sql
│       │       │   ├── udf/{sqlite,duckdb,snowflake}.sql
│       │       │   └── procedure/snowflake.sql
│       │       ├── preview/
│       │       │   └── common.sql
│       │       ├── profile/
│       │       │   ├── sqlite.sql
│       │       │   ├── duckdb.sql
│       │       │   └── snowflake.sql
│       │       └── test/
│       │           └── common.sql  # Used by renderer unit tests
│       ├── tui/
│       │   ├── __init__.py         # Package marker
│       │   ├── app.py              # ExploreApp — main Textual TUI application
│       │   ├── screens/
│       │   │   ├── __init__.py
│       │   │   ├── column_picker.py    # ColumnPickerScreen — single-select column modal
│       │   │   ├── column_selector.py  # ColumnSelectorScreen — multi-select with classification
│       │   │   ├── dist.py             # DistScreen — column distribution modal
│       │   │   ├── help.py             # HelpScreen — key binding reference overlay
│       │   │   ├── inspect.py          # InspectScreen — column metadata modal
│       │   │   └── profile.py          # ProfileScreen — tiered profiling (quick → select → full)
│       │   └── widgets/
│       │       ├── __init__.py
│       │       ├── filter_bar.py   # FilterBar — SQL WHERE expression input
│       │       ├── sidebar.py      # MetadataSidebar — column stats panel
│       │       └── status_bar.py   # StatusBar — table info, row count, filter/sort status
│       ├── tutorial/
│       │   ├── __init__.py         # Package marker
│       │   ├── _helpers.py         # Shared tutorial step helpers
│       │   ├── data.py             # National Parks sample data
│       │   ├── metadata_fixtures.py # Metadata examples for agent tutorial
│       │   ├── runner.py           # Core exploration tutorial (15 lessons)
│       │   └── runner_agent.py     # Metadata + agent workflow tutorial (13 lessons)
│       ├── output/
│       │   ├── __init__.py         # Package marker, shared helpers (fmt_value)
│       │   ├── console.py          # Rich terminal output (tables, panels, frequencies)
│       │   ├── envelope.py         # Agent-facing envelope (command/data/next_steps/meta); dispatches json vs agent rendering
│       │   ├── formats.py          # Machine-readable output (markdown, JSON, CSV, YAML)
│       │   ├── toon.py             # TOON v3.0 encoder (in-tree); primitives, objects, tabular + primitive arrays
│       │   ├── html.py             # Standalone HTML pages with interactive tables
│       │   └── report_html.py      # Single-file report renderer (cheatsheet aesthetic, inline SVG)
│       └── web/
│           ├── __init__.py         # FastAPI app factory (create_app)
│           ├── routes/
│           │   ├── __init__.py
│           │   ├── pages.py        # Full-page routes (landing, table detail)
│           │   ├── fragments.py    # HTMX partial endpoints (inspect, preview, profile, etc.)
│           │   └── pivot.py        # Pivot builder endpoints
│           ├── static/
│           │   ├── style.css       # Shared CSS (light/dark mode, nav, tabs, cards)
│           │   └── app.js          # Shared JS (sort, filter, copy, export, keyboard shortcuts)
│           └── templates/
│               ├── base.html       # Layout shell: nav, sidebar, HTMX/Alpine script tags
│               ├── landing.html    # Connection info + table card grid
│               ├── table.html      # Table detail page with tab navigation
│               ├── pivot.html      # Pivot builder form
│               └── partials/       # HTMX fragments (inspect, preview, profile, dist, etc.)
└── tests/
    ├── conftest.py                 # Shared fixtures (temp databases, test tables)
    ├── test_agent_mode.py          # Agent mode (QDO_FORMAT=json) tests
    ├── test_assert.py              # Assert command tests
    ├── test_bundle.py              # Knowledge bundle tests (export/import/inspect/diff)
    ├── test_workflow_spec.py       # Workflow JSON Schema + bundled examples tests
    ├── test_workflow_runner.py     # Workflow runner, lint, list, show tests
    ├── test_cache.py               # Metadata cache tests (sync, status, clear)
    ├── test_cancellation.py        # Query cancellation tests
    ├── test_catalog.py             # Catalog command tests (listing, filtering, caching)
    ├── test_cli.py                 # CLI help/version/show-sql tests
    ├── test_completion.py          # Shell completion tests
    ├── test_config.py              # Config loading and connection resolution tests
    ├── test_config_cmd.py          # Config add/list/clone command tests
    ├── test_connectors.py          # SQLite + DuckDB connector unit tests
    ├── test_context.py             # Context command tests
    ├── test_core.py                # Core utility tests
    ├── test_diff.py                # Schema diff tests
    ├── test_dist.py                # Distribution command tests (numeric + categorical)
    ├── test_errors.py              # Error handling and classification tests
    ├── test_explain.py             # Explain (query plan) tests
    ├── test_explore.py             # Explore CLI entry point tests
    ├── test_export.py              # Export command tests
    ├── test_format.py              # Output format tests (markdown, JSON, CSV)
    ├── test_html_format.py         # HTML output tests
    ├── test_inspect.py             # Inspect command tests (SQLite + DuckDB)
    ├── test_joins.py               # Join discovery tests
    ├── test_lineage.py             # View definition tests (view-def command)
    ├── test_metadata.py            # Enriched metadata tests (init/show/list/refresh)
    ├── test_overview.py            # Overview command tests
    ├── test_parquet.py             # Parquet file support tests
    ├── test_pivot_cmd.py           # Pivot command tests
    ├── test_preview.py             # Preview command tests (SQLite + DuckDB)
    ├── test_profile.py             # Profile command tests (top-N, frequencies, quick, classify)
    ├── test_quality.py             # Data quality tests
    ├── test_query.py               # Query command tests
    ├── test_renderer.py            # SQL template rendering tests
    ├── test_serve_cli.py           # Serve command CLI tests
    ├── test_snowflake.py           # Snowflake connector tests (mocked)
    ├── test_snowflake_commands.py  # Snowflake-specific command tests
    ├── test_sql.py                 # SQL generation command tests
    ├── test_template.py            # Template command tests (all formats, SQLite + DuckDB)
    ├── test_tui.py                 # TUI widget and app tests (Textual pilot framework)
    ├── test_tutorial.py            # Tutorial tests
    ├── test_values.py              # Values command tests
    ├── test_web.py                 # Web UI tests (FastAPI TestClient, all endpoints)
    └── integration/
        ├── conftest.py             # Integration test fixtures
        ├── test_connectors.py      # Connector tests against real data
        ├── test_inspect.py         # Inspect tests against real data
        ├── test_preview.py         # Preview tests against real data
        └── test_profile.py         # Profile tests against real data
```

## Key Design Principles

### 1. Pay for What You Use

qdo follows a strict "pay for what you use" model at every level:

**Install time** — Only SQLite (stdlib) is included by default. Database backends are opt-in:

```bash
uv pip install querido              # SQLite only (no extra dependencies)
uv pip install 'querido[duckdb]'    # + DuckDB + Parquet support
uv pip install 'querido[snowflake]' # + Snowflake
```

If a user tries a backend they haven't installed, the factory gives a clear error with install instructions.

**Runtime** — All heavy dependencies are imported inside functions, not at module level. A command that isn't invoked costs nothing:

```python
# GOOD - imported when the command runs
def inspect_command(table: str):
    from rich.table import Table
    from querido.connectors.factory import create_connector
    ...

# BAD - imported at startup even if this command isn't used
from rich.table import Table
```

This applies to: database drivers (sqlite3, duckdb, snowflake-connector-python), Rich, Jinja2. The only top-level imports allowed are `typer`, stdlib modules, and type-checking-only imports behind `if TYPE_CHECKING`.

### 2. Connector Protocol

All database backends implement the same Protocol and support context manager usage:

```python
class Connector(Protocol):
    dialect: str  # "sqlite", "duckdb", "snowflake"

    def execute(self, sql: str, params: dict | tuple | None = None) -> list[dict]: ...
    def get_tables(self) -> list[dict]: ...
    def get_columns(self, table: str) -> list[dict]: ...
    def get_table_comment(self, table: str) -> str | None: ...
    def get_view_definition(self, view: str) -> str | None: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, *args: object) -> None: ...
```

Usage:
```python
with create_connector(config) as conn:
    rows = conn.execute("SELECT * FROM users")
```

A factory function creates the right connector based on the connection config's `type` field.

**Parquet support**: The DuckDB connector has a `register_parquet()` method that creates an in-memory view from a Parquet file. The factory calls this automatically when `parquet_path` is present in the config.

**Arrow fast path**: The Snowflake and DuckDB connectors provide an `execute_arrow()` method that returns a PyArrow Table instead of `list[dict]`. This avoids materializing Python dicts for every row. The helper `connectors/arrow_util.py:execute_arrow_or_dicts()` tries the Arrow path and falls back to `execute()` for connectors that don't support it (SQLite). Column names from Snowflake are normalized to lowercase via zero-copy `rename_columns()` on the Arrow table.

**Concurrent queries**: Connectors expose a `supports_concurrent_queries` class attribute (`True` for Snowflake, `False` for DuckDB/SQLite). When enabled, `core/profile.py:get_frequencies()` runs per-column frequency queries in parallel using a thread pool, reducing wall-clock time for Snowflake profiling.

### 3. SQL Templates

SQL queries live in `.sql` files using Jinja2 syntax. Templates are organized by command and dialect:

```
sql/templates/profile/sqlite.sql    # SQLite-specific profiling query
sql/templates/profile/duckdb.sql    # DuckDB-specific profiling query
sql/templates/preview/common.sql    # Shared across dialects (simple SELECT)
sql/templates/frequency/common.sql  # Top-N frequent values (shared)
```

The renderer loads templates by command name and dialect, falling back to `common.sql` if no dialect-specific template exists.

Template variables use Jinja2 syntax for structural elements (table names, optional clauses) and the database driver's parameterized query mechanism for values (preventing SQL injection):

```sql
-- Structural (Jinja2 renders this)
SELECT * FROM {{ table }}
{% if columns %}WHERE {{ columns | join(', ') }}{% endif %}
LIMIT {{ limit }}

-- Values are passed as bind parameters to the driver, NOT rendered by Jinja2
```

Note: Column metadata queries (`get_columns`) are implemented directly in each connector rather than as SQL templates, since each database uses different mechanisms (e.g. SQLite uses `PRAGMA table_info`, DuckDB uses `duckdb_columns()`, Snowflake uses `information_schema`). Each connector also provides `get_table_comment()` — DuckDB queries `duckdb_tables()`, Snowflake queries `information_schema.tables`, and SQLite returns None (no native comment support). Column-level comments are included in the `get_columns()` dict as the `"comment"` key.

### 4. Input Validation

Table and column names are validated at the CLI boundary using `validate_table_name()` and `validate_column_name()` from `connectors/base.py`. Since these names are interpolated into SQL templates (Jinja2) and sampling subqueries (f-strings), they must be safe identifiers — letters, digits, underscores, and dots only.

### 5. Identifier Case Normalization

Each connector normalizes identifier case in **Python** (e.g. `.lower()` for DuckDB, `.upper()` for Snowflake) before passing values as bind parameters to catalog queries. This is intentional — pushing normalization into SQL with functions like `LOWER()` forces the database to evaluate a function call per row in the catalog, which is wasteful. Doing it once in Python before the query is cheaper and keeps the SQL simple with exact-match `WHERE` clauses.

### 6. Configuration

Connections are stored in TOML at the platform-appropriate config directory (via `platformdirs`):

- Linux: `~/.config/qdo/connections.toml`
- macOS: `~/Library/Application Support/qdo/connections.toml`
- Windows: `%LOCALAPPDATA%\qdo\connections.toml`

Override with `QDO_CONFIG` environment variable.

```toml
[connections.my-local-db]
type = "duckdb"
path = "./analytics.duckdb"

[connections.prod]
type = "snowflake"
account = "xy12345.us-east-1"
warehouse = "ANALYTICS_WH"
database = "PROD"
schema = "PUBLIC"
auth = "externalbrowser"
```

Connections can be managed via CLI (`qdo config add` / `qdo config list`) or by editing the file directly.

Column sets are stored alongside connections in `column_sets.toml`:

```toml
["mydb.orders.default"]
columns = ["id", "status", "amount", "created_at"]

["mydb.orders.audit"]
columns = ["id", "status", "amount", "created_at", "updated_by"]
```

Keys are `connection.table.set_name`. Managed via `qdo config column-set {save,list,show,delete}` and consumed by `qdo profile --column-set`.

CLI resolves `--connection` by:
1. Looking up as a named connection in the config file
2. If not found, treating it as a file path (for SQLite/DuckDB/Parquet)
3. `.duckdb`/`.ddb` → DuckDB, `.parquet` → Parquet (via DuckDB), else → SQLite

### 6. Output

Rich is used for all terminal output. Output functions live in `output/console.py` and accept data in a generic format (list of dicts) so they're decoupled from the database layer. Rich is imported lazily inside each output function.

Output functions: `print_inspect`, `print_preview`, `print_profile`, `print_dist`, `print_lineage` (view-def), `print_frequencies`, `print_template`. HTML output (`output/html.py`) generates standalone HTML pages with embedded CSS/JS for sorting, filtering, copy, and CSV export. The web UI (`web/`) serves the same data via FastAPI + Jinja2 templates + HTMX for interactive browsing.

Progress spinners (Rich `Status`) display on stderr during query execution so they don't interfere with output piping.

### 7. Sessions

When `QDO_SESSION=<name>` is set in the environment, every `qdo` invocation
appends a record to `.qdo/sessions/<name>/steps.jsonl` and saves that step's
stdout to `.qdo/sessions/<name>/step_<n>/stdout`. The step record contains
`timestamp`, `cmd`, `args`, `duration`, `exit_code`, `row_count`, and
`stdout_path`. No daemon, no DB — just append-only files scoped to the cwd.

The recorder is installed in `cli/main.py:_maybe_start_session()` which tees
stdout into a buffer and registers a `ctx.call_on_close()` finalizer so the
step is recorded whether the command succeeds or fails. `LazyGroup.resolve_command()`
stashes the raw subcommand argv on `ctx.obj` so the finalizer can persist the
exact invocation. `qdo session start/list/show` manage session directories.

### 8. Global Flags

- `--version` / `-V`: Show version and exit
- `--show-sql`: Print rendered SQL to stderr with syntax highlighting before executing. Uses Rich `Syntax` with SQL lexer. Stored in Click context, accessed by `cli/_context.py:maybe_show_sql()`.
- `--format {rich,markdown,json,csv,html,yaml,agent}` / `-f`: Output format. Default is `rich` (Rich terminal tables). `html` opens results in the default browser. `yaml` is used for Snowflake semantic model output. `agent` renders the same envelope as `json` but in TOON (tabular) + YAML (nested) — tuned for LLM consumption, typically 30–70% fewer tokens than `json`. Other formats write plain text to stdout for piping. Stored in Click context, accessed by `cli/_context.py:get_output_format()`. Commands that build an envelope gate on `envelope.is_structured_format()` to cover both `json` and `agent`.
- `--debug`: Enable debug logging to stderr. Logs connection details, query timing, table resolution, and cache status. Uses Python `logging` module with `querido` logger hierarchy.

Command-specific flags:
- `inspect --verbose` / `-v`: Show extended metadata (table and column comments/descriptions).

## Data Flow

```
CLI (Typer)
  → validate table name (base.py)
  → resolve connection (config.py)
  → create connector (factory.py)
  → [show spinner on stderr]
  → load + render SQL template (renderer.py)
  → [maybe_show_sql to stderr if --show-sql]
  → execute query (connector)
  → format + display results (output/console.py)
```

## Dependencies

| Package | Purpose | Install | Import Strategy |
|---------|---------|---------|----------------|
| typer | CLI framework | Default | Top-level (unavoidable) |
| platformdirs | Cross-platform config paths | Default | In config.py only |
| jinja2 | SQL template rendering | Default | In renderer.py only |
| rich | Terminal output | Default | In output functions only |
| tomli-w | TOML writing (config) | Default | In cli/config.py only |
| duckdb | DuckDB + Parquet connector | `uv pip install 'querido[duckdb]'` | In connectors/duckdb.py only |
| pyarrow | Arrow columnar format | `uv pip install 'querido[snowflake]'` | In connectors/snowflake.py, arrow_util.py |
| snowflake-connector-python | Snowflake connector | `uv pip install 'querido[snowflake]'` | In connectors/snowflake.py only |
| textual | Interactive TUI | `uv pip install 'querido[tui]'` | In tui/ only |
| fastapi | Web UI backend | `uv pip install 'querido[web]'` | In web/ only |
| uvicorn | ASGI server | `uv pip install 'querido[web]'` | In cli/serve.py only |

Note: `sqlite3` is stdlib — no extra dependency needed, always available.

## Testing Strategy

- pytest for all tests
- Unit tests create temporary in-memory databases with test data
- Tests run actual CLI commands via `typer.testing.CliRunner` or call connector methods directly
- SQLite and DuckDB tests run in every phase; Snowflake tests are separate (require credentials)
- DuckDB is included in dev dependencies so all tests run regardless of install extras
- Goal: enough tests to prove things work, not 100% coverage
