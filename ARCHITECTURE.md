# qdo - Architecture

## Overview

qdo is a CLI data analysis toolkit for running common analytics tasks against database sources (SQLite, DuckDB, Snowflake) and Parquet files. It uses SQL templates to query databases and renders results as rich terminal output.

## Project Structure

```
querido/
├── pyproject.toml                  # All dependencies, build config, ruff/ty config
├── LICENSE                         # MIT license
├── PLAN.md                         # Incremental build plan with phases
├── AGENTS.md                       # Agent onboarding guide
├── ARCHITECTURE.md                 # This file
├── README.md
├── scripts/
│   ├── init_test_data.py           # Generate synthetic data → data/test.db + data/test.duckdb
│   └── tutorial.py                 # Interactive step-by-step tutorial
├── src/
│   └── querido/
│       ├── __init__.py             # Version string (__version__)
│       ├── py.typed                # PEP 561 marker for typed package
│       ├── cache.py                # Local metadata cache (SQLite-backed)
│       ├── config.py               # TOML config loading, connection resolution
│       ├── cli/
│       │   ├── __init__.py         # Package marker
│       │   ├── _util.py            # CLI utilities (maybe_show_sql, is_numeric_type)
│       │   ├── main.py             # Entry point, Typer app, registers subcommands
│       │   ├── cache.py            # `qdo cache sync/status/clear` — metadata cache management
│       │   ├── config.py           # `qdo config add/list` — connection management
│       │   ├── dist.py             # `qdo dist` — column distribution visualization
│       │   ├── inspect.py          # `qdo inspect` — table metadata
│       │   ├── lineage.py          # `qdo lineage` — view SQL definition retrieval
│       │   ├── preview.py          # `qdo preview` — row preview
│       │   ├── profile.py          # `qdo profile` — data profiling
│       │   ├── search.py           # `qdo search` — metadata search across tables/columns (cache-aware)
│       │   ├── explore.py          # `qdo explore` — interactive TUI launcher
│       │   ├── snowflake.py         # `qdo snowflake` — Snowflake-specific commands (semantic, lineage)
│       │   ├── sql.py              # `qdo sql` — SQL statement generation (select, insert, ddl, task, udf, procedure)
│       │   └── template.py         # `qdo template` — documentation template generation
│       ├── connectors/
│       │   ├── __init__.py         # Package marker
│       │   ├── base.py             # Connector Protocol, table name validation
│       │   ├── factory.py          # Creates connector from config/args
│       │   ├── sqlite.py           # SQLite connector (stdlib, always available)
│       │   ├── duckdb.py           # DuckDB connector (optional install, also handles Parquet)
│       │   └── snowflake.py        # Snowflake connector (optional install)
│       ├── sql/
│       │   ├── __init__.py         # Package marker
│       │   ├── renderer.py         # Jinja2 template loading and rendering
│       │   └── templates/          # .sql files organized by command and dialect
│       │       ├── count/
│       │       │   └── common.sql
│       │       ├── dist/
│       │       │   ├── sqlite.sql      # CASE-based binning
│       │       │   ├── duckdb.sql      # FLOOR-based binning
│       │       │   └── snowflake.sql   # WIDTH_BUCKET binning
│       │       ├── frequency/
│       │       │   └── common.sql  # Top-N frequent values query
│       │       ├── null_count/
│       │       │   └── common.sql  # NULL count + total rows for a column
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
│       │   │   ├── help.py         # HelpScreen — key binding reference overlay
│       │   │   └── inspect.py      # InspectScreen — column metadata modal
│       │   └── widgets/
│       │       ├── __init__.py
│       │       ├── filter_bar.py   # FilterBar — SQL WHERE expression input
│       │       ├── sidebar.py      # MetadataSidebar — column stats panel
│       │       └── status_bar.py   # StatusBar — table info, row count, filter/sort status
│       ├── output/
│       │   ├── __init__.py         # Package marker, shared helpers (fmt_value)
│       │   ├── console.py          # Rich terminal output (tables, panels, frequencies)
│       │   ├── formats.py          # Machine-readable output (markdown, JSON, CSV)
│       │   └── html.py             # Standalone HTML pages with interactive tables
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
    ├── test_cli.py                 # CLI help/version/show-sql tests
    ├── test_config.py              # Config loading and connection resolution tests
    ├── test_config_cmd.py          # Config add/list command tests
    ├── test_connectors.py          # SQLite + DuckDB connector unit tests
    ├── test_cache.py               # Metadata cache tests (sync, status, clear, search integration)
    ├── test_dist.py                # Distribution command tests (numeric + categorical)
    ├── test_explore.py             # Explore CLI entry point tests
    ├── test_tui.py                 # TUI widget and app tests (Textual pilot framework)
    ├── test_format.py              # Output format tests (markdown, JSON, CSV)
    ├── test_inspect.py             # Inspect command tests (SQLite + DuckDB)
    ├── test_lineage.py             # Lineage/view definition tests (SQLite + DuckDB)
    ├── test_parquet.py             # Parquet file support tests
    ├── test_preview.py             # Preview command tests (SQLite + DuckDB)
    ├── test_profile.py             # Profile command tests (top-N, frequencies)
    ├── test_renderer.py            # SQL template rendering tests
    ├── test_search.py              # Search command tests (SQLite + DuckDB)
    ├── test_snowflake.py           # Snowflake connector tests (mocked)
    ├── test_sql.py                 # SQL generation command tests
    ├── test_template.py            # Template command tests (all formats, SQLite + DuckDB)
    ├── test_web.py                 # Web UI tests (FastAPI TestClient, all endpoints)
    └── integration/
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
pip install querido              # SQLite only (no extra dependencies)
pip install 'querido[duckdb]'    # + DuckDB + Parquet support
pip install 'querido[snowflake]' # + Snowflake
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

### 5. Configuration

Connections are stored in TOML at the platform-appropriate config directory (via `platformdirs`):

- Linux: `~/.config/qdo/connections.toml`
- macOS: `~/Library/Application Support/qdo/connections.toml`
- Windows: `%APPDATA%\qdo\connections.toml`

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

CLI resolves `--connection` by:
1. Looking up as a named connection in the config file
2. If not found, treating it as a file path (for SQLite/DuckDB/Parquet)
3. `.duckdb`/`.ddb` → DuckDB, `.parquet` → Parquet (via DuckDB), else → SQLite

### 6. Output

Rich is used for all terminal output. Output functions live in `output/console.py` and accept data in a generic format (list of dicts) so they're decoupled from the database layer. Rich is imported lazily inside each output function.

Output functions: `print_inspect`, `print_preview`, `print_profile`, `print_search`, `print_dist`, `print_lineage`, `print_frequencies`, `print_template`. HTML output (`output/html.py`) generates standalone HTML pages with embedded CSS/JS for sorting, filtering, copy, and CSV export. The web UI (`web/`) serves the same data via FastAPI + Jinja2 templates + HTMX for interactive browsing.

Progress spinners (Rich `Status`) display on stderr during query execution so they don't interfere with output piping.

### 7. Global Flags

- `--version` / `-V`: Show version and exit
- `--show-sql`: Print rendered SQL to stderr with syntax highlighting before executing. Uses Rich `Syntax` with SQL lexer. Stored in Click context, accessed by `cli/_util.py:maybe_show_sql()`.
- `--format {rich,markdown,json,csv,html,yaml}` / `-f`: Output format. Default is `rich` (Rich terminal tables). `html` opens results in the default browser. `yaml` is used for Snowflake semantic model output. Other formats write plain text to stdout for piping. Stored in Click context, accessed by `cli/_util.py:get_output_format()`.

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
| duckdb | DuckDB + Parquet connector | `pip install 'querido[duckdb]'` | In connectors/duckdb.py only |
| snowflake-connector-python | Snowflake connector | `pip install 'querido[snowflake]'` | In connectors/snowflake.py only |
| textual | Interactive TUI | `pip install 'querido[tui]'` | In tui/ only |
| fastapi | Web UI backend | `pip install 'querido[web]'` | In web/ only |
| uvicorn | ASGI server | `pip install 'querido[web]'` | In cli/serve.py only |

Note: `sqlite3` is stdlib — no extra dependency needed, always available.

## Testing Strategy

- pytest for all tests
- Unit tests create temporary in-memory databases with test data
- Tests run actual CLI commands via `typer.testing.CliRunner` or call connector methods directly
- SQLite and DuckDB tests run in every phase; Snowflake tests are separate (require credentials)
- DuckDB is included in dev dependencies so all tests run regardless of install extras
- Goal: enough tests to prove things work, not 100% coverage
