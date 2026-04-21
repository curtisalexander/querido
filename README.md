# querido

> **querido** (Spanish): *dear*, *beloved*
>
> Also: **queri**-**do** — your data is dear to you, and you want to query it. `qdo` = query, do.

qdo is an agent-first data exploration CLI that turns one-off investigation into reusable team knowledge.

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
uv pip install 'querido[all]'        # Everything
```

## Quick Start

The opinionated qdo workflow is:

`discover -> understand -> capture -> answer -> hand off`

```bash
# 1. Discover what exists
qdo catalog -c my-db

# 2. Understand one table in depth
qdo context -c my-db --table orders

# 3. Capture what you learned
qdo metadata init -c my-db --table orders
qdo metadata suggest -c my-db --table orders --apply

# 4. Answer a question and verify it
qdo query -c my-db --sql "select status, count(*) from orders group by 1"
qdo assert -c my-db --sql "select count(*) from orders where status is null" --expect 0

# 5. Hand it off
qdo report table -c my-db --table orders -o orders-report.html
```

Need more detail while investigating? Use `inspect`, `preview`, `profile`,
`quality`, `values`, `dist`, `joins`, and `diff` as drill-down tools inside
that workflow.

All commands support `--format json` (or `csv`, `markdown`, `html`, `yaml`). Output goes to stdout; spinners go to stderr so piping is safe:

```bash
qdo context -c my-db -t orders -f json | jq '.columns[].name'
qdo catalog -c my-db -f json > schema.json
qdo profile -c my-db -t orders -f csv > stats.csv
```

## Commands

### Start Here — promoted workflow

```bash
qdo catalog   -c my-db                       # discover tables and row counts
qdo context   -c my-db -t orders              # schema + stats + sample values in one call
qdo metadata  init -c my-db -t orders         # create metadata YAML
qdo metadata  suggest -c my-db -t orders --apply  # capture deterministic additions
qdo query     -c my-db --sql "select ..."     # answer a question
qdo assert    -c my-db --sql "..." --expect 0 # verify an invariant
qdo report    table -c my-db -t orders        # single-file hand-off report
qdo bundle    export -c my-db -t orders -o bundle.zip  # portable knowledge bundle
```

### Investigate Deeper — specialist tools

```bash
qdo inspect   -c my-db -t orders              # column types, nullable, PK, row count
qdo preview   -c my-db -t orders -r 20        # see rows
qdo profile   -c my-db -t orders --top 10     # stats + top frequent values
qdo profile   -c my-db -t orders --quick      # fast: nulls + distinct only (auto for 50+ cols)
qdo profile   -c my-db -t orders --classify   # classify columns by category (implies --quick)
qdo dist      -c my-db -t orders -C amount    # histogram or value frequencies
qdo values    -c my-db -t orders -C status    # all distinct values for a column
qdo quality   -c my-db -t orders              # null rates, uniqueness, anomalies
qdo diff      -c my-db -t orders --target v2  # compare two table schemas
qdo joins     -c my-db -t orders              # suggest likely join keys
```

### Query — run and validate SQL

```bash
qdo catalog   -c my-db                                       # all tables and columns
qdo catalog   -c my-db --pattern order                       # filter tables/columns by name
qdo pivot     -c my-db -t orders -g region -a "sum(amount)"  # GROUP BY
qdo explain   -c my-db --sql "select ..."                    # query execution plan
qdo export    -c my-db -t orders -o out.csv                  # export to file
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
qdo config column-set save -c mydb -t orders -n default --columns "id,status,amount"
qdo config column-set list
qdo profile -c mydb -t orders --column-set default  # reuse saved selection
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
qdo snowflake lineage -c prod --object DB.SCHEMA.TABLE  # Snowflake GET_LINEAGE
qdo sql task -c prod -t my_table                        # task template
qdo sql procedure -c prod -t my_table                   # stored procedure template
```

### Interactive — TUI

```bash
qdo explore -c my-db -t orders               # terminal UI (requires querido[tui])
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
qdo context -c my-db -t orders                     # rich terminal output
qdo context -c my-db -t orders -f json             # machine-readable
qdo context -c my-db -t orders --sample-values 10  # more sample values
qdo context -c my-db -t orders --no-sample         # exact stats, no row sampling
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

## Sampling and accuracy

Commands that scan table data (`context`, `profile`, `quality`) automatically sample tables over 1M rows for speed. This is a deliberate trade-off: fast approximate results by default, exact results on request.

**What sampling affects:**
- Null counts and percentages (computed from the sample, not the full table)
- Distinct counts (approximate algorithms on DuckDB/Snowflake: `APPROX_COUNT_DISTINCT`)
- Min/max/mean/median/stddev (computed from the sample)
- Sample values for categorical columns

**What sampling does NOT affect:**
- Column names, types, nullable flags (from metadata, not scanned)
- Row counts (from `information_schema` on Snowflake, always exact)

**How to tell if results are sampled:**
- Rich (terminal) output shows `(sampled 100,000 rows)` in the header and a hint: `Sampled — use --no-sample for exact results (slower)`
- JSON output includes `"sampled": true`, `"sample_size": 100000`, and a `"sampling_note"` field explaining the trade-off

**How to get exact results:**

```bash
qdo profile -c my-db -t big_table --no-sample     # full scan, exact stats
qdo context -c my-db -t big_table --no-sample      # full scan, exact context
qdo quality -c my-db -t big_table --no-sample       # full scan, exact quality
qdo profile -c my-db -t big_table --exact           # also use exact COUNT(DISTINCT)
```

**Tuning the threshold:**

The auto-sample threshold (default 1M rows) can be adjusted via the `QDO_SAMPLE_THRESHOLD` environment variable:

```bash
export QDO_SAMPLE_THRESHOLD=5000000   # only sample tables over 5M rows
export QDO_SAMPLE_THRESHOLD=0         # always sample (use for testing)
```

## Wide tables (50+ columns)

Profiling tables with many columns can be slow. qdo has a tiered profiling system designed for wide tables:

```bash
# Quick mode: only null counts + distinct counts (auto-engages at 50+ columns)
qdo profile -c my-db -t wide_table --quick

# Classify columns into categories (constant, sparse, high cardinality, time, etc.)
qdo profile -c my-db -t wide_table --classify
qdo profile -c my-db -t wide_table --classify -f json   # machine-readable for agents

# Profile specific columns (full stats)
qdo profile -c my-db -t wide_table --columns "col1,col2,col3"

# Save a column set for reuse across commands
qdo config column-set save -c my-db -t wide_table -n default --columns "col1,col2,col3"
qdo profile -c my-db -t wide_table --column-set default

# Manage saved column sets
qdo config column-set list
qdo config column-set show -c my-db -t wide_table -n default
qdo config column-set delete -c my-db -t wide_table -n default
```

**How quick mode works:** At 50+ columns (configurable via `QDO_QUICK_THRESHOLD`), `profile` automatically switches to quick mode, computing only null counts, null percentages, and distinct counts. Use `--no-quick` to force full stats. Use `--classify` to see columns grouped by type (constant, sparse, high cardinality, time dimensions, measures, low cardinality).

**TUI workflow:** In `qdo explore`, press `p` on a wide table to see a column selector with checkboxes, grouped by classification. Select the columns you care about, optionally save the selection, then get full stats for just those columns.

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

Ready-made context files live in the `integrations/` directory. Copy the one that matches your agent harness:

| Harness | How to install |
|---------|----------------|
| **Claude Code** | Copy `integrations/skills/SKILL.md` to your project's `skills/querido/` directory, or paste the contents into your `CLAUDE.md` |
| **Continue.dev** | Copy `integrations/continue/qdo.md` to your project's `.continue/rules/` directory |

**Recommended agent workflow:**

```bash
# 1. Discover
qdo catalog -c my-db -f json

# 2. Understand
qdo context -c my-db -t orders -f json

# 3. Load or capture prior knowledge
qdo metadata show -c my-db -t orders -f json
qdo metadata suggest -c my-db -t orders --apply

# 4. Answer and verify
qdo query -c my-db --sql "..." -f json
qdo assert -c my-db --sql "..." --expect 0 -f json

# 5. Hand off
qdo report table -c my-db -t orders -o orders-report.html
```

The `context` command is the anchor for agent workflows: it returns everything
an LLM needs to write correct SQL for a table in one call, and metadata turns
that understanding into durable context for later runs and other teammates.

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
