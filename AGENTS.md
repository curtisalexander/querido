# Agent Guide for qdo

This file helps coding agents get up to speed quickly on the qdo project.

## What is qdo?

A CLI data analysis toolkit. Users run commands like `qdo inspect`, `qdo preview`, `qdo profile` against database tables (SQLite, DuckDB, Snowflake) and Parquet files, and get formatted output in the terminal.

## Quick Start

```bash
# Install dependencies (dev includes duckdb for tests)
uv sync

# Run the CLI
uv run qdo --help

# Run tests
uv run pytest

# Lint, format, and type check
uv run ruff check .
uv run ruff format .
uv run ty check
```

## Critical Rules

### Pay for What You Use

This is the project's core engineering principle. Users should never pay (in install size, startup time, or runtime cost) for features they don't use.

**Install time** — Database backends beyond SQLite are optional extras:
```bash
uv pip install querido               # SQLite only
uv pip install 'querido[duckdb]'     # + DuckDB
uv pip install 'querido[snowflake]'  # + Snowflake
```

The factory (`connectors/factory.py`) catches `ImportError` and tells users how to install missing backends. When adding a new backend, always make it opt-in via `[project.optional-dependencies]` in `pyproject.toml`.

**Runtime / Lazy Imports** — All heavy imports must happen inside functions, not at module level. This keeps CLI startup fast. The only top-level imports allowed are: `typer`, stdlib modules, and type-checking-only imports behind `if TYPE_CHECKING`.

```python
# CORRECT
def my_command():
    from rich.table import Table  # imported only when this command runs
    ...

# WRONG
from rich.table import Table  # slows down every command, even --help
```

This applies to everything that isn't `typer` or stdlib: database drivers, Rich, Jinja2, platformdirs, tomli-w.

### SQL Templates
All database queries must use `.sql` template files in `src/querido/sql/templates/`. Never hardcode SQL strings in Python code (exception: connector `get_columns` methods, which use database-specific mechanisms like `PRAGMA`). Templates use Jinja2 syntax. See `ARCHITECTURE.md` for details.

### Connector Protocol
All database connectors implement the `Connector` protocol in `connectors/base.py`. Connectors are context managers — always use `with create_connector(config) as conn:` in CLI commands. When adding a new database backend, implement the full protocol including `__enter__`/`__exit__`.

Snowflake and DuckDB connectors also provide `execute_arrow()` which returns a PyArrow Table for zero-copy data handling. Use `connectors/arrow_util.py:execute_arrow_or_dicts()` to opportunistically take the Arrow path with automatic fallback. Connectors also expose `supports_concurrent_queries` (True for Snowflake) to enable parallel query execution in operations like frequency profiling.

### Input Validation
Table names are validated at the CLI boundary using `validate_table_name()` from `connectors/base.py`. This prevents SQL injection in templates and f-string interpolations. Always call this before passing a table name to any query.

## Project Layout

Read `ARCHITECTURE.md` for the full structure. Key locations:

- `src/querido/cli/` — CLI commands (one file per subcommand, plus `_pipeline.py`, `_context.py`, `_errors.py`, `_options.py`, `_progress.py`, `_validation.py` for shared helpers)
- `src/querido/connectors/` — Database connectors (one file per backend; DuckDB also handles Parquet)
- `src/querido/sql/templates/` — SQL templates (organized by command, then dialect)
- `src/querido/output/` — Output formatting (Rich tables, HTML pages, Markdown, JSON, CSV)
- `src/querido/config.py` — TOML config loading, connection resolution (incl. Parquet detection)
- `tests/integration/` — Integration tests (SQLite + DuckDB)

## Commands

### inspect — table structure
```bash
qdo inspect -c <connection> -t <table> [-v]
```
Shows: column names, types, nullable, default, primary key, row count. Use `-v` for comments.

### preview — see rows
```bash
qdo preview -c <connection> -t <table> [-r <rows>]
```
Default 20 rows. Use `-r` to change.

### profile — data profiling
```bash
qdo profile -c <connection> -t <table> [--columns col1,col2] [--sample N] [--no-sample] [--top N]
qdo profile -c <connection> -t <table> --quick          # fast: nulls + distinct only
qdo profile -c <connection> -t <table> --classify       # classify columns by category
qdo profile -c <connection> -t <table> --column-set default  # use saved column set
```
Numeric: min, max, mean, median, stddev, null count/%, distinct. String: min/max length, null count/%, distinct. Auto-samples at >1M rows (100k sample). `--top N` shows most frequent values.

**Wide tables (50+ columns):** `--quick` auto-engages at 50+ columns, computing only null counts and distinct counts. Use `--classify` (implies `--quick`) to group columns into categories: constant, sparse, high_cardinality, time, measure, low_cardinality, other. Use `--column-set` to reuse a saved set of columns across commands.

### dist — column distribution
```bash
qdo dist -c <connection> -t <table> -C <column> [--buckets N] [--top N]
```
Numeric: histogram with N buckets (default 20). Categorical: top N values by frequency (default 20).

### template — documentation template
```bash
qdo template -c <connection> -t <table> [--sample-values N]
```
Generates a documentation template with auto-populated metadata (column name, type, nullable, distinct count, min/max, sample values) and placeholder fields for business definitions, data owner, and notes. Default 3 sample values per column; use `--sample-values 0` to skip.

### explore — interactive TUI
```bash
qdo explore -c <connection> -t <table> [-r <rows>]
```
Interactive terminal UI for data exploration. Requires `uv pip install 'querido[tui]'`.
Key bindings: `q` quit, `?` help, `i` inspect metadata, `p` profile, `d` distribution,
`m` toggle sidebar, `/` filter, `Escape` clear, `r` refresh. Click column headers to sort.
The main grid uses semantic highlighting so PKs, sorted columns, null-heavy columns,
and null cells are obvious at a glance. On wide tables, `p` opens a quick-triage flow
first so you can select the most useful columns before running a full profile.

### catalog — full schema overview (also searches)
```bash
qdo catalog -c <connection>
qdo catalog -c <connection> --pattern users   # filter by table/column name
qdo catalog -c <connection> --tables-only     # skip columns and row counts
qdo catalog -c <connection> --enrich          # merge stored metadata descriptions
```
Cache-first by default; use `--live` to bypass. `--pattern` does a case-insensitive substring
match across both table and column names.

### sql — generate SQL statements
```bash
qdo sql select -c <conn> -t <table>     # SELECT with all columns
qdo sql insert -c <conn> -t <table>     # INSERT with placeholders
qdo sql ddl -c <conn> -t <table>        # CREATE TABLE DDL
qdo sql scratch -c <conn> -t <table>    # TEMP TABLE + sample INSERTs
qdo sql task -c <conn> -t <table>       # Snowflake task template
qdo sql udf -c <conn> -t <table>        # UDF template
qdo sql procedure -c <conn> -t <table>  # Stored procedure (Snowflake)
```

### snowflake — Snowflake-specific commands
```bash
qdo snowflake semantic -c <conn> -t <table>        # Generate Cortex Analyst semantic model YAML
qdo snowflake semantic -c <conn> -t <table> -o out.yaml  # Write to file
qdo snowflake lineage --object <fqn> -c <conn>     # Trace via Snowflake GET_LINEAGE
qdo snowflake lineage --object <fqn> -c <conn> -d upstream --depth 3  # upstream, depth 3
```

### config — manage connections and column sets
```bash
qdo config add --name mydb --type sqlite --path ./data.db
qdo config list
qdo config column-set save -c CONN -t TABLE -n NAME --columns "col1,col2"
qdo config column-set list [-c CONN] [-t TABLE]
qdo config column-set show -c CONN -t TABLE -n NAME
qdo config column-set delete -c CONN -t TABLE -n NAME
```

### Global flags
- `--show-sql` — print rendered SQL to stderr with syntax highlighting
- `--format {rich,markdown,json,csv,html,yaml}` / `-f` — output format (default: rich)
- `--version` / `-V` — show version

### Connection resolution
`-c` accepts a named connection from `connections.toml` or a file path. Extension determines type: `.duckdb`/`.ddb` → DuckDB, `.parquet` → Parquet (via DuckDB), else → SQLite. Override with `--db-type`.

## Using qdo as an Agent Tool

If you are a coding agent using qdo to analyze data (rather than developing qdo itself), this section describes the recommended workflow and output formats.

### Agent mode — set once, prefer JSON everywhere

Set `QDO_FORMAT=json` in your environment to make structured output the default where a command supports it:

```bash
export QDO_FORMAT=json
```

Priority: explicit `--format` flag > `QDO_FORMAT` env var > `rich` (default).

Most scan/query commands, plus many management/reference commands, support `--format json` (or `-f json`) and emit JSON to stdout. Artifact-oriented commands such as `report table` still keep their file-writing behavior. Errors go to stderr.

### Recommended exploration workflow

The canonical agent workflow is: **catalog -> context -> metadata -> query/assert -> report/bundle**.
Start broad, build context, then answer and hand off.

1. **Get full schema** — see everything in one call:
   ```bash
   qdo catalog -c ./my.db                    # all tables, columns, row counts
   qdo catalog -c ./my.db --tables-only      # just table names
   qdo catalog -c ./my.db --pattern orders   # filter by name
   ```
   Returns: `{"table_count", "tables": [{"name", "type", "row_count", "columns": [...]}]}`

3. **Build context** — understand a table in one call:
   ```bash
   qdo context -c ./my.db -t orders
   ```
   Returns: `{"table", "row_count", "columns": [{"name", "type", "null_pct", "distinct_count", "sample_values", ...}]}`

4. **Load or capture shared knowledge** — read or create metadata:
   ```bash
   qdo metadata show -c ./my.db -t orders -f json
   qdo metadata init -c ./my.db -t orders
   qdo metadata suggest -c ./my.db -t orders --apply
   ```

5. **Answer and verify** — run SQL and check an invariant:
   ```bash
   qdo query -c ./my.db --sql "select region, sum(amount) from orders group by region"
   qdo assert -c ./my.db --sql "select count(*) from orders where amount < 0" --expect 0
   ```
6. **Hand off the result** — render a report or export a bundle:
    ```bash
    qdo report table -c ./my.db -t orders -o orders-report.html
    qdo bundle export -c ./my.db -t orders -o orders-bundle.zip
    ```

Use drill-down commands such as `inspect`, `preview`, `profile`, `quality`, `values`, `dist`, `joins`, `diff`, and `pivot` when this promoted path leaves a specific gap.

### Metadata workflow — enriched context for intelligent queries

The metadata system lets you create, store, and read back enriched table
documentation. This gives an agent business context (descriptions, owners,
PII flags, valid values) beyond what the raw schema provides.

**Setup (one-time per table):**
```bash
# 1. Generate a metadata template with auto-populated stats
qdo metadata init -c mydb -t orders

# 2. The analyst fills in human fields in the YAML file:
#    .qdo/metadata/mydb/orders.yaml
#    - table_description, data_owner, update_frequency, notes
#    - per-column: description, pii flag, valid_values

# 3. Optionally open in editor:
qdo metadata edit -c mydb -t orders
```

**Agent reads context before writing queries:**
```bash
# Get enriched metadata (schema + business context) as JSON
qdo metadata show -c mydb -t orders -f json

# List all tables with metadata and completeness scores
qdo metadata list -c mydb -f json
```

**Keep metadata fresh as schema evolves:**
```bash
# Re-run inspect/profile, update row counts and types
# Human-written fields (descriptions, owner, notes) are preserved
qdo metadata refresh -c mydb -t orders
```

**Storage:** Metadata lives in `.qdo/metadata/<connection>/<table>.yaml`
in the project directory. This is version-controlled with the repo, so
metadata travels with the codebase. Override the location with the
`QDO_METADATA_DIR` environment variable.

**YAML structure:**
```yaml
table: orders
connection: mydb
row_count: 50000
table_description: "Sales orders — one row per transaction"
data_owner: "Revenue team (revenue@company.com)"
update_frequency: "Hourly via CDC"
notes: |
  PII: customer_email
  Soft-deleted rows have status='cancelled'
columns:
  - name: id
    type: INTEGER
    description: "Auto-increment order ID"
    distinct_count: 50000
    null_count: 0
  - name: status
    type: TEXT
    description: "Order lifecycle status"
    valid_values: ["pending", "shipped", "cancelled"]
```

### Error handling

When `--format json` is active, errors are emitted as structured JSON to stderr:
```json
{"error": true, "code": "TABLE_NOT_FOUND", "message": "Table not found: ...", "hint": "Try: qdo catalog -c <connection> --pattern <name>"}
```

Representative error codes include `TABLE_NOT_FOUND`, `COLUMN_NOT_FOUND`, `SESSION_NOT_FOUND`, `METADATA_NOT_FOUND`, `COLUMN_SET_NOT_FOUND`, `CONNECTION_NOT_FOUND`, `CONNECTION_EXISTS`, `SQL_REQUIRED`, `SQL_FILE_NOT_FOUND`, `SNOWFLAKE_REQUIRED`, `VALIDATION_ERROR`, `DATABASE_ERROR`, `MISSING_DEPENDENCY`, and `PERMISSION_DENIED`. Treat the public contract as "stable code plus actionable `hint` / `try_next` when available", not as a promise that every validation edge case has its own named code.

Exit codes: `0` success, `1` error, `130` interrupted.

### Command discovery

To get a machine-readable description of all commands, options, and output shapes:
```bash
qdo -f json overview
```

### Caching for performance

For large databases (especially Snowflake), cache metadata locally to speed up search and validation:
```bash
qdo cache sync -c my-snowflake-conn                # cache for 24h (default)
qdo cache sync -c my-snowflake-conn --cache-ttl 0  # force re-sync
qdo -f json cache status                           # check cache freshness
```

## Authoring workflows

A **workflow** is a YAML file that composes `qdo` subcommands into a parameterized, repeatable investigation. Workflows are declarative — only `qdo` invocations, typed inputs, captured step outputs, and simple conditionals. No shell escape, no embedded Python.

Canonical invocation: `qdo workflow run <name> key=value key=value`. There is **no** top-level `qdo <workflow-name>` alias — that was considered and dropped for namespace-clarity reasons.

**Agent-authoring loop** (investigate → codify → lint → run):

```bash
QDO_SESSION=scratch qdo catalog -c mydb
QDO_SESSION=scratch qdo context -c mydb -t orders
QDO_SESSION=scratch qdo quality -c mydb -t orders
qdo workflow from-session scratch --name orders-summary \
  -o .qdo/workflows/orders-summary.yaml
qdo workflow lint .qdo/workflows/orders-summary.yaml
qdo workflow run orders-summary connection=mydb table=orders
```

Files:

- `src/querido/core/workflow/spec.py` — authoritative JSON Schema
- `src/querido/core/workflow/examples/` — bundled reference workflows
- `src/querido/core/workflow/{loader,lint,runner,from_session,expr}.py` — implementation
- `integrations/skills/WORKFLOW_AUTHORING.md` — full authoring guide (grammar, lint-error catalog, patterns, anti-patterns). This is the doc an agent should load when asked to write a workflow.

See `integrations/skills/WORKFLOW_AUTHORING.md` for the complete authoring guide.

## Interactive Tutorials

```bash
# Core exploration workflow (catalog → inspect → profile → query, 15 lessons)
qdo tutorial explore              # run all lessons
qdo tutorial explore --list       # list all 15 lessons
qdo tutorial explore --lesson 5   # start from a specific lesson
qdo tutorial explore --db FILE    # use your own database

# Metadata + AI-assisted SQL workflow (13 lessons)
qdo tutorial agent                # metadata enrichment and agent prompt pattern
qdo tutorial agent --list         # list all 13 lessons
qdo tutorial agent --lesson 4     # start from a specific lesson
```

Both tutorials generate a National Parks DuckDB database (parks, trails, wildlife sightings, visitor stats) in a temp directory and clean up on exit. Require `querido[duckdb]`.

The `agent` tutorial covers: `template` → `metadata init` → enriching human fields → `metadata show` → exporting JSON for agent context → the recommended prompt structure → a metadata-aware join query.

## Test Data

```bash
uv run python scripts/init_test_data.py   # creates data/test.db and data/test.duckdb
```

| Database | Tables | Rows |
|----------|--------|------|
| test.db (SQLite) | customers, products, orders, datatypes | 1000 / 1000 / 5000 / 100 |
| test.duckdb | customers, products, orders, datatypes | 1000 / 1000 / 5000 / 100 |

**customers**: customer_id, first_name, last_name, company, city, country, phone1, phone2, email, subscription_date, website

**products**: name, description, brand, category, price, currency, stock, ean, color, size, availability, internal_id

**orders**: customer_id, product_id, status, amount, region, order_date — 5000 rows linking customers and products, with intentional data-quality outliers (~0.8% malformed status values, ~2.5% null amounts, ~1.5% negative amounts) so demos of `qdo quality` and `qdo values --write-metadata` have something to flag

**datatypes**: mixed types for edge-case testing (blobs, JSON, nulls, negatives, large ints)

## Self-hosting evaluations

Three optional eval scripts live under `scripts/`. Two are Claude-backed; one
uses Codex. All are opt-in and intended for local runs after docs or command-surface
changes.

- **`eval_workflow_authoring.py`** — Phase 4.6. Feeds `WORKFLOW_AUTHORING.md` + `qdo workflow spec` + bundled examples to `claude -p`, asks the model to author three workflows it hasn't seen, and checks lint + run + shape assertions. Signals whether the authoring doc is pedagogically complete.

- **`eval_skill_files_claude.py`** — EV.Build for Claude Code. Feeds SKILL.md + AGENTS.md + WORKFLOW_EXAMPLES.md to `claude -p` and asks it to answer 15 realistic data-exploration questions across four categories aligned to the promoted workflow (`catalog -> context -> metadata -> query/assert -> report/bundle`). Each task has required-command / content-regex / preferred-command checks; some tasks also require multiple workflow steps to appear. Failures are categorized (qdo-bug / model-mistake / envelope-mismatch / timeout / auth-error). Supports Haiku / Sonnet / Opus; per-model pass gates (70 / 85 / 95 %). Per-run JSON results land in `scripts/eval_results/` (gitignored).

- **`eval_skill_files_codex.py`** — EV.Build for Codex. Runs the same task catalog and pass/fail logic through `codex exec` so the benchmark corpus stays comparable across agents. Produces the same JSON result shape under `scripts/eval_results/`.

Run them locally after doc or implementation changes; failures that cluster in a category point at specific docs to tighten.

## Dependency Management

- **uv** for package management — no `requirements.txt`, everything in `pyproject.toml`
- **ruff** for linting and formatting
- **ty** for type checking
- **pytest** for testing
- DuckDB and Snowflake are optional extras, not default dependencies
- DuckDB is included in the `[dependency-groups] dev` group so tests always run

### Checking and updating dependencies

```bash
uv run python scripts/check_deps.py              # report outdated with quarantine status
uv run python scripts/check_deps.py --update     # update only packages past quarantine
uv run python scripts/check_deps.py --audit      # include uv audit for known CVEs
uv run python scripts/check_deps.py --days 3     # set quarantine to 3 days
```

The checker queries PyPI for release dates and flags packages published within the quarantine window (default 7 days) to guard against supply-chain attacks. `--update` runs `uv lock --upgrade-package` + `uv sync` for safe packages only — quarantined and flagged packages are skipped. Always run tests after updating.

## Config File

Connections are stored in TOML. Location determined by `platformdirs`:
- Linux: `~/.config/qdo/connections.toml`
- macOS: `~/Library/Application Support/qdo/connections.toml`
- Windows: `%LOCALAPPDATA%\qdo\connections.toml`
- Override: `QDO_CONFIG` env var

## Code Quality — CI Gate

**Run these three checks before every push.** CI runs them and will fail if any produce errors or formatting changes. Run in this order:

```bash
uv run ruff format src/ tests/   # 1. format — may modify files, stage changes
uv run ruff check src/ tests/    # 2. lint — must pass with zero errors
uv run ty check                  # 3. type check — must pass with zero errors
```

If `ruff format` modifies files, stage those changes before committing. Run `pytest` as well to catch regressions.

Ruff config is in `pyproject.toml` (`[tool.ruff]`). Line length is 99. ty config is under `[tool.ty.environment]`.

There are no pre-commit hooks — just run these manually before committing.

### Releasing / Retagging

When the user says "retag", run the retag script to move the release tag to the current commit:

```bash
./scripts/retag.sh v0.1.0          # retag HEAD
./scripts/retag.sh v0.1.0 abc1234  # retag a specific commit
```

This deletes the GitHub release and remote/local tag, then recreates the tag at the target commit and pushes it. Always commit and push first, then retag.

## Writing tests

Before adding a test, read these rules. A tight, fast test suite is more valuable than a big one — every test is a lifelong maintenance obligation. The suite has drifted under "just add another" pressure before; don't re-accumulate it.

1. **Name the failure mode.** Write the one-sentence regression this test prevents. If you can't name it, don't write the test. "Coverage" is not a failure mode.
2. **Test behavior, not framework.** We don't own Typer's `--help` rendering, Jinja's escaping, YAML's round-trip, or DuckDB's query engine. Don't re-test them. A test whose assertions are really about a dependency's contract belongs upstream, not here.
3. **Exit code alone is not an assertion.** `assert result.exit_code == 0` proves the command parsed, nothing more. Pair every exit-code check with a real assertion about the output payload, a file written to disk, or an observable side effect. Same rule applies to `!= 0` — assert on the error code or classification, not just on failure.
4. **Prefer parameterization to copy-paste.** Two tests that differ only in fixture path (`sqlite_path` vs `duckdb_path`) should be one `@pytest.mark.parametrize` unless the assertions genuinely diverge (e.g., DDL types, UDF syntax, dialect-specific built-ins). When they do diverge, keep both — that's real dialect coverage.
5. **Scenario coverage is not redundancy.** Three tests per rule that each exercise a distinct branch (populated / empty / no-metadata) are each doing work — don't cut them in the name of "deduplication." Duplicate assertions across three files *is* redundancy; three assertions across three branches isn't.
6. **Integration tests beat unit tests for helpers used in one place.** If a helper is only called from one CLI command, one round-trip test through that command beats an isolated unit test of the helper. Reserve unit tests for pure logic that's reused or genuinely hard to reach via integration.
7. **Don't string-match error prose.** Error message wording drifts; brittle substring matches churn on every refactor and silently pass when the error handling degrades. Assert on error codes, exit statuses, or structured `try_next` / envelope fields — not on human-readable messages.

See PLAN.md → "Test-suite cleanup" (T.1–T.10) for the concrete cleanup todos derived from these rules. When pruning, the `Don't touch — already good` list in that section calls out tests that look cuttable but aren't.

## Style Guide

- Keep functions focused and small
- Don't over-engineer — solve the current problem, not hypothetical future ones
- Tests should prove things work, not chase coverage numbers (see "Writing tests" above)
- Use type hints on function signatures
- Don't add docstrings/comments unless the logic is non-obvious
- Connectors are context managers — use `with` statements, not try/finally
