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

uv tool install 'querido[snowflake]' \
  --find-links https://github.com/curtisalexander/querido/releases/expanded_assets/v0.1.0
```

With all optional backends:

```bash
uv tool install 'querido[all]' \
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
uv pip install 'querido[all]'        # Everything
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

[connections.prod-keypair]
type = "snowflake"
account = "xy12345.us-east-1"
user = "SVC_USER"
warehouse = "ANALYTICS_WH"
database = "PROD"
schema = "PUBLIC"
private_key_path = "~/.snowflake/rsa_key.p8"
# private_key_passphrase = "optional-passphrase"
```

### Managing connections via CLI

```bash
qdo config add --name mydb --type sqlite --path ./data.db
qdo config add --name prod --type snowflake --account xy123 --database PROD
qdo config add --name svc --type snowflake --account xy123 --database PROD \
  --private-key-path ~/.snowflake/rsa_key.p8
qdo config list
```

You can also pass a file path directly: `qdo preview --connection ./my.db --table users`

### Working with multiple Snowflake databases

In Snowflake, accessing a different database often requires a different role and warehouse. Rather than passing `--database`, `--role`, and `--warehouse` flags on every command, qdo uses **one named connection per database context**. Each connection captures the full set of credentials and session parameters needed for that database.

**Quick setup with `config clone`** — create per-database connections from a base connection, overriding only what changes:

```bash
# Start with a base connection
qdo config add --name sf-base --type snowflake \
  --account xy123.us-east-1 --user analyst \
  --warehouse COMPUTE_WH --database ANALYTICS --schema PUBLIC \
  --role ANALYST --auth externalbrowser

# Clone for other databases, overriding database/role/warehouse as needed
qdo config clone --source sf-base --name sf-finance \
  --database FINANCE_DB --role FINANCE_ROLE --warehouse FINANCE_WH

qdo config clone --source sf-base --name sf-marketing \
  --database MARKETING_DB --role MARKETING_ROLE
```

**Use `config list` to see all connections at a glance** — when Snowflake connections are present, the table shows dedicated columns for database, role, and warehouse:

```bash
qdo config list
```

**Then just switch with `-c`:**

```bash
qdo preview -c sf-finance -t transactions
qdo profile -c sf-marketing -t campaigns
qdo inspect -c sf-base -t events
```

This approach is intentional: each connection is self-contained and correct, so you never have to remember which role goes with which database. The `config clone` command makes setup fast — you only specify the fields that differ.

## Development

```bash
uv run ruff check src/ tests/    # lint
uv run ruff format src/ tests/   # format
uv run ty check                   # type check
uv run pytest                     # test
```

### Dependency updates

```bash
uv run python scripts/check_deps.py              # check for outdated deps
uv run python scripts/check_deps.py --update     # update safe packages
uv run python scripts/check_deps.py --audit      # also check for known CVEs
```

New releases are quarantined for 7 days (configurable with `--days`) before `--update` will apply them. This guards against supply-chain attacks by giving the community time to detect and yank compromised packages.
