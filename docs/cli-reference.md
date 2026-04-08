---
layout: default
title: CLI Reference
---

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

### Explore

| Command | Purpose |
|---------|---------|
| `qdo context -c CONN -t TABLE` | Schema + stats + sample values in one call |
| `qdo inspect -c CONN -t TABLE` | Column metadata and row count |
| `qdo preview -c CONN -t TABLE [-r ROWS]` | Preview rows (default 20) |
| `qdo profile -c CONN -t TABLE [--top N]` | Statistical profile (min/max/mean/nulls/distinct) |
| `qdo dist -c CONN -t TABLE -C COLUMN` | Column value distribution / histogram |
| `qdo values -c CONN -t TABLE -C COL` | Distinct values for a column |
| `qdo quality -c CONN -t TABLE` | Data quality summary (nulls, uniqueness, issues) |
| `qdo diff -c CONN -t A --target B` | Compare schemas between two tables |
| `qdo joins -c CONN -t TABLE [--target T]` | Discover join keys between tables |

### Query

| Command | Purpose |
|---------|---------|
| `qdo query -c CONN --sql "SQL" [--limit N]` | Execute ad-hoc SQL query |
| `qdo catalog -c CONN [--pattern P] [--tables-only]` | Full database catalog |
| `qdo pivot -c CONN -t TABLE -g COL -a "sum(col)"` | Aggregate with GROUP BY |
| `qdo explain -c CONN --sql "SQL" [--analyze]` | Show query execution plan |
| `qdo assert -c CONN --sql "SQL" --expect N` | Assert query result (exit 0=pass, 1=fail) |
| `qdo export -c CONN -t TABLE -o file.csv` | Export to file (csv/tsv/json/jsonl) |

### Generate

| Command | Purpose |
|---------|---------|
| `qdo sql select -c CONN -t TABLE` | Generate SELECT statement |
| `qdo sql ddl -c CONN -t TABLE` | Generate CREATE TABLE DDL |
| `qdo sql scratch -c CONN -t TABLE` | Temp table + sample INSERTs |
| `qdo template -c CONN -t TABLE` | Generate documentation template |
| `qdo view-def -c CONN -v VIEW` | View SQL definition |

### Manage

| Command | Purpose |
|---------|---------|
| `qdo config add` | Add a named connection |
| `qdo config clone -s SRC -n NAME` | Clone a connection with overrides |
| `qdo config list` | List configured connections |
| `qdo cache sync -c CONN` | Cache metadata locally |
| `qdo metadata init -c CONN -t TABLE` | Generate metadata YAML template |
| `qdo metadata show -c CONN -t TABLE` | Show stored metadata |
| `qdo metadata list -c CONN` | List metadata files |
| `qdo metadata refresh -c CONN -t TABLE` | Refresh machine fields, keep human fields |
| `qdo completion show SHELL` | Generate shell completion scripts |

### Snowflake

| Command | Purpose |
|---------|---------|
| `qdo snowflake semantic -c CONN -t TABLE` | Cortex Analyst YAML |
| `qdo snowflake lineage -c CONN --object NAME` | Snowflake GET_LINEAGE graph |
| `qdo sql task -c CONN -t TABLE` | Task template |
| `qdo sql procedure -c CONN -t TABLE` | Stored procedure template |

### Interactive

| Command | Purpose |
|---------|---------|
| `qdo explore -c CONN -t TABLE` | Interactive TUI explorer |
| `qdo serve -c CONN` | Launch web UI (default port 8888) |

### Learn

| Command | Purpose |
|---------|---------|
| `qdo tutorial explore` | 15-lesson core workflow tutorial |
| `qdo tutorial agent` | 13-lesson metadata + AI-assisted SQL tutorial |

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
| `--debug` | Enable debug logging to stderr |
| `--version`, `-V` | Show version |

## Agent Mode

Set `QDO_FORMAT` to get structured output from all commands by default, without passing `--format` on every call:

```bash
export QDO_FORMAT=json
qdo catalog -c mydb              # full schema as JSON
qdo query -c mydb --sql "..."    # query results as JSON
qdo values -c mydb -t t -C col   # distinct values as JSON
```

Priority: explicit `--format` flag > `QDO_FORMAT` env var > `rich` (default). Invalid `QDO_FORMAT` values are silently ignored (falls back to `rich`).

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

# Search for tables or columns containing "email"
qdo catalog -c prod --pattern email

# Get JSON metadata for scripting
qdo inspect -c mydb -t users -f json

# Get full database catalog as JSON (for agents or scripting)
qdo catalog -c mydb -f json

# List just table names
qdo catalog -c mydb --tables-only

# Run an ad-hoc query
qdo query -c mydb --sql "select count(*) from users where age > 30" -f json

# Run SQL from a file
qdo query -c mydb --file report.sql

# Pipe SQL via stdin
echo "select * from events limit 10" | qdo query -c analytics.duckdb

# Generate DDL for a table
qdo sql ddl -c mydb -t users

# Launch web UI for interactive exploration
qdo serve -c analytics.duckdb
```
