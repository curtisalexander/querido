# qdo Quick Start (for agents)

CLI data analysis tool. Query SQLite, DuckDB, Snowflake, and Parquet files from the terminal.

## Setup

```bash
uv sync
uv run python scripts/init_test_data.py   # creates data/test.db and data/test.duckdb
```

## Optional backends

SQLite is always available (stdlib). Other backends are opt-in:

```bash
pip install 'querido[duckdb]'      # DuckDB support (also enables Parquet)
pip install 'querido[snowflake]'   # Snowflake support
```

Dev dependencies include duckdb so all tests run out of the box.

## Commands

### inspect — table structure
```bash
qdo inspect -c <connection> -t <table>
```
Shows: column names, types, nullable, default, primary key, row count.

### preview — see rows
```bash
qdo preview -c <connection> -t <table> [-r <rows>]
```
Default 20 rows. Use `-r` to change.

### profile — data profiling
```bash
qdo profile -c <connection> -t <table> [--columns col1,col2] [--sample N] [--no-sample] [--top N]
```
Shows statistical summaries per column:
- **Numeric**: min, max, mean, median, stddev, null count/%, distinct count
- **String**: min/max length, null count/%, distinct count

Sampling: auto-samples at >1M rows (100k sample). Use `--sample N` to set sample size, `--no-sample` to force full scan.

Top values: `--top N` shows the N most frequent values per column with counts and percentages.

### search — find tables and columns
```bash
qdo search -p <pattern> -c <connection> [--type {table,column,all}]
```
Case-insensitive substring match across table names and column names. Use `--type table` to search only table/view names, `--type column` for only columns.

### dist — column distribution
```bash
qdo dist -c <connection> -t <table> -col <column> [--buckets N] [--top N]
```
Visualize how a column's values are distributed:
- **Numeric columns**: histogram with N buckets (default 20, range 2-100)
- **Categorical columns**: top N values by frequency (default 20)

Always shows null count and percentage.

### sql — generate SQL statements
```bash
qdo sql select -c <connection> -t <table>     # SELECT with all columns
qdo sql insert -c <connection> -t <table>     # INSERT with named placeholders
qdo sql ddl -c <connection> -t <table>        # CREATE TABLE DDL
qdo sql scratch -c <connection> -t <table>    # CREATE TEMP TABLE + sample INSERTs
qdo sql task -c <connection> -t <table>       # Snowflake task template
qdo sql udf -c <connection> -t <table>        # UDF template
qdo sql procedure -c <connection> -t <table>  # Stored procedure (Snowflake only)
```
Generates copy-paste-ready SQL using table metadata. Output goes to stdout.

### config — manage connections
```bash
qdo config add --name mydb --type sqlite --path ./data.db
qdo config add --name prod --type snowflake --account xy123 --database PROD --schema PUBLIC
qdo config list
```

## Global flags

### `--show-sql`
Print the rendered SQL to stderr before executing, with syntax highlighting:
```bash
qdo --show-sql preview -c data/test.db -t customers -r 5
```

### `--format {rich,markdown,json,csv}` / `-f`
Output format. Default is `rich` (Rich terminal tables). Other formats write plain text to stdout for piping:
```bash
qdo --format json inspect -c data/test.db -t customers
qdo -f csv preview -c data/test.db -t customers
```

## Connection resolution

`-c` accepts either:
- A **file path**: `qdo inspect -c ./data/test.db -t customers`
- A **named connection** from `connections.toml` (see below)

File extension determines type:
- `.duckdb`/`.ddb` → DuckDB
- `.parquet` → Parquet (via DuckDB, table name = filename without extension)
- Otherwise → SQLite

Override with `--db-type sqlite|duckdb`.

### Parquet files

Parquet files are queried via DuckDB. The table name is the filename stem:
```bash
qdo inspect -c data/sales.parquet -t sales
qdo preview -c data/sales.parquet -t sales
qdo profile -c data/sales.parquet -t sales --top 5
```

## Config file

Location: `~/.config/qdo/connections.toml` (Linux), `%APPDATA%\qdo\connections.toml` (Windows).
Override with `QDO_CONFIG` env var.

```toml
[connections.mydb]
type = "duckdb"
path = "./analytics.duckdb"
```

Manage via CLI: `qdo config add` / `qdo config list`.

## Test databases

After running `init_test_data.py`, two databases exist in `data/`:

| Database | Tables | Rows each |
|----------|--------|-----------|
| test.db (SQLite) | customers, products, datatypes | 1,000 / 1,000 / 100 |
| test.duckdb | customers, products, datatypes | 1,000 / 1,000 / 100 |

**customers**: customer_id, first_name, last_name, company, city, country, phone1, phone2, email, subscription_date, website

**products**: name, description, brand, category, price, currency, stock, ean, color, size, availability, internal_id

**datatypes**: mixed types for edge-case testing (blobs, JSON, nulls, negatives, large ints, etc.)

## Example session

```bash
qdo inspect -c data/test.db -t customers       # see column metadata
qdo inspect -c data/test.duckdb -t products     # works with DuckDB too
qdo preview -c data/test.db -t customers -r 5   # preview 5 rows
qdo preview -c data/test.duckdb -t products     # default 20 rows
qdo profile -c data/test.db -t products         # full profile
qdo profile -c data/test.duckdb -t products --columns price,stock  # specific columns
qdo profile -c data/test.db -t customers --top 5  # top 5 frequent values
qdo dist -c data/test.db -t products -col price       # numeric distribution
qdo dist -c data/test.db -t customers -col country    # categorical distribution
qdo search -p email -c data/test.db                    # find tables/columns matching "email"
qdo sql select -c data/test.db -t customers            # generate SELECT statement
qdo sql scratch -c data/test.db -t products            # scratch table with sample data
qdo --show-sql inspect -c data/test.db -t customers    # see the SQL being run
qdo config list                                        # see configured connections
```

## Development

```bash
uv run pytest                        # run tests
uv run ruff check src/ tests/       # lint
uv run ruff format src/ tests/      # format
uv run ty check src/                # type check
```
