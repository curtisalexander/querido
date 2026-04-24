---
layout: default
title: CLI Reference
---

# qdo CLI Reference

`qdo` is an agent-first data exploration CLI for SQLite, DuckDB, Snowflake, and Parquet files.

## Installation

```bash
uv pip install querido              # core (SQLite)
uv pip install 'querido[duckdb]'    # + DuckDB support
uv pip install 'querido[snowflake]' # + Snowflake support
uv pip install 'querido[tui]'       # Interactive TUI (qdo explore)
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

## Promoted Workflow

qdo is optimized around this path:

`catalog -> context -> metadata -> query/assert -> report/bundle`

Use drill-down commands like `inspect`, `preview`, `profile`, `quality`, `values`, `dist`, `joins`, and `diff` when that default path leaves a specific gap.

## Commands

### Start Here

| Command | Purpose |
|---------|---------|
| `qdo catalog -c CONN [--pattern P] [--tables-only]` | Discover tables, columns, and row counts |
| `qdo context -c CONN -t TABLE` | Schema + stats + sample values in one call |
| `qdo metadata init -c CONN -t TABLE` | Create metadata YAML for shared table knowledge |
| `qdo metadata show -c CONN -t TABLE` | Read stored metadata back into the workflow |
| `qdo query -c CONN --sql "SQL" [--limit N]` | Execute ad-hoc SQL query |
| `qdo query -c CONN --from SESSION:STEP` | Reuse SQL from a recorded query step |
| `qdo assert -c CONN --sql "SQL" --expect N` | Assert query result (exit 0=pass, 1=fail) |
| `qdo report table -c CONN -t TABLE -o report.html` | Generate a shareable HTML hand-off report |
| `qdo bundle export -c CONN -t TABLE -o bundle.zip` | Export portable team knowledge |

### Investigate Deeper

| Command | Purpose |
|---------|---------|
| `qdo inspect -c CONN -t TABLE` | Column metadata and row count |
| `qdo preview -c CONN -t TABLE [-r ROWS]` | Preview rows (default 20) |
| `qdo profile -c CONN -t TABLE [--top N]` | Statistical profile (min/max/mean/nulls/distinct) |
| `qdo profile -c CONN -t TABLE --quick` | Quick mode: nulls + distinct only (auto at 50+ cols) |
| `qdo profile -c CONN -t TABLE --classify` | Classify columns by category (implies --quick) |
| `qdo profile -c CONN -t TABLE --column-set NAME` | Profile using a saved column set |
| `qdo dist -c CONN -t TABLE -C COLUMN` | Column value distribution / histogram |
| `qdo values -c CONN -t TABLE -C COL` | Distinct values for a column |
| `qdo freshness -c CONN -t TABLE [--stale-after DAYS]` | Temporal column detection + recency summary |
| `qdo quality -c CONN -t TABLE` | Data quality summary (nulls, uniqueness, issues) |
| `qdo diff -c CONN -t A --target B` | Compare schemas between two tables |
| `qdo joins -c CONN -t TABLE [--target T]` | Discover join keys between tables |

### Query And Validate

| Command | Purpose |
|---------|---------|
| `qdo assert -c CONN --sql "SQL" --expect N` | Assert query result (exit 0=pass, 1=fail) |
| `qdo pivot -c CONN -t TABLE -g COL -a "sum(col)"` | Aggregate with GROUP BY |
| `qdo explain -c CONN --sql "SQL" [--analyze]` | Show query execution plan |
| `qdo export -c CONN -t TABLE -o file.csv` | Export to file (csv/tsv/json/jsonl) |
| `qdo export -c CONN --from SESSION:STEP -o file.csv` | Export using SQL from a recorded query step |

### Generate

| Command | Purpose |
|---------|---------|
| `qdo sql select -c CONN -t TABLE` | Generate SELECT statement |
| `qdo sql ddl -c CONN -t TABLE` | Generate CREATE TABLE DDL |
| `qdo sql scratch -c CONN -t TABLE` | Temp table + sample INSERTs |
| `qdo template -c CONN -t TABLE` | Generate documentation template |
| `qdo view-def -c CONN -v VIEW` | View SQL definition |

### Automate And Share

| Command | Purpose |
|---------|---------|
| `qdo workflow list` | List bundled, project, and user workflows |
| `qdo workflow run NAME key=value` | Execute a declarative workflow |
| `qdo workflow lint NAME` | Lint a workflow before running it |
| `qdo workflow from-session NAME` | Draft a workflow from a recorded session |
| `qdo session start NAME` | Create a new session directory |
| `qdo session list` | List recorded sessions |
| `qdo session show NAME` | Review recorded steps in a session |
| `qdo session replay NAME [--into NEW]` | Re-execute successful recorded steps into a replay session |
| `qdo report session NAME -o report.html` | Generate a shareable HTML session narrative |

### Setup

| Command | Purpose |
|---------|---------|
| `qdo config add` | Add a named connection |
| `qdo config clone -s SRC -n NAME` | Clone a connection with overrides |
| `qdo config list` | List configured connections |
| `qdo config test NAME` | Test a configured connection |
| `qdo config remove --name NAME` | Remove a named connection |
| `qdo config column-set save` | Save a named column set |
| `qdo config column-set list` | List saved column sets |
| `qdo config column-set show` | Show columns in a set |
| `qdo config column-set delete` | Delete a column set |
| `qdo cache sync -c CONN` | Cache metadata locally |
| `qdo cache status [-c CONN]` | Show cache age and coverage |
| `qdo cache clear [-c CONN]` | Clear cached metadata |
| `qdo metadata init -c CONN -t TABLE` | Generate metadata YAML template |
| `qdo metadata show -c CONN -t TABLE` | Show stored metadata |
| `qdo metadata list -c CONN` | List metadata files |
| `qdo metadata search -c CONN QUERY [--limit N]` | Lexical search across stored table + column descriptions |
| `qdo metadata score -c CONN` | Rank metadata completeness |
| `qdo metadata suggest -c CONN -t TABLE [--apply]` | Propose deterministic metadata additions |
| `qdo metadata refresh -c CONN -t TABLE` | Refresh machine fields, keep human fields |
| `qdo metadata undo -c CONN -t TABLE [--dry-run]` | Restore the last qdo-managed metadata snapshot |
| `qdo agent list` | List packaged coding-agent integration docs |
| `qdo agent install skill` | Install Claude Code skill files into `skills/querido/` |
| `qdo agent install continue` | Install Continue.dev rules into `.continue/rules/` |
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
| `qdo explore -c CONN -t TABLE` | Interactive TUI with selected-column context and wide-table triage |

### Learn

| Command | Purpose |
|---------|---------|
| `qdo tutorial explore` | 10-lesson compounding-loop walkthrough |
| `qdo tutorial agent` | 13-lesson metadata + AI-assisted SQL tutorial |

## Output Formats

```bash
qdo inspect -c mydb -t users -f json    # JSON to stdout
qdo inspect -c mydb -t users -f csv     # CSV to stdout
qdo inspect -c mydb -t users -f markdown # Markdown table
qdo inspect -c mydb -t users -f html    # Opens in browser
```

Default format is `rich` (pretty terminal tables). The shared structured envelope is available in `json` and `agent` format for the main scan/query commands and an expanding set of management/reference commands. File-producing commands such as `report table` and `export` keep their artifact-oriented behavior.

## Piping & Scripting

Data goes to **stdout**; spinners and status messages go to **stderr**. This means you can safely pipe output:

```bash
qdo preview -c mydb -t users -f csv | head -5
qdo inspect -c mydb -t users -f json | jq '.columns[].name'
qdo profile -c mydb -t orders -f csv > profile.csv
```

## Session Step Reuse

When `QDO_SESSION` is set, `query` steps are recorded and can be referenced later by `query` and `export`. Record the source step with `-f json` so `--from` has the canonical SQL to replay (rich-format steps are rejected):

```bash
QDO_SESSION=scratch qdo -f json query -c mydb --sql "select * from orders where status = 'pending'"
qdo query  -c mydb --from scratch:1
qdo export -c mydb --from scratch:last -o pending-orders.csv
```

Use `<session>:<step>` or `<session>:last`. `--from` is mutually exclusive with direct SQL input (`--sql` / `--file`) and with table-based export input (`--table`).

## Session Replay

Replay reruns the successful recorded commands from a prior session in order and records the rerun into a new session:

```bash
qdo session replay scratch
qdo session replay scratch --into rerun-scratch
qdo session replay scratch --last 3
```

By default replay stops on the first failed rerun. Use `--continue-on-error` to keep going, and `qdo session show <replay-session>` to inspect the replayed run afterward.

## Metadata Undo

Metadata undo restores the previous on-disk YAML snapshot for one table, but only for qdo-managed writes such as `metadata init`, `metadata refresh`, `metadata suggest --apply`, and `--write-metadata` flows:

```bash
qdo metadata undo -c mydb -t orders
qdo metadata undo -c mydb -t orders --dry-run
qdo metadata undo -c mydb -t orders --steps 2
```

Undo is table-scoped and guarded: if the current file has drifted since the last qdo-managed write, qdo refuses to restore unless you pass `--force`.

## Global Options

| Flag | Description |
|------|-------------|
| `--format`, `-f` | Output format: `rich`, `json`, `agent`, `csv`, `markdown`, `html`, `yaml` |
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

# Wide table: classify columns, then profile a subset
qdo profile -c prod -t wide_table --classify
qdo profile -c prod -t wide_table --columns "col1,col2,col3"
qdo config column-set save -c prod -t wide_table -n default --columns "col1,col2,col3"
qdo profile -c prod -t wide_table --column-set default

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

# Generate a shareable single-file HTML report for a table
qdo report table -c analytics.duckdb -t orders -o orders.html
```
