# Ideas

Research archive and deferred ideas for qdo.

> **Active work lives in [PLAN.md](PLAN.md).** This file is not a todo list and should not be used to decide what to build next. It exists to preserve background research, rejected decisions, and deferred ideas that may later be promoted into `PLAN.md`.
>
> **What belongs here:**
> - competitive analysis and positioning notes
> - rejected directions / non-goals worth preserving
> - deferred ideas that are not yet committed
>
> **What does not belong here:**
> - current status tracking
> - implemented feature walkthroughs
> - anything that now lives more accurately in code or `PLAN.md`
>
> **Last major research pass:** 2026-06-23. Covered qsv, datasette, VisiData, Harlequin, DuckDB CLI, csvkit, xsv, Recap, datacontract-cli, Splink, Great Expectations / Soda / dbt-expectations, Metabase / Mathesar, Sling, dlt, Polars CLI, and data-analysis MCP servers in the wild. Also researched token-efficient output formats, MCP server architecture, Rust+PyO3 feasibility, and agent tutorial design.

---

## Positioning

Research notes from comparing querido to qsv, datasette, visidata, harlequin, and the DuckDB CLI (2026-04-13).

### What qdo is

Querido sits in a niche between:

- **qsv** — large CSV/Parquet/Excel toolbelt (~55 subcommands), row-oriented, Rust/Polars, now also MCP-oriented. Extraordinarily fast on flat files (NYC 311 27M rows: `stats` in ~16s, `count` indexed in 0.03s). Docs: https://github.com/jqnatividad/qsv
- **datasette** — web-first SQLite/Parquet explorer with a large plugin ecosystem, facets, canned queries, and publishing workflow. Every view is an API (HTML+JSON on the same URL). Docs: https://datasette.io
- **visidata** — interactive terminal spreadsheet / EDA multitool. Batch mode (`vd -b`) and cmdlog replay (`.vd` scripts) for reproducible workflows. Reads ~30 file formats. Docs: https://www.visidata.org
- **harlequin** — SQL IDE in the terminal. DuckDB-first with pluggable adapters (SQLite, Postgres, MySQL). Query history log per project. Docs: https://harlequin.sh
- **duckdb CLI** — database shell with `SUMMARIZE`, `DESCRIBE TABLES`, `FROM 'file.parquet'` implicit readers, `ATTACH` for multi-DB. Minimal workflow opinion. Docs: https://duckdb.org/docs/stable/clients/cli/overview
- **csvkit** — Python CSV toolkit (`csvstat`, `csvsql`, `in2csv` for xlsx/json/dbf). Docs: https://csvkit.readthedocs.io
- **Polars CLI** — tiny SQL shell over Polars; pipe mode (`echo "SELECT ..." | polars`). No catalog, no metadata, no structured errors — the gap qdo fills. Docs: https://github.com/pola-rs/polars-cli

**Adjacent tools worth tracking (not direct competitors):**

- **datacontract-cli** — YAML-driven schema contracts with `lint`, `test`, `breaking` (detects breaking schema changes). Docs: https://cli.datacontract.com/
- **Great Expectations / Soda Core** — data testing / assertion vocabularies. GX's `expect_column_values_to_not_be_null` naming is de-facto standard. Soda uses SodaCL YAML like `row_count > 0`. Docs: https://docs.soda.io/, https://github.com/calogica/dbt-expectations
- **Recap** — unified type spec across Protobuf/Avro/JSON Schema/DDL. URL-addressable schemas (`postgresql://host/db/schema/table`). Docs: https://recap.build/docs/quickstart/
- **Sling** — extract/load CLI with `sling discover` for stream enumeration. Docs: https://docs.slingdata.io/
- **dlt** — schema inference + evolution + alerting; flattens nested JSON, detects drift. Docs: https://dlthub.com/docs/general-usage/schema-evolution

**qdo's differentiator:** CLI-native, multi-backend (SQLite/DuckDB/Snowflake/Parquet), structured agent-facing output, metadata-aware exploration, tiered profiling for wide tables, and a strong "pay for what you use" discipline. The Snowflake depth and metadata compounding loop remain the most differentiated parts of the product. No other tool in this space offers all four of: single-call `context` for agent cold-start, structured JSON errors with next-step hints, skill files for agent harnesses, and cross-backend parity.

### Lean into

1. **Agent-first, but not agent-only.** Stable flags, structured errors, deterministic next-step hints, and coherent command chains matter more than clever prose.
2. **Metadata that compounds.** The `.qdo/metadata/<conn>/<table>.yaml` system is one of the strongest moats; future ideas should reinforce it rather than route around it.
3. **Snowflake depth.** Cortex Analyst YAML, lineage, RESULT_SCAN-style reuse, warehouse-awareness.
4. **Tiered profiling for wide tables.** Quick mode, classify, column sets, and better triage UX.
5. **Named command chains.** `catalog -> context -> metadata -> query/assert -> report/bundle` remains the canonical story.
6. **Token-efficient output for agents.** JSON is verbose; a `--format compact` or `--format llm` mode that declares column headers once and emits TSV rows could save 40-60% of tokens. See "Token-efficient output mode" in deferred ideas below.
7. **Discoverability as API design.** `qdo overview --format json` is a machine-readable command reference. Every error includes a `hint` field pointing to the next command. This is the agent UX advantage over tools that assume humans read `--help`.

### Do not become

- **qsv.** Avoid drifting into row-stream transformation / CSV wrangling territory. qsv has ~55 subcommands; discoverability suffers. Things like `geocode`, `enumerate`, `flatten`, `fixlengths`, `reverse`, `transpose` are tiny utilities that fragment the UX.
- **datasette.** Avoid turning qdo into a hosting / plugin platform. No `publish` to cloud, no plugin marketplace, no per-column metadata in a monolithic JSON file (Datasette itself is migrating away from this).
- **harlequin.** Avoid growing `explore` into a full terminal SQL IDE.
- **a Rust rewrite.** The hot path lives in DuckDB / SQLite / Snowflake already. See "Rust + PyO3" in rejected ideas.
- **an in-product NL-to-SQL assistant.** The agent is the brain; qdo should stay the deterministic tool layer. `describegpt` in qsv sends stats to an LLM — this is a credential/privacy footgun and scope creep.
- **an EL pipeline.** Sling and dlt own extract/load. qdo is read-focused.
- **an entity resolution library.** Splink owns probabilistic record linkage. `qdo joins` can suggest blocking candidates and document handoff.
- **a catalog registry / server.** Recap and DataHub own this. Files remain the primitive.
- **a data testing framework.** GX/Soda own deep testing. `qdo assert` and `qdo quality` are the right thin layer. Consider adopting GX vocabulary (see deferred ideas) but don't build suites, checkpoints, or Data Docs.

---

## Rejected Or Dropped

These ideas are worth keeping as historical decisions so they do not get re-proposed without context.

### Subcommand-to-workflow sugar

**Status:** rejected.

The idea was to let bundled workflows appear as top-level commands (`qdo <workflow-name>`) or to convert more built-ins into workflow-backed aliases. This was dropped in favor of a single invocation pattern: `qdo workflow run <name>`. The clarity gain from one workflow surface outweighed the convenience of dual paths.

### Broad Rust adoption

**Status:** dropped.

Two separate variants were considered and rejected:

- **Rust + PyO3 for hot paths:** low ROI because the meaningful performance work already happens inside native database engines.
- **Rust -> WASM browser rewrite:** too much code duplication for too little differentiation; if browser qdo ever matters, Pyodide is the more pragmatic path.

### Rich hosted / plugin platform

**Status:** rejected.

No hosted viewer, no plugin marketplace, no server-first direction. Files remain the primitive for sessions, metadata, bundles, workflows, and reports.

### In-product LLM features

**Status:** rejected.

Natural-language-to-SQL inside qdo and similar LLM-in-the-loop features remain out of scope. Deterministic heuristics and stable outputs are the intended product boundary.

### `qdo search "<intent>"` (BM25 command discovery)

**Status:** built then cut (2026-04-22).

Shipped as a lightweight BM25 ranker over command docs / descriptions. Cut during the pre-release polish pass because it never entered SKILL.md's promoted workflow, competed with `qdo --help` / `qdo <cmd> --help` for the same job, and showed no adoption in eval traces. Agents with context-cached `--help` output do not hit a "which command does this?" problem often enough to justify maintaining a search layer. Don't re-propose without evidence of a real discovery gap that cached help doesn't solve.

---

## Deferred Ideas

These ideas are not committed. Some also appear in `PLAN.md`'s deferred section once they become concrete enough to track there.

### Discovery and navigation

- **Visible command graph / `qdo next` / `qdo explain <command>`** — helpful for agents and onboarding, but not yet committed enough to leave the archive.

### Metadata and memory

- **Embedding-based semantic search across metadata** — local embeddings over table and column descriptions for intent search.
- **Metadata undo** — revert the last metadata write using session / provenance information.
- **Session replay** — rerun a prior investigation from the session log.
- **Stable output/result identifiers** — reference prior outputs more directly than session-step granularity.
- **Branching from a base query** — build on `--from <session>:<step>` so an investigation can fork cleanly from the same saved query without restating SQL.

  Deferred design sketch:

  - Keep the current invariant that the reusable unit is a prior structured `query` step whose envelope contains canonical SQL.
  - Add a small set of deterministic branch operators on top of that base SQL instead of inventing a general expression language.
  - Likely first candidates: `query --from s:7 --where ...`, `--order-by ...`, `--limit ...`, `--columns ...`, and maybe `export --from s:7 --where ...`.
  - Semantics should be "wrap the base SQL as a subquery, then apply the branch operator" so the base node remains immutable and multiple branches can reuse it safely.
  - Structured output should record both the source step and the derived operation, so sessions read like a tree even though the storage model stays append-only.
  - If this grows, prefer explicit branch naming such as `--label null-audit` or session-report grouping over hidden graph state.

  Constraints / non-goals:

  - Do not turn sessions into a mutable notebook or DAG runtime.
  - Do not allow arbitrary field-path extraction from old envelopes as the main mechanism.
  - Do not silently inherit connection or table context in ways that make re-execution ambiguous.
  - Avoid a full mini-SQL builder; the point is ergonomic branching from a known-good base query, not replacing SQL authoring.
  - Keep `query` as the branch root unless there is a strong case for promoting stable result identifiers or materialized intermediate artifacts later.

### Investigation workflows

- **`qdo investigate ...` commands** — canned investigations like freshness, migration safety, or join validation, likely as bundled workflows rather than special Python primitives.
- **Additional shared playbooks / recipes** — especially if they teach an agent how to choose and sequence commands well.

### Safety, cost, and progressive disclosure

- **`--estimate`** on `query` / `export` — cost or duration estimates before running.
- **Read-only-by-default `query`** — require an explicit opt-in for mutating SQL.
- **`--plan` dry-run** on exports, query execution, and metadata writes.
- **`--level 1..3`** on expensive commands — progressive disclosure of scan depth.

### Time-awareness and change detection

- **`qdo diff --since <session|snapshot>`** — schema and row-count changes over time.
- **Snapshot-oriented cache comparisons** — make "what changed since last time?" a first-class loop.
- **`qdo freshness`** — detect staleness via timestamp columns with optional assertions.

### Snowflake-specific depth

- **RESULT_SCAN reuse for chained queries** — reduce repeated scans across multi-step flows.
- **Warehouse/cost awareness in output** — more explicit time / credit signals where they matter.

### Portability and external surfaces

- **MCP thin wrapper** — still deferred; keep the CLI MCP-ready instead of building a large parallel surface.
- **Browser / Pyodide demo (`querido-lite`)** — only worth doing if there is a real adoption or embedding pull.

### Convenience / team ergonomics

- **Opt-in polars Arrow→DataFrame convenience** — not committed; capture only. qdo today has *no* DataFrame layer by design: connectors return Arrow (`fetch_arrow_batches` for Snowflake, `to_arrow_table()` for DuckDB) → `to_pylist()` → `list[dict]`, and all profiling / dist / pivot / quality compute is pushed down to SQL and run in the engine. There is **zero pandas** in the tree, so there is nothing to *migrate*; the pandas-vs-Snowflake efficiency concern (implicit conversion) is already avoided at the Arrow fast path. The only gap polars would fill is *handing data back* for local post-processing — e.g. an `export` that goes Arrow → polars → parquet/csv without the dict round-trip, or a command path that returns a `pl.DataFrame`. Treat as an *addition*, not a replacement: a thin Arrow→polars helper behind a `[polars]` extra, lazily imported inside the function (preserving "pay for what you use"), pandas kept only as a fallback for features polars lacks. **Trigger to promote:** dogfooding surfaces a concrete "I exported and immediately wanted a DataFrame" moment. Until then, the Arrow layer already captures the efficiency win and no code is warranted.
- **Audit log / SQL history / command history** — possibly useful, but likely only if sessions do not already cover the need well enough.
- **`qdo sniff`** — detect ad hoc file types / encodings more explicitly.
- **`qdo to`** — format conversion via the engine, e.g. CSV -> Parquet.
- **`qdo catalog functions`** — surface built-in SQL functions for DuckDB and Snowflake.

### Token-efficient output mode (agent-focused)

**Status:** deferred, high value. Research completed 2026-06-23.

**Problem:** JSON repeats keys per row in arrays, which is the dominant token cost. For a 500-row dataset, JSON can use 2-3x more tokens than a header-once format. Agents consume qdo output in their context window and pay per token.

**Research findings** (sources: [Nathaniel Thomas benchmarks](https://nathom.dev/llm-data-formats/), [David Gilbertson JSON vs TSV](https://david-gilbertson.medium.com/llm-output-formats-why-json-costs-more-than-tsv-ebaf590bd541), [LogRocket TOON analysis](https://blog.logrocket.com/reduce-tokens-with-toon/), [Tensorlake TOON vs JSON](https://www.tensorlake.ai/blog-posts/toon-vs-json), [TOON spec](https://github.com/toon-format/spec), [Anthropic tool use docs](https://docs.anthropic.com/en/docs/build-with-claude/tool-use), [MCP token bloat SEP-1576](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1576)):

| Format | Relative cost vs minified JSON | Notes |
|---|---|---|
| TOON (column-major tabular) | ~40-60% fewer tokens | 500-row dataset: JSON 11,842 → TOON 4,617 tokens (−61%) |
| CSV / TSV | ~30-50% fewer tokens | "CSV crushes everything" for flat uniform data |
| Minified JSON | 1.0× (baseline) | Best for nested/irregular data |
| Markdown lists | ~-15% for simple lists | |
| YAML | +15-25% more tokens | Surprisingly poor despite readability |
| Markdown pipe tables | Often worst | Pipes/dashes are pure token bloat |
| Pretty JSON | +60-90% vs minified | Pure whitespace cost |

**Key guidance from Anthropic:** "Design tool responses to return only high-signal information... include only the fields Claude needs. Bloated responses waste context." XML tags for bookends cost ~4 tokens total and help Claude isolate tool output. No published evidence that Claude tokenizes markdown vs JSON differently *structurally* — the win comes from fewer punctuation tokens and key deduplication. ([Claude 4 prompting best practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices), [Speakeasy MCP token reduction](https://www.speakeasy.com/blog/how-we-reduced-token-usage-by-100x-dynamic-toolsets-v2))

**Concrete plan for `--format compact` (or `--format llm`):**

1. Per-command optimal format: `compact` for catalog = TOON-style (nested tabular), `compact` for context/profile/query = TSV with typed header.
2. Header once, rows after. Never repeat keys per row.
3. Always minify — pretty JSON costs +60-90% tokens for zero agent benefit.
4. Truncate aggressively with explicit markers: `... 1199950 more rows (use --limit to expand)`. Default 50 rows for compact mode.
5. One-line preamble: `# qdo catalog db=prod tables=3 format=compact` — cheap, lets agent self-orient.
6. Do NOT use markdown pipe tables, YAML, or TOML — all worse than minified JSON per every 2025-2026 benchmark.
7. Consider `orjson` ([github.com/ijl/orjson](https://github.com/ijl/orjson), Rust-based, ~5x faster than stdlib) for JSON serialization; it's already a PyO3 binding so zero new Rust build infra needed.

**Example compact output for `qdo context`:**
```
# qdo context db=mydb table=orders rows=50000
column	type	null_pct	distinct	min	max	samples
id	int	0.0	50000	1	50000	
status	str	0.5	4			pending|shipped|delivered|cancelled
amount	num	1.2	12543	0.99	9999.0	
created_at	ts	0.0	49823	2020-01-01	2024-12-31	
```

**Example compact output for `qdo catalog`:**
```
# qdo catalog db=mydb tables=3
table	rows	columns
orders	50000	id:int,status:str,amount:num,created_at:ts
users	12000	id:int,email:str,name:str,created_at:ts
events	9400000	id:int,ts:ts,user_id:int,kind:str
```

**What NOT to do:** Don't invent a new format spec or require a parser. TSV with a comment preamble is universally parseable by every agent, jq, awk, and spreadsheet. Don't abbreviate field names to single letters — saving 2-3 tokens per row is not worth mystery abbreviations.

**Trigger to promote:** measure actual token costs of current JSON output across the top 5 commands using `tiktoken` (GPT-4o) and Anthropic's tokenizer. If the savings are >30% on real output, ship it.

### MCP thin wrapper (expanded research)

**Status:** deferred, low effort if auto-generated. Research completed 2026-06-23.

**Context:** qdo already has `qdo overview --format json` which documents all commands and options machine-readably. The question is whether to expose those as MCP tools.

**MCP servers in the data space (for reference):**

- **MotherDuck/DuckDB MCP** — `query` (read-only) + `query_rw` (writes) + metadata tools. https://github.com/motherduckdb/mcp-server-motherduck
- **Snowflake Labs MCP** — Cortex Search, Cortex Analyst, object management, raw SQL with RBAC. https://github.com/Snowflake-Labs/mcp
- **dbt MCP** — wraps both CLI invocations and Cloud APIs; tools like `dbt_run`, `dbt_test` are literally subprocess calls. https://github.com/dbt-labs/dbt-mcp
- **DuckDB community extension `duckdb_mcp`** — turns DuckDB itself into an MCP server. https://duckdb.org/community_extensions/extensions/duckdb_mcp
- **Google MCP Toolbox for Databases** — generic `list_tables`, `execute_sql`. https://github.com/googleapis/mcp-toolbox

**Architecture — minimum viable auto-generated wrapper (~100 lines):**

The official Anthropic Python SDK (`pip install "mcp[cli]"`) includes FastMCP ([github.com/modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk), [gofastmcp.com](https://gofastmcp.com)). A generated wrapper:

1. On startup, shell out to `qdo overview --format json` and parse the command manifest.
2. For each command, call `FastMCP.add_tool()` — name, description, and JSON Schema derived from the overview JSON.
3. Each tool handler converts kwargs to CLI flags and runs `subprocess.run(["qdo", subcommand, ...])`, returning stdout.
4. Mark read-only commands with `readOnlyHint: true`; mutating ones with `destructiveHint: true`.
5. Optional `--include` / `--exclude` globs to trim the tool list (reduces context cost — 20 tools × 200 tokens = 4k tokens baseline).
6. Transport: stdio only for v1 (works with Claude Desktop, Cursor).
7. Entry point: `qdo mcp serve` behind a `[mcp]` optional extra.

**Trade-offs vs direct shell-out:**

| Axis | MCP wrapper | Shell-out (Bash tool) |
|---|---|---|
| Discoverability | Tools appear in client tool list; descriptions in system prompt | Agent must know qdo exists, run `--help` |
| Token cost | Every tool def in context every turn (4k+ baseline) | Zero baseline; pay per `--help` invocation |
| Argument correctness | JSON Schema validated client-side | Agent frequently invents flags |
| Permissions | Per-tool allow/deny via MCP annotations | One blanket "can run bash" permission |
| Portability | Works in Claude Desktop, Cursor, Zed, Continue | Only where shell tool exists |
| Maintenance | Second surface to keep in sync (mitigated by auto-generation) | CLI is single source of truth |

**Recommendation:** worth doing because it's auto-generated from the overview JSON (near-zero maintenance), and it opens qdo to Claude Desktop and Cursor chat users. But it should remain a thin shim — no hand-written per-tool wrappers, no parallel feature surface, no MCP-specific features.

### Agent tutorial and skill file considerations

**Status:** deferred, needs more thought.

**Question:** should we create a dedicated tutorial for coding agents — a series of structured steps that guides particular workflows?

**Current state:** We already have `integrations/skills/SKILL.md` (comprehensive skill file), `qdo tutorial agent` (13 interactive lessons), and `AGENTS.md` (development context). The skill file covers the recommended workflow pattern (`catalog -> context -> metadata -> query`).

**Assessment:** a skill file is already effectively an agent tutorial. A separate document would duplicate it. The existing `qdo tutorial agent` is designed for human-guided agent onboarding — that's the right shape for learning, while the skill file is the right shape for production use.

**What might be worth doing instead:**

1. **Workflow recipes in the skill file** — add 3-5 named investigation patterns (freshness check, migration safety audit, join validation, data quality triage) as step-by-step sequences with expected outputs. Agents can pattern-match against these.
2. **"commonly follows" hints in `qdo overview`** — so agents can chain commands without memorizing the skill file.
3. **Compact skill file variant** — a stripped-down version for smaller context windows (Haiku-class models or tight system prompt limits).

**What NOT to do:** Don't create a separate tutorial that duplicates the skill file. Don't embed workflow logic in qdo itself — the agent harness is the orchestrator.

### Ideas from competitive research (2026-06-23)

Specific features observed in other tools, organized by source. See the Positioning section for tool descriptions and links.

**From qsv** (https://github.com/jqnatividad/qsv):

- **Stats cache** — `qsv stats` produces a reusable stats cache consumed by `frequency`, `schema`, `tojsonl`. qdo's `profile` output could be cached and reused by `template`, `metadata refresh`, `context` to avoid re-scanning. Related to "Cache improvements" but more aggressive — make profile results a first-class cached artifact.
- **Schema inference + JSON Schema validation** — `qsv schema` generates JSON Schema from stats+frequency; `qsv validate` checks rows against it, emitting `.valid.csv` + `.invalid.csv`. The validate/quarantine pattern is gold for agent data-cleaning loops. Could map to `qdo schema` + `qdo validate`, or extend `qdo quality`. Docs: https://github.com/jqnatividad/qsv/blob/master/src/cmd/schema.rs

**From datasette** (https://datasette.io):

- **Canned queries** — named SQL in YAML, parameterizable via `:param`. qdo could store named queries in `.qdo/queries/<conn>/<name>.sql` and invoke via `qdo query -c mydb --name monthly-revenue --param month=2024-06`. Agents discover available queries and reuse validated SQL instead of generating from scratch. Docs: https://docs.datasette.io/en/stable/sql_queries.html#canned-queries
- **Query log to SQLite** — Simon Willison's `llm` CLI logs every prompt/response to SQLite. The log-to-sqlite pattern could strengthen qdo's session system. Docs: https://llm.datasette.io

**From xsv** (https://github.com/BurntSushi/xsv):

- **Column selection mini-language** — `1,3,5`, `name,age`, ranges `1-3`, negation `!`. A uniform `--columns` spec across every subcommand would be a significant agent UX win. Currently qdo accepts comma-separated names; consider adding index-based and range-based selection.

**From datacontract-cli** (https://cli.datacontract.com/):

- **Breaking change detection** — `breaking` command detects changes that break downstream consumers (column removals, type narrowings, nullable→non-nullable). Could map to `qdo diff --breaking-only`.

**From Great Expectations / Soda** (https://docs.soda.io/, https://github.com/calogica/dbt-expectations):

- **Expectation vocabulary** — GX naming (`expect_column_values_to_not_be_null`) is de-facto standard. If qdo adds `qdo expect`, adopting this vocabulary means agents that know GX map directly.
- **SodaCL-style YAML assertions** — clean input format for `qdo assert` or new `qdo expect`:
  ```yaml
  checks for orders:
    - row_count > 0
    - missing_count(status) = 0
    - values in (status): [pending, shipped, delivered, cancelled]
    - freshness(created_at) < 24h
  ```

**From DuckDB CLI** (https://duckdb.org/docs/stable/clients/cli/overview):

- **`SUMMARIZE` delegation** — `qdo profile` could delegate to `SUMMARIZE` on DuckDB backend for the fast path and add qdo extras (top-k, classification) on top.
- **Glob patterns and URL support** — `FROM 'data/*.parquet'`, `FROM 'https://...'`. qdo handles single Parquet files; consider passing globs and URLs through to DuckDB.
- **`ATTACH` for cross-DB diff** — `qdo diff` could attach two databases in-process for in-engine comparison.

**From Metabase / Mathesar:**

- **FK hydration in catalog/inspect** — always surface FK constraints where the backend exposes them. Makes `qdo joins` authoritative when FKs exist.
- **dbt manifest.json ingestion** — `qdo context` could read dbt `manifest.json` when present and enrich catalog output with model descriptions and tests.

**From Recap** (https://recap.build/docs/quickstart/):

- **Canonical type normalization** — agents see `VARCHAR` (DuckDB), `TEXT` (SQLite), `STRING` (Snowflake) for the same concept. A normalized type vocabulary in `--format compact` output would reduce agent confusion.

### Rust + PyO3 assessment

**Status:** rejected. Research completed 2026-06-23.

**Finding:** qdo is I/O bound — most time is spent waiting on database queries and rendering output. The database engines (DuckDB C++, SQLite C, Snowflake network) are already native. Rewriting any part in Rust would add build complexity (maturin, Rust toolchain for contributors, wheel build matrix across platforms) for negligible gains.

**Startup time** is the one real Python tax:
- ruff (Rust): ~10 ms cold start. uv (Rust): ~20-30 ms. ripgrep (Rust): ~5-10 ms.
- Typical Python CLI with heavy imports: 300-800 ms. Click/Typer: 50-150 ms baseline.
- Refs: [Charlie Marsh on ruff startup](https://astral.sh/blog/the-ruff-formatter), [notes.crmarsh.com](https://notes.crmarsh.com/python-tooling-could-be-much-much-faster)

For a tool run once per query returning after 2+ seconds of database latency, 500 ms startup is noise. qdo already uses lazy imports to minimize this.

**If startup ever matters:** adopt `orjson` (already Rust/PyO3, ~5x faster JSON), push aggregations into SQL, distribute via `uv tool install` or [PyApp](https://github.com/ofek/pyapp) for bundled startup. Far cheaper than custom PyO3.

**What NOT to do:** Don't add maturin/Rust as a contributor requirement. Don't write PyO3 extensions for Arrow→JSON (pyarrow is already C++). Don't use PyOxidizer (unmaintained since 2023). Don't pursue until profiling shows a specific CPU-bound Python hot loop — today there isn't one.

### Quick wins worth considering now

Low-effort, high-value features identified during the 2026-06-23 research pass:

1. **`--format json-min`** — minified JSON (`indent=None` in json.dumps, or adopt `orjson`). Saves 60-90% of whitespace tokens. Near-zero implementation effort. Agents should default to this over pretty JSON.

2. **FK metadata in `inspect` / `catalog`** — surface foreign key constraints from `PRAGMA foreign_key_list` (SQLite), `duckdb_constraints()` (DuckDB), `information_schema.referential_constraints` (Snowflake). Makes `qdo joins` authoritative when FKs exist.

3. **Accept SQL from stdin** — `echo "SELECT ..." | qdo query -c mydb`. Useful for agent piping where SQL is generated in one step and executed in another.

4. **Glob patterns for Parquet** — `qdo preview -c 'data/*.parquet' -t data`. DuckDB handles this natively; qdo passes the glob through.

5. **`qdo profile` → `SUMMARIZE` delegation on DuckDB** — delegate to the built-in `SUMMARIZE` for the fast path and add qdo extras on top. Could halve profile time.

---

## Notes Worth Preserving

These are not active ideas by themselves, but they are useful filters for future planning:

1. **Prefer one mechanism over two.** If workflows can express a thing, avoid inventing a second parallel extension system.
2. **Prefer files over services.** Sessions, bundles, workflows, reports, and metadata should stay file-native unless there is overwhelming evidence otherwise.
3. **Prefer deterministic improvements over cleverness.** Better defaults, summaries, status signals, and next-step hints beat speculative AI features.
4. **Preserve "pay for what you use."** New features should not impose startup, install, or runtime costs on users who do not use them.
