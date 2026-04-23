---
name: querido
description: Use querido (qdo) to explore database schemas, profile data, enrich tables with metadata, and generate SQL. Use when working with SQLite, DuckDB, Snowflake, or Parquet files, when asked to write SQL against a local or named database, when asked to profile or summarize a table, or when the user mentions qdo.
compatibility: Requires qdo CLI (pip install querido). DuckDB support requires querido[duckdb]. Snowflake support requires querido[snowflake].
---

# Using querido (qdo)

qdo is an agent-first data exploration CLI. The product surface looks ordinary (`catalog`, `context`, `profile`, `query`). The asset is the **compounding loop** those commands form: metadata captured by one investigation (`values --write-metadata`, `metadata suggest --apply`) is auto-merged into the next `context` and checked by the next `quality` run. Every call makes the next one sharper. No LLMs inside qdo — you bring the brain; qdo brings the memory and the map.

Self-hosting eval: **42/45 (93%)** across haiku, sonnet, and opus on 15 tasks (re-run on every SKILL change; regressions are signal — the three current failures are all `model-mistake`, not `qdo-bug`).

Pass `-f json` on every invocation for machine-readable output — the envelope is `{command, data, next_steps, meta}` with deterministic `next_steps` hints that chain investigations. Canonical placement is right after `qdo` (`qdo -f json <cmd> ...`).

## Default agent workflow

Unless the user clearly asks for something else, use this path:

```bash
qdo -f json catalog -c <connection>                                  # discover candidate tables
qdo -f json context -c <connection> -t <table>                        # understand one table deeply
qdo -f json metadata show -c <connection> -t <table>                  # load existing shared knowledge
qdo -f json query -c <connection> --sql "select ..."                  # answer a concrete question
qdo -f json assert -c <connection> --sql "select ..." --expect ...    # verify an invariant when useful
qdo report table -c <connection> -t <table> -o report.html            # hand off a shareable artifact (file output)
```

Treat `catalog -> context -> metadata -> query/assert -> report/bundle` as the default path.

## Agent rules

- Pass `-f json` on every call unless you specifically want rich terminal output — the envelope gives you `next_steps` hints that shape the next call.
- Do not start with `qdo --help` or `qdo overview` for normal exploration tasks. The command surface is stable; pick from the workflow above.
- Prefer `qdo context` over stitching together `inspect` + `preview` + `profile` for first-pass understanding.
- Use `qdo query` only after `context` unless the user asks for a narrowly scoped SQL answer immediately.
- Use drill-down commands only when the default workflow leaves a specific gap.
- When the connection is a DuckDB file, run `qdo` commands sequentially against that file. Do not overlap multiple `qdo` processes on the same `.duckdb` database unless you explicitly need concurrent writes and have planned for locking.

**First time?** Pair a `qdo tutorial` run with this reference:

- `qdo tutorial explore` — 15-lesson guided tour on a National Parks sample DB. Covers the full core workflow (catalog → context → profile → joins → query) in ~20 minutes.
- `qdo tutorial agent` — 13 lessons focused on metadata + agent-assisted SQL. Run this before a real investigation to see the compounding loop end-to-end.

**For a new database, start here:**

```bash
qdo catalog -c <connection>          # all tables and columns
qdo context -c <connection> -t <table>   # full context for one table (use this first)
```

`context` returns schema + null rates + distinct counts + sample values for categoricals + min/max for numerics in one call. If metadata files exist (`.qdo/metadata/`), descriptions and valid values are merged in automatically. It is the most efficient starting point for understanding a table.

## Connection syntax

```bash
# Named connection (configured via qdo config add)
qdo catalog -c mydb

# File path — DuckDB, SQLite, or Parquet
qdo catalog -c /path/to/data.duckdb
qdo catalog -c ./warehouse.db
qdo catalog -c ./data.parquet
```

The `-c` flag accepts either a named connection or a direct file path.

## Promoted workflow

For most analyst and agent tasks, use this sequence:

```bash
# 1. Discover candidate tables
qdo catalog -c <connection>

# 2. Build context for one table
qdo context -c <connection> -t <table>

# 3. Load or capture shared understanding
qdo -f json metadata show -c <connection> -t <table>
qdo metadata init -c <connection> -t <table>
qdo metadata suggest -c <connection> -t <table> --apply

# 4. Answer a concrete question
qdo query -c <connection> --sql "select ..."

# 5. Verify or hand off
qdo assert -c <connection> --sql "select ..." --expect ...
qdo report table -c <connection> -t <table> -o report.html
qdo bundle export -c <connection> -t <table> -o bundle.zip
```

This is the main story qdo is optimized for: discover data, understand it, capture what you learned, answer the question, then share the result.

## Drill-down commands

Use these only when the promoted workflow leaves a specific unanswered question:

- `qdo joins` for likely foreign-key relationships.
- `qdo inspect` for PK / nullable / default details.
- `qdo preview` for example rows.
- `qdo profile` for focused numeric or multi-column statistics.
- `qdo quality` for anomaly-oriented review.
- `qdo values` for enumerating low-cardinality columns and writing `valid_values`.
- `qdo dist` for histograms or categorical distributions.
- `qdo pivot` for quick aggregations without writing SQL.
- `qdo diff` for schema comparison.

**`context` vs `profile` vs `quality`.**
`context` is the default first call. `profile` is for deeper statistical detail on selected columns. `quality` is for anomaly-oriented checks and invariant violations.

**`values` vs `dist`.** When asked for *the distinct values* of a column (especially for writing `valid_values` in metadata or listing an enum), reach for `qdo values` — it enumerates distinct values directly. Reach for `qdo dist` only when the user wants a *distribution*, *histogram*, or *frequency breakdown* — the shape of the data, not the list of values.

**`values --write-metadata` closes the compounding loop.** It enumerates a
column's distinct values *and* writes them into the metadata YAML as
`valid_values`. Next time `qdo context`/`qdo quality` runs, those values
surface automatically and `quality` will flag any row that violates the enum.
This is the single highest-leverage move for sharpening an agent's
understanding of a table.

## context — everything about a table in one call

`context` is the fastest way to understand a table. On DuckDB and Snowflake it
uses a single SQL scan to compute stats **and** fetch sample values via
`approx_top_k`. On SQLite it runs one profile scan plus sequential frequency
queries. Stored metadata is loaded from disk concurrently.

```bash
qdo context -c <connection> -t <table>
qdo -f json context -c <connection> -t <table>          # machine-readable
qdo context -c <connection> -t <table> --sample-values 10   # more samples
qdo context -c <connection> -t <table> --no-sample      # exact counts, no sampling
```

JSON output shape (trimmed):

```json
{
  "table": "orders",
  "dialect": "duckdb",
  "row_count": 50000,
  "table_description": "Customer orders",
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
      "null_pct": 1.2,
      "distinct_count": 12543,
      "min": 0.99,
      "max": 9999.0,
      "sample_values": null
    }
  ]
}
```

Use `context` as the primary tool call when you need to understand a table before writing SQL. It replaces separate calls to `inspect`, `preview`, and much of `profile` for most workflows.

## quality — detect data issues

`quality` is the command to reach for when the user asks about nulls, duplicates, anomalies, enum violations, or whether a table is *healthy*. It checks stored `valid_values` and flags rows that don't match, surfaces high null rates, and labels each column `ok` / `warn` / `fail`.

```bash
qdo -f json quality -c <connection> -t <table>
qdo -f json quality -c <connection> -t <table> --no-sample   # exact counts on large tables
qdo -f json quality -c <connection> -t <table> --write-metadata  # also tag likely_sparse
```

JSON output shape (trimmed):

```json
{
  "command": "quality",
  "data": {
    "table": "orders",
    "row_count": 50000,
    "sampled": true,
    "sample_size": 100000,
    "duplicate_rows": 0,
    "columns": [
      {
        "name": "status",
        "type": "VARCHAR",
        "null_count": 12,
        "null_pct": 0.02,
        "distinct_count": 4,
        "uniqueness_pct": 0.008,
        "status": "ok",
        "issues": [],
        "valid_values": ["pending", "shipped", "delivered", "cancelled"],
        "invalid_count": 0
      },
      {
        "name": "amount",
        "type": "DOUBLE",
        "null_count": 600,
        "null_pct": 1.2,
        "uniqueness_pct": 25.0,
        "status": "warn",
        "issues": ["null_rate_above_threshold"]
      }
    ]
  }
}
```

**When to pick `quality` over `context + values`:**

- The user asked about *health*, *issues*, *bad data*, *nulls*, *duplicates*, or *enum violations* — reach for `quality` first. It has a deterministic rubric agents can gate on (the `status` field + stable `issues[]` codes).
- The user asked *what values does this column take?* — use `values` (or `values --counts`).
- The user asked *what's in this table?* — use `context`.
- You want `quality` to auto-catch enum violations on later runs: run `values --write-metadata` (or `metadata suggest --apply`) first. `quality` then checks every row against the stored `valid_values` and populates `invalid_count`. This is the core of the compounding loop for data-quality work.

## JSON output for programmatic use

Pass `-f json` explicitly on every call you want to parse:

```bash
qdo -f json catalog -c mydb
qdo -f json context -c mydb -t orders
qdo -f json metadata show -c mydb -t orders
```

`-f/--format` is a **top-level** option. Canonical placement is right after
`qdo` (before the subcommand), as above. qdo also accepts `-f json` *after*
the subcommand (`qdo inspect -c mydb -f json`) — the entrypoint hoists it
automatically. Either works; prefer the canonical form for readability.

Errors go to stderr as structured JSON when `-f json` is set:
```json
{"error": true, "code": "TABLE_NOT_FOUND", "message": "...", "hint": "..."}
```

> **Env-var shortcut.** `export QDO_FORMAT=json` defaults every command to JSON so you can drop the flag. Supported, but explicit `-f json` per invocation is the canonical pattern in this doc — it keeps each example self-contained and copyable.

## Metadata workflow

Metadata files live at `.qdo/metadata/<connection>/<table>.yaml` and contain both machine-populated statistics and human-written business context. Rich metadata dramatically improves AI-generated SQL.

### Create and enrich metadata

```bash
# Preview what the metadata scaffold looks like (no file written)
qdo template -c <connection> -t <table> --sample-values 10

# Initialize the YAML file (machine fields auto-populated)
qdo metadata init -c <connection> -t <table>

# Open in $EDITOR to fill in human fields
qdo metadata edit -c <connection> -t <table>

# Read back the enriched metadata
qdo metadata show -c <connection> -t <table>

# Deterministically propose additions from scans
qdo metadata suggest -c <connection> -t <table>

# Check completeness across all documented tables
qdo metadata list -c <connection>

# Find stored tables / columns by description keyword (lexical, local)
qdo -f json metadata search -c <connection> "fulfillment" --limit 5

# Re-profile after data changes (preserves human fields)
qdo metadata refresh -c <connection> -t <table>
```

### Human fields to fill in

| Field | Level | Purpose |
|-------|-------|---------|
| `table_description` | table | What this table contains and its role |
| `data_owner` | table | Team or person responsible |
| `update_frequency` | table | How often data is refreshed |
| `notes` | table | Gotchas, quirks, caveats |
| `description` | column | What this column means in business terms |
| `valid_values` | column | List of allowed enum values |
| `pii` | column | `true` if column contains personal data |

### Using metadata as agent context

Export metadata as JSON and paste it into your prompt:

```bash
qdo -f json metadata show -c <connection> -t <table1>
qdo -f json metadata show -c <connection> -t <table2>
```

**Prompt template:**

```
You are a SQL expert. I'm working with a DuckDB database.

Table metadata:
[paste output of: qdo -f json metadata show -c <db> -t <table1>]
[paste output of: qdo -f json metadata show -c <db> -t <table2>]

Question: <your question>

Requirements:
- Use lowercase SQL keywords
- Handle nullable columns per null_pct in metadata
- Use only values from valid_values fields in WHERE/IN clauses
- Respect pii: true columns (do not expose in output unless asked)
```

The metadata tells the agent what schema alone cannot: valid enum values for filters, which columns are nullable, business meaning, ownership, and PII flags. Read it before writing nontrivial SQL.

## SQL generation

```bash
# SELECT scaffold — all columns, ready to trim
qdo sql select -c <connection> -t <table>

# CREATE TABLE DDL — portable to another database
qdo sql ddl -c <connection> -t <table>

# INSERT template with named placeholders
qdo sql insert -c <connection> -t <table>

# Scratch pad — TEMP TABLE + sample INSERTs from real data
qdo sql scratch -c <connection> -t <table>
```

## Export

```bash
# CSV to stdout — pipe to file or another tool
qdo -f csv preview -c <connection> -t <table> -r 100

# JSON lines — one object per row
qdo -f jsonl query -c <connection> --sql "select ..."

# Export command uses its own -e/--export-format for file format
qdo export -c <connection> -t <table> -e csv
```

## Sampling and accuracy

Commands that scan table data (`context`, `profile`, `quality`) automatically
sample tables over 1M rows for speed. **When results are sampled, the JSON
output includes `"sampled": true` and a `"sampling_note"` field.** Check these
fields before treating statistics as exact.

- Null percentages, distinct counts, and min/max are approximate when sampled
- Row counts are always exact (from database metadata, not scanned)
- Use `--no-sample` for exact results: `qdo profile -c <conn> -t <table> --no-sample`
- Use `--exact` to disable approximate count distinct: `qdo quality -c <conn> -t <table> --exact`
- The threshold is configurable: `export QDO_SAMPLE_THRESHOLD=5000000`

## Advanced / specialized commands

Not in the common workflow, but worth knowing about:

- **`qdo assert -c <conn> --sql "…" --expect <n>`** — value assertion for CI
  or end-of-workflow invariants. Single numeric SQL result; expectations via
  `--expect`, `--expect-gt`, `--expect-lte`, etc. Exits non-zero on failure.
  Use as the last step of a workflow to gate publishes or detect drift.
- **`qdo diff -c <conn> -t <left> --target <right>`** — schema diff between
  two tables (added / removed / type-changed columns). `--target-connection`
  for cross-database comparison (staging vs prod).
- **`qdo explain -c <conn> --sql "…"`** — database-native EXPLAIN plan with
  a `-f json` envelope. DuckDB surfaces `EXPLAIN ANALYZE` suggestions; use
  this when a profile / query feels slower than it should.
- **`qdo view-def -c <conn> --view <name>`** — fetch the SQL definition of
  a view. Works on DuckDB, SQLite (via `sqlite_master`), and Snowflake
  (`information_schema.views`).
- **`qdo snowflake semantic -c <conn> …`** — emit a Cortex Analyst semantic
  model YAML from stored metadata. Snowflake-only.
- **`qdo snowflake lineage -c <conn> -t <table>`** — upstream/downstream
  trace via Snowflake `GET_LINEAGE`. Snowflake-only.

## Gotchas

Behavior an agent needs to know so it doesn't write broken SQL or pick the wrong path:

- **Table names are case-insensitive** — qdo normalizes them internally; use whatever case feels natural.
- **Parquet files** — pass the file path directly as the connection: `-c ./data.parquet`. No separate config step needed.
- **Snowflake** — requires a named connection set up via `qdo config add`. Use `qdo snowflake` for Cortex Analyst semantic model generation.
- **pivot aggregations** — the `-a` argument is a SQL aggregate expression: `"count(*)"`, `"avg(price)"`, `"sum(revenue)"`. Quote it to prevent shell interpretation.
- **Wide tables auto-engage quick mode at 50+ columns** — only null counts + distinct counts are computed. Use `--classify` for a category breakdown, `--column-set` to reuse a saved selection, `--no-quick` to force full stats. If exploring interactively, `qdo explore` opens quick triage first when you press `p` on a wide table.
- **Metadata merge preserves human fields** — scans that `--write-metadata` never overwrite fields stored with `confidence: 1.0`. Pass `--force` only when the human value is actually stale.

Operator gotchas — setup / environment behavior, not needed for day-to-day query work:

- **Metadata location** — files go to `.qdo/metadata/<connection-dir>/<table>.yaml` relative to the working directory. For `-c mydb` (named) the dir is the connection name; for `-c ./data.duckdb` (file path) the dir is the file *stem*. Override the root with `QDO_METADATA_DIR`.
- **Metadata portability** — a local YAML's `connection:` field stores whatever was passed to `-c` (possibly an absolute path). Don't rely on it across machines. The portability boundary is `qdo bundle export`: bundles match tables by a `schema_fingerprint` (hash of columns+types) and import cleanly regardless of local paths.
- **`metadata refresh` vs `init`** — `init` creates a new file and errors if one exists; `refresh` updates machine fields on an existing file. Use `init --force` to overwrite.
- **Wide-table threshold is configurable** — `export QDO_QUICK_THRESHOLD=100` raises the bar for auto-engaging quick mode. Set to 0 to always engage; very large to always skip.

## Workflows — author, run, share

A **workflow** is a YAML file that composes `qdo` commands into a parameterized, repeatable investigation (think: "run catalog → context → quality against this table, expose a few fields"). Use workflows when the same 3+ step pattern repeats against different tables or connections.

```bash
qdo workflow list                   # bundled + user + project workflows
qdo workflow spec                   # JSON Schema (authoritative contract)
qdo workflow spec --examples        # bundled example YAMLs
qdo workflow show <name>            # print the YAML
qdo workflow lint <name-or-path>    # structured issues with fix hints
qdo workflow run <name> key=value key=value
```

**Canonical invocation is `qdo workflow run <name>`.** There is no top-level `qdo <workflow-name>` alias.

**Authoring loop** (investigate interactively, then codify):

```bash
QDO_SESSION=scratch qdo catalog -c mydb
QDO_SESSION=scratch qdo context -c mydb -t orders
QDO_SESSION=scratch qdo quality -c mydb -t orders
qdo workflow from-session scratch --name orders-summary \
  -o .qdo/workflows/orders-summary.yaml
qdo workflow lint .qdo/workflows/orders-summary.yaml
qdo workflow run orders-summary connection=mydb table=orders
```

Full guides:
- **[WORKFLOW_AUTHORING.md](./WORKFLOW_AUTHORING.md)** — grammar, lint-error catalog, patterns, anti-patterns.
- **[WORKFLOW_EXAMPLES.md](./WORKFLOW_EXAMPLES.md)** — annotated walkthrough of the bundled examples (table-summary, schema-compare, column-deep-dive, wide-table-triage, table-handoff, feature-target-exploration).

## Discover all commands

```bash
qdo --help
qdo <command> --help
qdo -f json overview         # machine-readable command reference
```
