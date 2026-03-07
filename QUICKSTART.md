# qdo Quick Start (for agents)

CLI data analysis tool. Query SQLite and DuckDB from the terminal.

## Setup

```bash
uv sync
uv run python scripts/init_test_data.py   # creates data/test.db and data/test.duckdb
```

## Optional backends

SQLite is always available (stdlib). Other backends are opt-in:

```bash
pip install 'querido[duckdb]'      # DuckDB support
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
qdo profile -c <connection> -t <table> [--columns col1,col2] [--sample N] [--no-sample]
```
Shows statistical summaries per column:
- **Numeric**: min, max, mean, median, stddev, null count/%, distinct count
- **String**: min/max length, null count/%, distinct count

Sampling: auto-samples at >1M rows (100k sample). Use `--sample N` to set sample size, `--no-sample` to force full scan.

## Connection resolution

`-c` accepts either:
- A **file path**: `qdo inspect -c ./data/test.db -t customers`
- A **named connection** from `connections.toml` (see below)

File extension determines type: `.duckdb`/`.ddb` → DuckDB, else SQLite. Override with `--db-type sqlite|duckdb`.

## Config file

Location: `~/.config/qdo/connections.toml` (Linux), `%APPDATA%\qdo\connections.toml` (Windows).
Override with `QDO_CONFIG` env var.

```toml
[connections.mydb]
type = "duckdb"
path = "./analytics.duckdb"
```

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
```

## Development

```bash
uv run pytest                        # run tests
uv run ruff check src/ tests/       # lint
uv run ruff format src/ tests/      # format
uv run ty check src/                # type check
```
