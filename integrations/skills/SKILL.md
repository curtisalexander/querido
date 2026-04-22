---
name: querido
description: Use querido (qdo) to explore database schemas, profile data, enrich tables with metadata, and generate SQL. Use when working with SQLite, DuckDB, Snowflake, or Parquet files, when asked to write SQL against a local or named database, when asked to profile or summarize a table, or when the user mentions qdo.
compatibility: Requires qdo CLI (pip install querido). DuckDB support requires querido[duckdb]. Snowflake support requires querido[snowflake].
---

# Using querido (qdo)

qdo is an agent-first data exploration CLI that turns one-off investigation into reusable team knowledge. Use `--format json` (or `export QDO_FORMAT=json`) to get machine-readable output for the main scan/query commands and the management/reference commands that support structured output.

## Quick Setup

Run this once per session (or add to your shell profile):

```bash
export QDO_FORMAT=json   # all commands output JSON — no --format flag on every call
```

## Default agent workflow

Unless the user clearly asks for something else, use this path:

```bash
qdo catalog -c <connection>                 # discover candidate tables
qdo context -c <connection> -t <table>      # understand one table deeply
qdo metadata show -c <connection> -t <table> -f json
                                             # load existing shared knowledge
qdo query -c <connection> --sql "select ..."
                                             # answer a concrete question
qdo assert -c <connection> --sql "select ..." --expect ...
                                             # verify an invariant when useful
qdo report table -c <connection> -t <table> -o report.html
                                             # hand off a shareable artifact
```

Treat `catalog -> context -> metadata -> query/assert -> report/bundle` as the default path.

## Agent rules

- Do not start with `qdo --help` or `qdo overview` for normal exploration tasks. The command surface is stable; pick from the workflow above.
- Prefer `qdo context` over stitching together `inspect` + `preview` + `profile` for first-pass understanding.
- Use `qdo query` only after `context` unless the user asks for a narrowly scoped SQL answer immediately.
- Use drill-down commands only when the default workflow leaves a specific gap.
- Prefer `-f json` when you need to inspect output programmatically.
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
qdo metadata show -c <connection> -t <table> -f json
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

## JSON output for programmatic use

```bash
# Set once, affects all commands
export QDO_FORMAT=json

# Or per-command
qdo -f json catalog -c mydb
qdo -f json context -c mydb -t orders
qdo -f json metadata show -c mydb -t orders
```

`-f/--format` is a **top-level** option. Canonical placement is right after
`qdo` (before the subcommand), as in the examples above. qdo also accepts
`-f json` *after* the subcommand (`qdo inspect -c mydb -f json`) — the
entrypoint hoists it automatically. Either works; prefer the canonical form
for readability.

Errors go to stderr as structured JSON when `-f json` is set:
```json
{"error": true, "code": "TABLE_NOT_FOUND", "message": "...", "hint": "..."}
```

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
qdo --format csv preview -c <connection> -t <table> -r 100

# JSON lines — one object per row
qdo --format jsonl query -c <connection> --sql "select ..."

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

- **Table names are case-insensitive** — qdo normalizes them internally; use whatever case feels natural.
- **Parquet files** — pass the file path directly as the connection: `-c ./data.parquet`. No separate config step needed.
- **Snowflake** — requires a named connection set up via `qdo config add`. Use `qdo snowflake` for Cortex Analyst semantic model generation.
- **Metadata location** — files go to `.qdo/metadata/<connection-dir>/<table>.yaml` relative to your working directory. When `--connection` is a named connection (e.g. `-c mydb`), `<connection-dir>` is the connection name (`.qdo/metadata/mydb/`). When `--connection` is a file path (e.g. `-c ./data/test.duckdb`), `<connection-dir>` is the file *stem* — the filename without extension (`.qdo/metadata/test/`). Override the root with the `QDO_METADATA_DIR` environment variable.
- **Portability of metadata** — a local metadata YAML's `connection:` field stores whatever was passed to `-c` (possibly an absolute path). Don't rely on that field for cross-machine work. The portability boundary is `qdo bundle export` — bundles match tables by a `schema_fingerprint` (hash of columns+types), so an export from one machine imports cleanly onto another regardless of local paths.
- **metadata refresh vs init** — `init` creates a new file and will error if one already exists. `refresh` updates machine fields in an existing file. Use `init --force` to overwrite.
- **pivot aggregations** — the `-a` argument is a SQL aggregate expression: `"count(*)"`, `"avg(price)"`, `"sum(revenue)"`. Quote it to prevent shell interpretation.
- **Wide tables** — `--quick` auto-engages at 50+ columns (only null counts + distinct counts). Use `--classify` for a category breakdown and `--column-set` to reuse a saved selection. If you're exploring interactively, `qdo explore` now opens quick triage first when you press `p` on a wide table, with recommended columns pre-selected before full profiling. Configurable threshold: `export QDO_QUICK_THRESHOLD=100`.

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
qdo --format json overview   # machine-readable command reference
```
