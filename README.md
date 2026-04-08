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
uv pip install 'querido[duckdb]'     # DuckDB + Parquet support
uv pip install 'querido[snowflake]'  # Snowflake support
uv pip install 'querido[tui]'        # Interactive TUI (qdo explore)
uv pip install 'querido[web]'        # Web UI (qdo serve)
uv pip install 'querido[all]'        # Everything
```

## Quick Start

```bash
# 1. See all tables and columns
qdo catalog -c my-db

# 2. Get everything about a table at once (schema + stats + sample values)
qdo context -c my-db --table orders

# 3. Drill into structure
qdo inspect -c my-db --table orders

# 4. See real rows
qdo preview -c my-db --table orders --rows 20

# 5. Statistical summary
qdo profile -c my-db --table orders

# 6. Run a query
qdo query -c my-db --sql "select status, count(*) from orders group by 1"
```

All commands support `--format json` (or `csv`, `markdown`, `html`, `yaml`). Output goes to stdout; spinners go to stderr so piping is safe:

```bash
qdo context -c my-db -t orders -f json | jq '.columns[].name'
qdo catalog -c my-db -f json > schema.json
qdo profile -c my-db -t orders -f csv > stats.csv
```

## Commands

### Explore — understand your data

```bash
qdo context   -c my-db -t orders              # schema + stats + sample values in one call
qdo inspect   -c my-db -t orders              # column types, nullable, PK, row count
qdo preview   -c my-db -t orders -r 20        # see rows
qdo profile   -c my-db -t orders --top 10     # stats + top frequent values
qdo dist      -c my-db -t orders -C amount    # histogram or value frequencies
qdo values    -c my-db -t orders -C status    # all distinct values for a column
qdo quality   -c my-db -t orders              # null rates, uniqueness, anomalies
qdo diff      -c my-db -t orders --target v2  # compare two table schemas
qdo joins     -c my-db -t orders              # suggest likely join keys
```

### Query — run and validate SQL

```bash
qdo query     -c my-db --sql "select ..."     # ad-hoc SQL
qdo catalog   -c my-db                        # all tables and columns
qdo catalog   -c my-db --pattern order        # filter tables/columns by name
qdo pivot     -c my-db -t orders -g region -a "sum(amount)"  # GROUP BY
qdo explain   -c my-db --sql "select ..."     # query execution plan
qdo assert    -c my-db --sql "..." --expect 0 # assert a condition (CI-friendly)
qdo export    -c my-db -t orders -o out.csv   # export to file
```

### Generate — scaffold SQL and docs

```bash
qdo sql select   -c my-db -t orders           # SELECT scaffold
qdo sql ddl      -c my-db -t orders           # CREATE TABLE DDL
qdo sql scratch  -c my-db -t orders           # TEMP TABLE + sample INSERTs
qdo template     -c my-db -t orders           # documentation template
qdo view-def     -c my-db --view my_view      # SQL definition of a view
```

### Manage — connections, cache, metadata

```bash
qdo config add  --name mydb --type duckdb --path ./my.duckdb
qdo config list
qdo config clone --source sf-base --name sf-finance --database FINANCE_DB
qdo cache sync  -c my-db
qdo completion show fish > ~/.config/fish/completions/qdo.fish

# Metadata (business context for AI-assisted SQL)
qdo metadata init    -c my-db -t orders       # create metadata YAML
qdo metadata edit    -c my-db -t orders       # open in $EDITOR
qdo metadata show    -c my-db -t orders       # read back metadata
qdo metadata list    -c my-db                 # completeness overview
qdo metadata refresh -c my-db -t orders       # re-profile, keep human fields
```

### Snowflake — platform-specific commands

```bash
qdo snowflake semantic -c prod -t my_table              # Cortex Analyst YAML
qdo snowflake lineage -c prod --object DB.SCHEMA.TABLE  # GET_LINEAGE query
qdo sql task -c prod -t my_table                        # task template
qdo sql procedure -c prod -t my_table                   # stored procedure template
```

### Interactive — TUI and web UI

```bash
qdo explore -c my-db -t orders               # terminal UI (requires querido[tui])
qdo serve   -c my-db --port 8888             # web UI (requires querido[web])
```

### Learn — built-in tutorials

```bash
qdo tutorial explore                 # 15-lesson core workflow
qdo tutorial agent                   # 13-lesson metadata + AI-assisted SQL
qdo tutorial explore --list          # list lessons
qdo tutorial explore --lesson 5      # jump to a lesson
```

### Parquet files

Pass the file path directly as the connection — DuckDB handles the rest:

```bash
qdo preview -c data.parquet --table data          # table name = file stem
qdo context -c data.parquet --table data          # full context
qdo catalog -c data.parquet                       # see all tables in the file
```

## context — the quick-look command

`context` is the fastest way to understand a table. It returns schema, statistics, and sample values in a single database scan (DuckDB/Snowflake), or a profile scan plus frequency queries (SQLite).

```bash
qdo context -c my-db -t orders                  # rich terminal output
qdo context -c my-db -t orders -f json          # machine-readable
qdo context -c my-db -t orders --sample-values 10   # more sample values
qdo context -c my-db -t orders --no-sample      # exact stats, no row sampling
```

If you've run `qdo metadata init` on the table, stored descriptions, valid values, and PII flags are merged in automatically.

JSON output shape:

```json
{
  "table": "orders",
  "dialect": "duckdb",
  "row_count": 50000,
  "table_description": "Customer orders placed through the website",
  "columns": [
    {
      "name": "status",
      "type": "VARCHAR",
      "nullable": true,
      "null_pct": 0.5,
      "distinct_count": 4,
      "sample_values": ["pending", "shipped", "delivered", "cancelled"],
      "description": "Fulfillment status",
      "valid_values": ["pending", "shipped", "delivered", "cancelled"]
    },
    {
      "name": "amount",
      "type": "DOUBLE",
      "nullable": true,
      "null_pct": 1.2,
      "distinct_count": 12543,
      "min": 0.99,
      "max": 9999.0,
      "sample_values": null
    }
  ]
}
```

## Using qdo with a coding agent

qdo is designed to be useful at the keyboard for a human analyst, and equally useful as a tool for a coding agent writing SQL on your behalf.

**Set up structured output once:**

```bash
export QDO_FORMAT=json     # all commands output JSON — no --format flag needed
```

Errors also output structured JSON in this mode:
```json
{"error": true, "code": "TABLE_NOT_FOUND", "message": "...", "hint": "..."}
```

**Give your agent the SKILL file:**

A ready-made context file lives at `skills/querido/SKILL.md`. Copy it into your agent harness so it knows how to use qdo:

| Harness | How to install |
|---------|----------------|
| **Claude Code** | Copy `skills/querido/` to your project's `skills/` directory, or paste the contents into your `CLAUDE.md` |
| **Pi** | Copy `skills/querido/SKILL.md` contents into your pi skills directory or paste into your project instructions |
| **Continue.dev** | Create `.continuerules` at your project root and paste the SKILL.md contents into it — or save it as `.continue/rules/qdo.md` |

**Recommended agent workflow:**

```bash
# 1. Give the agent a schema overview
qdo catalog -c my-db -f json

# 2. For each relevant table, get full context
qdo context -c my-db -t orders -f json

# 3. Run queries the agent generates
qdo query -c my-db --sql "..." -f json

# 4. If needed, enriched metadata gives the agent more signal
qdo metadata show -c my-db -t orders -f json
```

The `context` command is especially useful for agent workflows: it returns everything an LLM needs to write correct SQL for a table (column types, nullable flags, null rates, sample values for categoricals, min/max for numerics) in a single call.

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

## Shell Completions

Tab completion is available for bash, zsh, fish, and PowerShell:

```bash
# Bash — add to ~/.bashrc:
eval "$(qdo completion show bash)"

# Zsh — add to ~/.zshrc:
eval "$(qdo completion show zsh)"

# Fish — save to completions directory:
qdo completion show fish > ~/.config/fish/completions/qdo.fish

# PowerShell — add to $PROFILE:
qdo completion show powershell | Out-String | Invoke-Expression
```

Use `qdo completion show <shell> --hint` to see install instructions for a specific shell.

## Development

```bash
uv run ruff check src/ tests/    # lint
uv run ruff format src/ tests/   # format
uv run ty check                  # type check
uv run pytest                    # test
```

### Dependency updates

```bash
uv run python scripts/check_deps.py              # check for outdated deps
uv run python scripts/check_deps.py --update     # update safe packages
uv run python scripts/check_deps.py --audit      # also check for known CVEs
```

New releases are quarantined for 7 days (configurable with `--days`) before `--update` will apply them. This guards against supply-chain attacks by giving the community time to detect and yank compromised packages.
