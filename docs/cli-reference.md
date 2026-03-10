# qdo CLI Reference

`qdo` is a CLI data-analysis toolkit for SQLite, DuckDB, and Snowflake databases.

## Installation

```bash
uv pip install querido              # core (SQLite)
uv pip install 'querido[duckdb]'    # + DuckDB support
uv pip install 'querido[snowflake]' # + Snowflake support
uv pip install 'querido[tui]'       # Interactive TUI (qdo explore)
uv pip install 'querido[web]'       # Web UI (qdo serve)
```

## Connection Setup

```bash
# Add a named connection
qdo config add --name mydb --type duckdb --path ./analytics.duckdb

# Or point directly at a file
qdo preview -c ./my.db -t users
qdo preview -c ./data.duckdb -t sales
qdo preview -c ./file.parquet -t file   # DuckDB auto-registers parquet
```

Connections are stored in `~/.config/qdo/connections.toml` (Linux), `~/Library/Application Support/qdo/connections.toml` (macOS), or `%LOCALAPPDATA%\qdo\connections.toml` (Windows). Override with `QDO_CONFIG` env var.

## Commands

| Command | Purpose |
|---------|---------|
| `qdo inspect -c CONN -t TABLE` | Column metadata and row count |
| `qdo preview -c CONN -t TABLE [-r ROWS]` | Preview rows (default 20) |
| `qdo profile -c CONN -t TABLE [--top N]` | Statistical profile (min/max/mean/nulls/distinct) |
| `qdo dist -c CONN -t TABLE -col COLUMN` | Column value distribution / histogram |
| `qdo search -c CONN -p PATTERN` | Search tables/columns by name |
| `qdo lineage -c CONN -v VIEW` | View SQL definition |
| `qdo template -c CONN -t TABLE` | Generate documentation template |
| `qdo sql select -c CONN -t TABLE` | Generate SELECT statement |
| `qdo sql ddl -c CONN -t TABLE` | Generate CREATE TABLE DDL |
| `qdo cache sync -c CONN` | Cache metadata locally for fast search |
| `qdo serve -c CONN` | Launch web UI (default port 8888) |
| `qdo explore -c CONN -t TABLE` | Interactive TUI explorer |
| `qdo snowflake semantic -c CONN -t TABLE` | Cortex Analyst YAML |
| `qdo snowflake lineage -c CONN --object NAME` | Snowflake lineage graph |
| `qdo config add` | Add a named connection |
| `qdo config clone -s SRC -n NAME` | Clone a connection with overrides |
| `qdo config list` | List configured connections |

## Output Formats

```bash
qdo inspect -c mydb -t users -f json    # JSON to stdout
qdo inspect -c mydb -t users -f csv     # CSV to stdout
qdo inspect -c mydb -t users -f markdown # Markdown table
qdo inspect -c mydb -t users -f html    # Opens in browser
```

Default format is `rich` (pretty terminal tables). Use `--format json` or `--format csv` for machine-readable output that can be piped to other tools.

## Piping & Scripting

Data goes to **stdout**; spinners and status messages go to **stderr**. This means you can safely pipe output:

```bash
qdo preview -c mydb -t users -f csv | head -5
qdo inspect -c mydb -t users -f json | jq '.columns[].name'
qdo profile -c mydb -t orders -f csv > profile.csv
```

## Global Options

| Flag | Description |
|------|-------------|
| `--format`, `-f` | Output format: `rich`, `json`, `csv`, `markdown`, `html`, `yaml` |
| `--show-sql` | Print rendered SQL to stderr before executing |
| `--version`, `-V` | Show version |

## Query Interruption

Press **Ctrl-C** to cancel a running query. The CLI will:
1. Send a cancel signal to the database (works with SQLite, DuckDB, and Snowflake)
2. Print how long the query ran before cancellation
3. Exit with code 130

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (bad input, database error, etc.) |
| 130 | Query cancelled (Ctrl-C) |

## Working with Multiple Snowflake Databases

In Snowflake, each database often requires a specific role and warehouse. qdo handles this with **one named connection per database context** — each connection captures the account, credentials, database, role, and warehouse together.

Use `config clone` to quickly create per-database connections from a base:

```bash
# Set up a base Snowflake connection
qdo config add --name sf-base --type snowflake \
  --account xy123.us-east-1 --user analyst \
  --warehouse COMPUTE_WH --database ANALYTICS --schema PUBLIC \
  --role ANALYST --auth externalbrowser

# Clone for other databases, changing only what differs
qdo config clone --source sf-base --name sf-finance \
  --database FINANCE_DB --role FINANCE_ROLE --warehouse FINANCE_WH

qdo config clone --source sf-base --name sf-marketing \
  --database MARKETING_DB --role MARKETING_ROLE

# See all connections at a glance (shows database/role/warehouse columns)
qdo config list

# Switch databases by switching the -c flag
qdo preview -c sf-finance -t transactions
qdo profile -c sf-marketing -t campaigns
```

This design is intentional: each connection is self-contained and correct, so you never need to remember which role or warehouse goes with which database.

## Examples

```bash
# Quick look at a table
qdo preview -c analytics.duckdb -t events -r 10

# Profile with top-N frequent values
qdo profile -c prod -t orders --top 5

# Search for columns containing "email"
qdo search -c prod -p email --type column

# Get JSON metadata for scripting
qdo inspect -c mydb -t users -f json

# Generate DDL for a table
qdo sql ddl -c mydb -t users

# Launch web UI for interactive exploration
qdo serve -c analytics.duckdb
```
