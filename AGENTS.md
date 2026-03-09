# Agent Guide for qdo

This file helps coding agents get up to speed quickly on the qdo project.

## What is qdo?

A CLI data analysis toolkit. Users run commands like `qdo inspect`, `qdo preview`, `qdo profile` against database tables (SQLite, DuckDB, Snowflake) and Parquet files, and get formatted output in the terminal.

## Quick Start

```bash
# Install dependencies (dev includes duckdb for tests)
uv sync

# Run the CLI
uv run qdo --help

# Run tests
uv run pytest

# Lint, format, and type check
uv run ruff check .
uv run ruff format .
uv run ty check
```

## Critical Rules

### Pay for What You Use

This is the project's core engineering principle. Users should never pay (in install size, startup time, or runtime cost) for features they don't use.

**Install time** — Database backends beyond SQLite are optional extras:
```bash
pip install querido               # SQLite only
pip install 'querido[duckdb]'     # + DuckDB
pip install 'querido[snowflake]'  # + Snowflake
```

The factory (`connectors/factory.py`) catches `ImportError` and tells users how to install missing backends. When adding a new backend, always make it opt-in via `[project.optional-dependencies]` in `pyproject.toml`.

**Runtime / Lazy Imports** — All heavy imports must happen inside functions, not at module level. This keeps CLI startup fast. The only top-level imports allowed are: `typer`, stdlib modules, and type-checking-only imports behind `if TYPE_CHECKING`.

```python
# CORRECT
def my_command():
    from rich.table import Table  # imported only when this command runs
    ...

# WRONG
from rich.table import Table  # slows down every command, even --help
```

This applies to everything that isn't `typer` or stdlib: database drivers, Rich, Jinja2, platformdirs, tomli-w.

### SQL Templates
All database queries must use `.sql` template files in `src/querido/sql/templates/`. Never hardcode SQL strings in Python code (exception: connector `get_columns` methods, which use database-specific mechanisms like `PRAGMA`). Templates use Jinja2 syntax. See `ARCHITECTURE.md` for details.

### Connector Protocol
All database connectors implement the `Connector` protocol in `connectors/base.py`. Connectors are context managers — always use `with create_connector(config) as conn:` in CLI commands. When adding a new database backend, implement the full protocol including `__enter__`/`__exit__`.

### Input Validation
Table names are validated at the CLI boundary using `validate_table_name()` from `connectors/base.py`. This prevents SQL injection in templates and f-string interpolations. Always call this before passing a table name to any query.

## Project Layout

Read `ARCHITECTURE.md` for the full structure. Key locations:

- `src/querido/cli/` — CLI commands (one file per subcommand, plus `_util.py` for shared helpers)
- `src/querido/connectors/` — Database connectors (one file per backend; DuckDB also handles Parquet)
- `src/querido/sql/templates/` — SQL templates (organized by command, then dialect)
- `src/querido/output/` — Output formatting (Rich tables, HTML pages, Markdown, JSON, CSV)
- `src/querido/config.py` — TOML config loading, connection resolution (incl. Parquet detection)
- `tests/integration/` — Integration tests (SQLite + DuckDB)

## Commands

### inspect — table structure
```bash
qdo inspect -c <connection> -t <table> [-v]
```
Shows: column names, types, nullable, default, primary key, row count. Use `-v` for comments.

### preview — see rows
```bash
qdo preview -c <connection> -t <table> [-r <rows>]
```
Default 20 rows. Use `-r` to change.

### profile — data profiling
```bash
qdo profile -c <connection> -t <table> [--columns col1,col2] [--sample N] [--no-sample] [--top N]
```
Numeric: min, max, mean, median, stddev, null count/%, distinct. String: min/max length, null count/%, distinct. Auto-samples at >1M rows (100k sample). `--top N` shows most frequent values.

### dist — column distribution
```bash
qdo dist -c <connection> -t <table> -col <column> [--buckets N] [--top N]
```
Numeric: histogram with N buckets (default 20). Categorical: top N values by frequency (default 20).

### template — documentation template
```bash
qdo template -c <connection> -t <table> [--sample-values N]
```
Generates a documentation template with auto-populated metadata (column name, type, nullable, distinct count, min/max, sample values) and placeholder fields for business definitions, data owner, and notes. Default 3 sample values per column; use `--sample-values 0` to skip.

### explore — interactive TUI
```bash
qdo explore -c <connection> -t <table> [-r <rows>]
```
Interactive terminal UI for data exploration. Requires `pip install 'querido[tui]'`. Key bindings: `q` quit, `?` help, `i` inspect metadata, `m` toggle sidebar, `/` filter, `Escape` clear, `r` refresh. Click column headers to sort.

### serve — local web UI
```bash
qdo serve -c <connection> [--port 8888] [--host 127.0.0.1]
```
Launches a local web server for interactive data exploration in the browser. Requires `pip install 'querido[web]'`. Features: table list with search, tabbed detail pages (inspect, preview, profile, template, lineage), distribution drill-down, pivot table builder. Uses HTMX for dynamic loading, keyboard shortcuts (`?` help, `/` search).

### search — find tables and columns
```bash
qdo search -p <pattern> -c <connection> [--type {table,column,all}]
```
Case-insensitive substring match across table and column names.

### sql — generate SQL statements
```bash
qdo sql select -c <conn> -t <table>     # SELECT with all columns
qdo sql insert -c <conn> -t <table>     # INSERT with placeholders
qdo sql ddl -c <conn> -t <table>        # CREATE TABLE DDL
qdo sql scratch -c <conn> -t <table>    # TEMP TABLE + sample INSERTs
qdo sql task -c <conn> -t <table>       # Snowflake task template
qdo sql udf -c <conn> -t <table>        # UDF template
qdo sql procedure -c <conn> -t <table>  # Stored procedure (Snowflake)
```

### snowflake — Snowflake-specific commands
```bash
qdo snowflake semantic -c <conn> -t <table>        # Generate Cortex Analyst semantic model YAML
qdo snowflake semantic -c <conn> -t <table> -o out.yaml  # Write to file
qdo snowflake lineage --object <fqn> -c <conn>     # Trace lineage via GET_LINEAGE
qdo snowflake lineage --object <fqn> -c <conn> -d upstream --depth 3
```

### config — manage connections
```bash
qdo config add --name mydb --type sqlite --path ./data.db
qdo config list
```

### Global flags
- `--show-sql` — print rendered SQL to stderr with syntax highlighting
- `--format {rich,markdown,json,csv,html,yaml}` / `-f` — output format (default: rich)
- `--version` / `-V` — show version

### Connection resolution
`-c` accepts a named connection from `connections.toml` or a file path. Extension determines type: `.duckdb`/`.ddb` → DuckDB, `.parquet` → Parquet (via DuckDB), else → SQLite. Override with `--db-type`.

## Test Data

```bash
uv run python scripts/init_test_data.py   # creates data/test.db and data/test.duckdb
```

| Database | Tables | Rows |
|----------|--------|------|
| test.db (SQLite) | customers, products, datatypes | 1000 / 1000 / 100 |
| test.duckdb | customers, products, datatypes | 1000 / 1000 / 100 |

**customers**: customer_id, first_name, last_name, company, city, country, phone1, phone2, email, subscription_date, website

**products**: name, description, brand, category, price, currency, stock, ean, color, size, availability, internal_id

**datatypes**: mixed types for edge-case testing (blobs, JSON, nulls, negatives, large ints)

## Build Plan

See `PLAN.md` for the phased build plan. Work through phases in order. Each phase has concrete deliverables and tests.

## Dependency Management

- **uv** for package management — no `requirements.txt`, everything in `pyproject.toml`
- **ruff** for linting and formatting
- **ty** for type checking
- **pytest** for testing
- DuckDB and Snowflake are optional extras, not default dependencies
- DuckDB is included in the `[dependency-groups] dev` group so tests always run

## Config File

Connections are stored in TOML. Location determined by `platformdirs`:
- Linux: `~/.config/qdo/connections.toml`
- macOS: `~/Library/Application Support/qdo/connections.toml`
- Windows: `%APPDATA%\qdo\connections.toml`
- Override: `QDO_CONFIG` env var

## Code Quality

Before committing any changes, ensure all three checks pass:

```bash
uv run ruff check .        # lint — must pass with zero errors
uv run ruff format .       # format — must produce no changes
uv run ty check            # type check — must pass with zero errors
```

Ruff config is in `pyproject.toml` (`[tool.ruff]`). Line length is 99. ty config is under `[tool.ty.environment]`.

There are no pre-commit hooks — just run these manually before committing.

## Style Guide

- Keep functions focused and small
- Don't over-engineer — solve the current problem, not hypothetical future ones
- Tests should prove things work, not chase coverage numbers
- Use type hints on function signatures
- Don't add docstrings/comments unless the logic is non-obvious
- Connectors are context managers — use `with` statements, not try/finally
