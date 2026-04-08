---
layout: default
title: Home
---

# querido

> **querido** (Spanish): *dear*, *beloved*
>
> Also: **queri**-**do** — your data is dear to you, and you want to query it. `qdo` = query, do.

A CLI toolkit for common data analysis tasks against SQLite, DuckDB, Snowflake, and Parquet files.

## Documentation

- [CLI Reference](cli-reference.html) — full command listing with flags and examples
- [Cheatsheet](qdo-cheatsheet.html) — visual quick-reference card
- [GitHub Repository](https://github.com/curtisalexander/querido)

## Install

Pre-built wheels are available from [GitHub Releases](https://github.com/curtisalexander/querido/releases). Requires Python >= 3.12 and [uv](https://docs.astral.sh/uv/).

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

uv tool install 'querido[all]' \
  --find-links https://github.com/curtisalexander/querido/releases/expanded_assets/v0.1.0
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

All commands support `--format json` (or `csv`, `markdown`, `html`, `yaml`). Output goes to stdout; spinners go to stderr so piping is safe.

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
qdo query     -c my-db --sql "select ..."                    # ad-hoc SQL
qdo catalog   -c my-db                                       # all tables and columns
qdo pivot     -c my-db -t orders -g region -a "sum(amount)"  # GROUP BY
qdo explain   -c my-db --sql "select ..."                    # query execution plan
qdo assert    -c my-db --sql "..." --expect 0                # assert a condition (CI-friendly)
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
qdo cache sync  -c my-db
qdo completion show fish > ~/.config/fish/completions/qdo.fish
```

See the [CLI Reference](cli-reference.html) for the full command listing with all flags and options.

## Using qdo with a coding agent

qdo is designed to be useful at the keyboard for a human analyst, and equally useful as a tool for a coding agent writing SQL on your behalf.

```bash
export QDO_FORMAT=json     # all commands output JSON
qdo catalog -c my-db       # full schema as JSON
qdo context -c my-db -t orders  # everything an LLM needs to write correct SQL
qdo query -c my-db --sql "..." # query results as JSON
```

A ready-made context file lives at `skills/querido/SKILL.md` — copy it into your agent harness so it knows how to use qdo.
