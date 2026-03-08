# querido

> **querido** (Spanish): *dear*, *beloved*
>
> Also: **qu**e**ri**-**do** — your data is dear to you, and you want to query it. `qdo` = query, do. Simple as that.

A fast CLI toolkit for common data analysis tasks against SQLite, DuckDB, Snowflake, and Parquet files.

## Install

```bash
# Development — run via uv from the project directory
uv sync
uv run qdo --help

# Global install — puts qdo on your PATH
uv tool install .
qdo --help
```

### Optional backends

SQLite support is always available (stdlib). Other backends are opt-in:

```bash
pip install 'querido[duckdb]'      # DuckDB + Parquet support
pip install 'querido[snowflake]'   # Snowflake support
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

# Query a Parquet file directly (table name = filename stem)
qdo preview --connection data.parquet --table data
```

## Configuration

Connections are stored in `connections.toml` at your platform's config directory:

- **Linux**: `~/.config/qdo/connections.toml`
- **macOS**: `~/Library/Application Support/qdo/connections.toml`
- **Windows**: `%APPDATA%\qdo\connections.toml`

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
uv run ty check src/              # type check
uv run pytest                     # test
```
