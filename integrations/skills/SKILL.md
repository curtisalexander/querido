---
name: querido
description: Use querido (qdo) to explore database schemas, profile data, enrich tables with metadata, and generate SQL. Use when working with SQLite, DuckDB, Snowflake, or Parquet files, when asked to write SQL against a local or named database, when asked to profile or summarize a table, or when the user mentions qdo.
compatibility: Requires qdo CLI (pip install querido). DuckDB support requires querido[duckdb]. Snowflake support requires querido[snowflake].
---

# Using querido (qdo)

qdo is a CLI toolkit for data exploration and SQL generation. It speaks to SQLite, DuckDB, Snowflake, and Parquet files through a uniform interface. Use `--format json` (or `export QDO_FORMAT=json`) to get machine-readable output for every command.

## Quick Setup

Run this once per session (or add to your shell profile):

```bash
export QDO_FORMAT=json   # all commands output JSON — no --format flag on every call
```

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

## Quick exploration workflow

For any new database or table, follow this sequence:

```bash
# 1. See all tables, column counts, and row counts
qdo catalog -c <connection>

# 2. Discover likely join keys across all tables (before you pick one)
qdo joins -c <connection> -t <table>

# 3. Full context for a table — schema + stats + sample values in one call
qdo context -c <connection> -t <table>

# 4. Drill into structure (if you need PK/nullable/default details)
qdo inspect -c <connection> -t <table>

# 5. See sample rows
qdo preview -c <connection> -t <table> -r 10

# 6. Statistical summary — min/max/mean/null_count/distinct_count
qdo profile -c <connection> -t <table>

# 6b. Wide tables (50+ cols): classify first, then profile a subset
qdo profile -c <connection> -t <table> --classify          # categorize columns
qdo profile -c <connection> -t <table> --columns <cols>    # full stats on selected
qdo config column-set save -c <conn> -t <table> -n default --columns "<cols>"  # persist
qdo profile -c <connection> -t <table> --column-set default  # reuse

# 7. Top values for specific categorical columns
qdo profile -c <connection> -t <table> --columns <col1>,<col2> --top 5

# 8. Full value list with counts for an enum-like column — write to metadata
qdo values -c <connection> -t <table> -C <column> --write-metadata

# 9. Histogram for a numeric column
qdo dist -c <connection> -t <table> -C <column>

# 10. Data quality report — null rates, uniqueness, invariant violations
qdo quality -c <connection> -t <table>

# 11. Run ad-hoc SQL
qdo query -c <connection> --sql "select ..."

# 12. GROUP BY aggregation without writing SQL
qdo pivot -c <connection> -t <table> -g <group_col> -a "sum(<value_col>)"
```

**`profile` vs `quality`.** Both scan a table but surface different signals:
`profile` is statistical (min/max/mean/null_pct/distinct_count — use it when
you want *distributions*). `quality` is invariant-oriented (elevates columns
whose null rate, uniqueness, or stored `valid_values` enum is violated — use
it when you want *what's wrong*). They're complementary; run both on a new
table.

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
qdo context -c <connection> -t <table> -f json          # machine-readable
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

Use `context` as the primary tool call when you need to understand a table
before writing SQL. It replaces separate calls to `inspect`, `profile`, and
`values` for most workflows.

## JSON output for programmatic use

```bash
# Set once, affects all commands
export QDO_FORMAT=json

# Or per-command
qdo --format json catalog -c mydb
qdo --format json inspect -c mydb -t orders
qdo --format json profile -c mydb -t events
```

Errors go to stderr as structured JSON when `--format json` is set:
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
qdo metadata show -c <connection> -t <table1> -f json
qdo metadata show -c <connection> -t <table2> -f json
```

**Prompt template:**

```
You are a SQL expert. I'm working with a DuckDB database.

Table metadata:
[paste output of: qdo metadata show -c <db> -t <table1> -f json]
[paste output of: qdo metadata show -c <db> -t <table2> -f json]

Question: <your question>

Requirements:
- Use lowercase SQL keywords
- Handle nullable columns per null_pct in metadata
- Use only values from valid_values fields in WHERE/IN clauses
- Respect pii: true columns (do not expose in output unless asked)
```

The metadata tells the agent what schema alone cannot: valid enum values for filters, which columns are nullable (use LEFT JOIN or IS NOT NULL guards), date columns that need EXTRACT for year comparisons, and PII columns to avoid.

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

# Export command with explicit format flag
qdo export -c <connection> -t <table> --format csv
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
- **Wide tables** — `--quick` auto-engages at 50+ columns (only null counts + distinct counts). Use `--classify` for a category breakdown. Use `--column-set` to reuse a saved selection. Configurable threshold: `export QDO_QUICK_THRESHOLD=100`.

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
