# querido

[![CI](https://github.com/curtisalexander/querido/actions/workflows/ci.yml/badge.svg)](https://github.com/curtisalexander/querido/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

> **querido** (Spanish): *dear*, *beloved*. `qdo` = query, do.

qdo is the persistent-memory layer for data exploration: a deterministic CLI
that turns one-off investigation into reusable knowledge for you, your team,
and your coding agent.

## Why qdo

Most tools help you query data. qdo helps you **accumulate understanding** of
data, so each investigation starts with what the last one learned.

```text
discover ─► understand ─► capture ─► answer ─► hand off
catalog     context       metadata    query     report / bundle
                          values        ▲
                            │           │
                            └── feeds future context and quality ──┘
```

A `values --write-metadata` run can record the actual values in an undocumented
status column. The next `context` shows those values, the next `quality` checks
them, and a `bundle` can carry that knowledge to another project. The files are
plain YAML; every automated write is deterministic, provenance-tracked, and
reversible. No LLM runs inside qdo—the agent brings the brain; qdo brings the
memory and the map.

qdo is built for **un-modeled data**: extracts, replicas, vendor drops, scratch
SQLite or DuckDB files, and warehouse corners that have not been curated yet.
See [What sets qdo apart](./DIFFERENTIATION.md) for the product boundaries and
the directions qdo deliberately does not pursue.

## Install only what you use

qdo requires Python 3.12 or newer. The package is **`querido`** and the command
is **`qdo`**; do not install the unrelated `qdo` package from PyPI.

| What you use | Install |
|---|---|
| SQLite | `uv tool install querido` |
| DuckDB or Parquet | `uv tool install 'querido[duckdb]'` |
| Snowflake | `uv tool install 'querido[snowflake]'` |
| Interactive TUI | `uv tool install 'querido[tui]'` |
| Everything | `uv tool install 'querido[all]'` |

The same extras work with pip, for example `pip install 'querido[duckdb]'`.
Use `uvx --from querido qdo --help` for a one-off run. SQLite is the only
always-available backend; optional integrations are imported only when used.

> **Release status:** `0.2.0` is prepared but not yet published to PyPI. Until
> the first release is tagged, install from a checkout with `uv tool install .`
> or run `uv sync && uv run qdo --help`. See [Releasing](./RELEASING.md).

## Start with one table

No configuration is needed for SQLite: pass the file directly. Replace
`./data.db`, `orders`, and `status` with values from your database.

```bash
# 1. Discover
qdo catalog -c ./data.db

# 2. Understand
qdo context -c ./data.db -t orders

# 3. Capture one concrete fact
qdo values -c ./data.db -t orders -C status --write-metadata

# 4. See that fact used, now and later
qdo quality -c ./data.db -t orders
qdo context -c ./data.db -t orders

# 5. Answer a question
qdo query -c ./data.db --sql "select status, count(*) from orders group by 1"
```

`--write-metadata` writes under `.qdo/metadata/`. qdo never overwrites
human-authored fields automatically, and `qdo metadata undo` previews or
reverts qdo-managed changes.

Already want a guided example? Install the DuckDB extra and run
`qdo tutorial explore`. It walks through the compounding loop with included
National Parks data.

## Use the core, reveal more when needed

The supported core is deliberately small:

| Need | Command |
|---|---|
| Find relevant tables | `qdo catalog` |
| Understand one table | `qdo context` |
| Capture and read durable knowledge | `qdo metadata` |
| Answer a question | `qdo query` |
| Verify an invariant | `qdo assert` |
| Check stored constraints | `qdo quality` |
| Create a human hand-off | `qdo report` |
| Share portable knowledge | `qdo bundle` |

When the core does not answer the question, drill down with `preview`,
`profile`, `values`, `dist`, `freshness`, `joins`, `diff`, `pivot`, `explain`,
or `export`. Snowflake-specific commands, the TUI, sessions, SQL generation,
and experimental YAML workflows remain available without crowding the first
path.

Run `qdo --help` for the grouped map, `qdo <command> --help` for exact options,
or read the complete [CLI reference](./docs/cli-reference.md).

## Humans and agents use the same interface

Scanning commands emit a stable `{command, data, next_steps, meta}` envelope
with `-f json`. Results go to stdout and progress goes to stderr, so piping is
safe:

```bash
qdo context -c ./data.db -t orders -f json | jq '.data.columns[].name'
qdo catalog -c ./data.db -f json > catalog.json
```

Coding-agent instructions ship inside the installed package; a repository
checkout is not required. Install them from the project where the agent works:

```bash
# Claude Code's project discovery path
qdo agent install skill --path .claude/skills/querido

# Continue.dev's conventional project path
qdo agent install continue
```

`qdo agent list` shows every packaged target and `qdo agent show skill` prints
instructions without writing files. The canonical source files are
[the agent skill](./integrations/skills/SKILL.md) and
[the Continue rule](./integrations/continue/qdo.md).

## Go deeper only when you need to

- **Learn interactively:** `qdo tutorial explore` or `qdo tutorial agent`
- **Configure named connections:** [CLI reference — Connection setup](./docs/cli-reference.md#connection-setup)
- **Understand output, sampling, sessions, and exit codes:** [CLI reference](./docs/cli-reference.md)
- **See generated artifacts:** [examples](./docs/examples/README.md)
- **Automate a repeated investigation:** [workflow authoring](./integrations/skills/WORKFLOW_AUTHORING.md) (experimental)
- **Understand the implementation:** [architecture](./ARCHITECTURE.md)
- **Contribute:** [contributor guide](./AGENTS.md)
- **See current committed work:** [plan](./PLAN.md)

qdo stores sessions as JSONL, metadata as YAML, bundles as zip archives, and
workflows as YAML. There is no daemon or hosted dependency: the knowledge stays
portable, diffable, and yours.
