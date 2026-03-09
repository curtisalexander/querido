# querido

> **querido** (Spanish): *dear*, *beloved*
>
> Also: **queri**-**do** — your data is dear to you, and you want to query it. `qdo` = query, do.

A CLI toolkit for common data analysis tasks against SQLite, DuckDB, Snowflake, and Parquet files.

## Install

Pre-built wheels are available from [GitHub Releases](https://github.com/curtisalexander/querido/releases). Requires Python >= 3.12 and [uv](https://docs.astral.sh/uv/).

### With `uv tool install` (recommended)

Install globally so the `qdo` command is always available:

```bash
uv tool install querido \
  --find-links https://github.com/curtisalexander/querido/releases/expanded_assets/v0.1.0
```

With optional backends:

```bash
uv tool install 'querido[duckdb]' \
  --find-links https://github.com/curtisalexander/querido/releases/expanded_assets/v0.1.0
```

To upgrade later (update the version in the URL):

```bash
uv tool install --upgrade querido \
  --find-links https://github.com/curtisalexander/querido/releases/expanded_assets/v0.1.0
```

To uninstall:

```bash
uv tool uninstall querido
```

### With `uvx` (one-off runs)

Run without installing:

```bash
uvx \
  --from querido \
  --find-links https://github.com/curtisalexander/querido/releases/expanded_assets/v0.1.0 \
  qdo --help
```

### From source

```bash
# Development — run via uv from the project directory
uv sync
uv run qdo --help

# Global install from local checkout
uv tool install .
qdo --help
```

### Optional backends

SQLite support is always available (stdlib). Other backends are opt-in:

```bash
uv pip install 'querido[duckdb]'      # DuckDB + Parquet support
uv pip install 'querido[snowflake]'   # Snowflake support
uv pip install 'querido[tui]'        # Interactive TUI (qdo explore)
uv pip install 'querido[web]'        # Web UI (qdo serve)
```

## Usage

```bash
# See available commands
qdo --help

# Inspect a table's structure
qdo inspect --connection my-db --table users

# Preview rows from a table
qdo preview --connection my-db --table users --rows 20

# Profile a table's data
qdo profile --connection my-db --table users

# Profile with top frequent values
qdo profile --connection my-db --table users --top 10

# Show the SQL being executed
qdo --show-sql preview --connection my-db --table users

# Search for tables and columns by name
qdo search --pattern user --connection my-db

# Visualize column distribution (numeric histogram or categorical frequencies)
qdo dist --connection my-db --table users --column age

# Generate SQL statements (select, insert, ddl, scratch, udf, task, procedure)
qdo sql select --connection my-db --table users
qdo sql ddl --connection my-db --table users
qdo sql scratch --connection my-db --table users --rows 5

# Generate a documentation template with auto-populated metadata
qdo template --connection my-db --table users

# Retrieve the SQL definition of a view
qdo lineage --connection my-db --view my_view

# Cache table/column metadata locally for faster search
qdo cache sync --connection my-db
qdo cache status
qdo cache clear

# Interactive TUI for exploring data (requires querido[tui])
qdo explore --connection my-db --table users

# Local web UI for interactive exploration (requires querido[web])
qdo serve --connection my-db --port 8888 --host 127.0.0.1

# Output as JSON, CSV, Markdown, or HTML instead of Rich tables
qdo inspect --connection my-db --table users --format json
qdo inspect --connection my-db --table users --format html

# Query a Parquet file directly (table name = filename stem)
qdo preview --connection data.parquet --table data
```

### Snowflake-specific commands

```bash
# Generate a Cortex Analyst semantic model YAML
qdo snowflake semantic --connection prod --table my_table

# Trace upstream/downstream lineage via GET_LINEAGE
qdo snowflake lineage --connection prod --object DB.SCHEMA.TABLE --direction downstream

# Snowflake-only SQL templates
qdo sql task --connection prod --table my_table
qdo sql procedure --connection prod --table my_table
```

## Configuration

Connections are stored in `connections.toml` at your platform's config directory:

- **Linux**: `~/.config/qdo/connections.toml`
- **macOS**: `~/Library/Application Support/qdo/connections.toml`
- **Windows**: `%LOCALAPPDATA%\qdo\connections.toml`

```toml
[connections.my-db]
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

### Managing connections via CLI

```bash
qdo config add --name mydb --type sqlite --path ./data.db
qdo config add --name prod --type snowflake --account xy123 --database PROD
qdo config list
```

You can also pass a file path directly: `qdo preview --connection ./my.db --table users`

## Development

```bash
uv run ruff check src/ tests/    # lint
uv run ruff format src/ tests/   # format
uv run ty check                   # type check
uv run pytest                     # test
```
