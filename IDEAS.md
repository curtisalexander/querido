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

---

## Positioning

Research notes from comparing querido to qsv, datasette, visidata, harlequin, and the DuckDB CLI (2026-04-13).

### What qdo is

Querido sits in a niche between:

- **qsv** — large CSV/Parquet/Excel toolbelt, row-oriented, Rust/Polars, now also MCP-oriented.
- **datasette** — web-first SQLite/Parquet explorer with a large plugin ecosystem and publishing workflow.
- **visidata** — interactive terminal spreadsheet / EDA multitool.
- **harlequin** — SQL IDE in the terminal.
- **duckdb CLI** — database shell with minimal workflow opinion.

**qdo's differentiator:** CLI-native, multi-backend (SQLite/DuckDB/Snowflake/Parquet), structured agent-facing output, metadata-aware exploration, tiered profiling for wide tables, and a strong "pay for what you use" discipline. The Snowflake depth and metadata compounding loop remain the most differentiated parts of the product.

**The gap qdo fills:** agents can already *run* SQL. They are bad at knowing *what* to run. qdo gives them the pre-query understanding layer — schema, statistics, quality signals, join candidates, metadata, sample values — with stable JSON contracts. It is the tool layer that sits between "I have a database" and "I wrote a correct query."

### Competitive landscape (detail)

Updated 2026-06-23 with web research. Links and notes for future context.

**qsv** ([github.com/dathere/qsv](https://github.com/dathere/qsv)) — Rust CSV/Parquet/Excel toolbelt, 80+ subcommands. Notable: `stats` (rich per-column summary with type inference), `frequency` (value distributions), `schema` (infer JSON Schema + validation rules), `scoresql` (pre-flight SQL scoring/cost hints — scores a query *before* running it using cached stats/freq data), `describegpt` (LLM integration with MiniJinja prompt templates, supports Ollama/local models), `validate` (JSON Schema validation with custom keywords like `dynamicEnum`, `uniqueCombinedWith`), `sample` (reservoir/stratified/weighted/cluster sampling). qsv now ships an MCP server. Most interesting for qdo: `scoresql` concept (preflight cost/quality scoring) and the stratified sampling strategies. Most of qsv is CSV-stream processing that doesn't apply to SQL engines.

**datasette** ([datasette.io](https://datasette.io)) — Web-first SQLite/Parquet explorer with 150+ plugins. The interesting parts for qdo are NOT the web layer but the companion tools: **sqlite-utils** ([sqlite-utils.datasette.io](https://sqlite-utils.datasette.io)) has `memory` (query CSV/JSON files via in-memory SQLite), `analyze-tables` (per-column stats + most-common values), `transform` (safe ALTER TABLE), `extract` (normalize repeated columns into lookup tables). **llm** ([llm.datasette.io](https://llm.datasette.io)) has auto-logging of every prompt/response to a queryable SQLite DB (`llm logs`), embeddings collections with `llm similar`, and tool-calling plugins (`llm-tools-datasette`, `llm-tools-sqlite`). The auto-log-everything-to-SQLite pattern is worth studying — it's what makes llm sessions auditable and replayable. `datasette-embeddings` stores vectors as table columns with cosine similarity search. Skip: all auth plugins, HTML rendering, publishing, GraphQL, dashboards — web-platform concerns.

**Harlequin** ([harlequin.sh](https://harlequin.sh)) — SQL IDE TUI for DuckDB/Postgres/Snowflake/MySQL/SQLite. Beautiful catalog tree, autocomplete, adapter pattern. Purely interactive — no scriptable/JSON mode, no profiling verbs, no agent APIs, no templating. Confirms our TUI should stay a secondary interface, not the main product.

**DuckDB CLI** ([duckdb.org/docs/api/cli](https://duckdb.org/docs/api/cli)) — In-process OLAP engine REPL. `SUMMARIZE`, `DESCRIBE`, direct Parquet/CSV/JSON reads, httpfs for S3. No agent-oriented output contracts, no semantic layer, weak profiling beyond SUMMARIZE, no assertions, no diff/lineage, no multi-warehouse abstraction. qdo already wraps DuckDB and adds the missing layers.

**dbt** ([docs.getdbt.com](https://docs.getdbt.com)) — SQL transformation framework. Relevant: YAML column metadata pattern (`description`/`tests` per column in `schema.yml`), `sources.yml` freshness checks, compiled SQL artifacts, `manifest.json` as machine-readable context. dbt now ships an MCP server. 2026 benchmark shows semantic-layer-routed queries approach ~100% accuracy vs raw text-to-SQL. Heavy project scaffolding; not an analysis tool. Our metadata YAML system is spiritually adjacent but lighter.

**Great Expectations / Soda Core** ([greatexpectations.io](https://greatexpectations.io), [soda.io](https://www.soda.io)) — Declarative data-quality frameworks. Relevant: expectation vocabulary (`expect_column_values_to_not_be_null`), Soda's compact SCL language, checkpoint concept. Heavy setup, slow iteration, not agent-native. Our `quality` and `assert` commands cover the same ground with less ceremony.

**VisiData** ([visidata.org](https://www.visidata.org)) — Terminal spreadsheet for 50+ formats. Relevant: frequency tables, column type inference UX, pivot ergonomics, **save session as replay script** (worth studying for our session model). Purely interactive — no SQL scaffolding, no warehouse connectivity.

**Miller / mlr** ([miller.readthedocs.io](https://miller.readthedocs.io)) — Awk/sed/cut for structured rows. Verb chaining DSL, format-transparent IO. Not SQL, no warehouses, no catalog/metadata.

**Agent-era tools (2025-2026):** MCP database servers (postgres-mcp, sqlite-mcp, duckdb-mcp, snowflake-mcp) all expose `list_tables` + `describe_table` + `execute_sql` and stop there. No profiling, no quality, no diff, no cost guards, no metadata enrichment. Aggregators like DBHub and ToolFront wrap multiple backends. Vanna.AI ([vanna.ai](https://vanna.ai)) uses RAG-trained NL-to-SQL with DDL/docs/query embeddings. WrenAI ([wren.ai](https://wren.ai)) and Cube ([cube.dev](https://cube.dev)) push a "semantic layer for LLMs" concept — agents query metrics (governed, typed) rather than raw tables. Direction of travel: semantic-layer-routed queries beat raw text-to-SQL on accuracy.

**Research refresh (2026-07-06):** two independent landscape sweeps confirmed the integrated loop (deterministic CLI → exploration-time capture to repo YAML → same-tool consumption) still has no exact incumbent, but every adjacent cell is occupied and the window is narrowing. Closest neighbors: **ai-analyst-lab/ai-analyst** ([github](https://github.com/ai-analyst-lab/ai-analyst)) — auto-profiles and writes schema docs/quirks to `.knowledge/datasets/` for cross-session reuse, but prompt-orchestrated rather than deterministic; **duckdb/duckdb-skills** ([github](https://github.com/duckdb/duckdb-skills)) — official DuckDB plugin persisting session state (`state.sql`), one step from semantic metadata; **Anthropic's data-engineering plugin** (by Astronomer, 14,750+ installs) already *markets* "caches discovered patterns so repeated analysis gets faster over time"; **dbt Agent Skills** (Feb 2026) adopted the SKILL.md playbook for modeled data. Architecture tailwinds confirmed: skills + CLIs won over MCP-everything (Anthropic's own code-execution-with-MCP post, Zechner's MCP-vs-CLI benchmark, "many skills, few MCPs" consensus). Sobering signals: dbt-mcp sits at ~587 GitHub stars despite dbt's brand (solo data-CLI ceiling is real); skill files alone moved dbt's ADE-bench only 56%→58.5% (the pitch must rest on deterministic enforcement + compounding metadata, not "the skill makes the agent smarter"); distribution now runs through the Claude Code plugin marketplace and `npx skills add`, not PyPI alone. The strongest demand evidence found: hallucinated identifiers are the #1 documented agent failure mode and CLAUDE.md instructions demonstrably fail to fix it ([claude-code#53988](https://github.com/anthropics/claude-code/issues/53988)) — see DIFFERENTIATION.md "The failure mode qdo exists to prevent" and the hallucination benchmark in PLAN.md.

### Lean into

1. **Agent-first, but not agent-only.** Stable flags, structured errors, deterministic next-step hints, and coherent command chains matter more than clever prose.
2. **Metadata that compounds.** The `.qdo/metadata/<conn>/<table>.yaml` system is one of the strongest moats; future ideas should reinforce it rather than route around it.
3. **Snowflake depth.** Cortex Analyst YAML, lineage, RESULT_SCAN-style reuse, warehouse-awareness.
4. **Tiered profiling for wide tables.** Quick mode, classify, column sets, and better triage UX.
5. **Named command chains.** `catalog -> context -> metadata -> query/assert -> report/bundle` remains the canonical story.

### Do not become

- **qsv.** Avoid drifting into row-stream transformation / CSV wrangling territory.
- **datasette.** Avoid turning qdo into a hosting / plugin platform.
- **harlequin.** Avoid growing `explore` into a full terminal SQL IDE.
- **a Rust rewrite.** The hot path lives in DuckDB / SQLite / Snowflake already.
- **an in-product NL-to-SQL assistant.** The agent is the brain; qdo should stay the deterministic tool layer.
- **a CSV ETL pipeline** (qsv, miller, csvkit own this).
- **a data-loading / ingestion tool** (dlt, Airbyte own this).
- **a visualization platform** or BI tool.
- **a semantic layer *authoring* tool** (Cube, dbt own this) — we *read* semantic models, we don't author them beyond `snowflake semantic`.

### `--for-agent` vs `--format json` (design analysis)

Research from 2026-06-23 on emerging agent-first CLI conventions.

`--format json` is **serialization** — it changes the output encoding but nothing else. `--for-agent` is a **behavior profile** that bundles multiple concerns:

| Concern | `--format json` | `--for-agent` (proposed) |
|---|---|---|
| Output format | JSON | JSON |
| Spinners / progress on stderr | Still emitted | Suppressed |
| Colors / ANSI codes | Still possible in errors | Suppressed |
| Key ordering | Python dict order | Deterministic (sorted or schema-stable) |
| Long strings / large arrays | Full output | Truncated with counts + continuation hints |
| Error shape | Structured JSON to stderr | Same, plus `suggested_command` field |
| `next_actions` hints | Not included | Included (list of logical next commands) |
| Sampling notes | Prose in `sampling_note` | Structured fields only (`sampled: true`, `sample_size: N`) |
| Token budget awareness | None | Default `--top 5` instead of 10, preview `--rows 5` instead of 20 |

**Implementation:** `--for-agent` could be a single flag or env var (`QDO_AGENT=1`) that implies `QDO_FORMAT=json` + `QDO_NO_COLOR=1` + the behavioral changes above. The env var approach means agents set it once in their environment and forget it, similar to the existing `QDO_FORMAT=json` pattern.

**Key insight from research:** the 2026 agent-CLI design community consensus is that `--format json` is necessary but not sufficient. The behavior profile (token efficiency, deterministic ordering, continuation cursors, next-action hints) is what separates "has JSON output" from "designed for agents." Multiple sources describe this as the single highest-leverage improvement for agent adoption.

**What NOT to do:** don't create a separate "agent API" surface with different command names or arguments. The same commands, the same flags, just a different behavior profile. One surface, not two.

### MCP server tradeoffs (analysis)

Research from 2026-06-23 on MCP database servers and the thin-wrapper pattern.

**What exists today:** MCP database servers (postgres, sqlite, duckdb, snowflake) all expose 3-5 tools: `list_tables`, `describe_table`, `sample_rows`, `execute_sql`, sometimes `explain`. They are thin wrappers with no profiling, quality, diff, cost guards, or metadata enrichment. Aggregators like DBHub wrap multiple backends.

**What MCP gives you that CLI doesn't:**
- Host compatibility (Claude Desktop, Cursor, Windsurf) without shell access
- Tool discovery via protocol (agents enumerate available tools automatically)
- OAuth scoping and audit logging in hosted environments
- Stateful connections (no per-command connection overhead)

**What CLI gives you that MCP doesn't:**
- Token efficiency: MCP tool schemas consume 70k-90k tokens for large surfaces; a `qdo ... --json` invocation is hundreds of tokens
- Composability via pipes: LLMs have massive Unix training data; near-zero MCP composition training data
- Debuggability: stderr, exit codes, `--show-sql`, standard shell patterns
- Dual-use by humans

**Thin MCP-over-CLI is a real pattern** (MCPorter, smithery wrappers, dbt-mcp all wrap their respective CLIs). It works when: (a) the CLI returns stable JSON, (b) the wrapper exposes a *small curated* tool set (~5-8 macro tools) rather than 1:1 subcommand mirroring, and (c) multi-step flows are collapsed into single tools to save tokens.

**Recommended shape if we build it:** `qdo mcp serve` exposing ~6 tools:
- `list_sources` (catalog)
- `describe_table` (context — schema + stats + samples in one call)
- `profile_table` (profile with classify)
- `query` (ad-hoc SQL with cost guard)
- `sample_rows` (preview)
- `check_quality` (quality)

Each tool shells out to qdo CLI with `--for-agent`. Don't mirror every flag — collapse into sensible defaults. Don't expose template, metadata, config, or snowflake-specific tools via MCP (too niche, wastes token budget on schema).

**Current recommendation:** keep MCP deferred. The CLI with `--for-agent` serves 90% of agent use cases. Build MCP only if there is real pull from Claude Desktop / Cursor users who lack shell access. The prep work is: stable JSON contracts + `--for-agent` profile.

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

Detailed assessment (2026-06-23 research): qdo is I/O bound — most time is spent
waiting on database queries and rendering output, and the engines (DuckDB C++,
SQLite C, Snowflake network) are already native. Startup time is the one real
Python tax: ruff (Rust) ~10 ms cold start, uv ~20-30 ms, ripgrep ~5-10 ms,
versus a typical Python CLI with heavy imports at 300-800 ms (Click/Typer
50-150 ms baseline; refs: [Charlie Marsh on ruff
startup](https://astral.sh/blog/the-ruff-formatter),
[notes.crmarsh.com](https://notes.crmarsh.com/python-tooling-could-be-much-much-faster)).
For a tool run once per query that returns after 2+ seconds of database latency,
500 ms startup is noise, and qdo already uses lazy imports to minimize it. If
startup ever matters: adopt `orjson` (already Rust/PyO3, ~5x faster JSON), push
aggregations into SQL, and distribute via `uv tool install` or
[PyApp](https://github.com/ofek/pyapp) — all far cheaper than custom PyO3. Do
**not** add maturin/Rust as a contributor requirement, write PyO3 for
Arrow→JSON (pyarrow is already C++), or use PyOxidizer (unmaintained since
2023). Revisit only if profiling shows a specific CPU-bound Python hot loop —
today there isn't one.

### Rich hosted / plugin platform

**Status:** rejected.

No hosted viewer, no plugin marketplace, no server-first direction. Files remain the primitive for sessions, metadata, bundles, workflows, and reports.

### In-product LLM features

**Status:** rejected.

Natural-language-to-SQL inside qdo and similar LLM-in-the-loop features remain out of scope. Deterministic heuristics and stable outputs are the intended product boundary.

### `-f agent` TOON output format

**Status:** built then cut (2026-07-06).

Shipped as an alternate envelope serialization: TOON for tabular payloads, YAML
for nested, with an in-tree encoder and vendored spec-conformance fixtures. Cut
because it had zero adoption even internally: SKILL.md promoted `-f json`
exclusively, the 45/45 eval never exercised `-f agent`, and independent 2026
benchmarks showed token-format gains are shape-dependent with marginal accuracy
impact. An unpromoted parallel format is pure maintenance surface. Don't
re-propose without evidence that JSON token cost is an actual adoption blocker
— and if it is, promote the format in SKILL.md and re-run the eval as part of
the same change.

### `qdo search "<intent>"` (BM25 command discovery)

**Status:** built then cut (2026-04-22).

Shipped as a lightweight BM25 ranker over command docs / descriptions. Cut during the pre-release polish pass because it never entered SKILL.md's promoted workflow, competed with `qdo --help` / `qdo <cmd> --help` for the same job, and showed no adoption in eval traces. Agents with context-cached `--help` output do not hit a "which command does this?" problem often enough to justify maintaining a search layer. Don't re-propose without evidence of a real discovery gap that cached help doesn't solve.

---

## Deferred Ideas

These ideas are not committed. Some also appear in `PLAN.md`'s deferred section once they become concrete enough to track there.

### Agent-only tutorial document

Not the same as `qdo tutorial agent` (interactive, lesson-by-lesson). This is a **static markdown document** designed to be fed to a coding agent as a prompt or cached in its context. Not a command list — a workflow guide with decision points.

**What makes this different from AGENTS.md or SKILL.md:**
- AGENTS.md teaches how to *develop* qdo. SKILL.md is a command reference for agents *using* qdo.
- The agent tutorial teaches *how to think* about data exploration — when to stop profiling, when to sample, when to use metadata, how to interpret signals.

**Proposed structure:**
1. **Orientation** — set `QDO_FORMAT=json`, pick a connection, run `catalog --tables-only` to scope the database.
2. **Triage** — for each relevant table, run `context`. Read the output. Decision: if `row_count` > 1M, expect sampling. If 50+ columns, expect `--classify` before full profile.
3. **Narrowing** — use `profile --classify` to categorize columns. Decision: if `distinct_count == row_count`, column is likely a PK — stop profiling it. If `null_pct > 50`, column is sparse — note it but don't drill in unless relevant.
4. **Join discovery** — run `joins` on tables you plan to join. Verify cardinality before writing JOIN SQL. Decision: if join candidate shows many-to-many, investigate with `dist` before assuming correctness.
5. **Quality check** — run `quality` on tables entering a query. Decision: if uniqueness violations or high null rates on key columns, flag to the user before proceeding.
6. **Metadata enrichment** — if metadata exists (`metadata show`), merge business context. If not, note the gap but don't block.
7. **Writing SQL** — use `sql select` scaffold as a starting point. Run queries with `query`. Verify results with `assert`.
8. **Cost consciousness** (Snowflake) — prefer `--no-sample` only when exact stats matter. Use `--rows 5` for preview, not 100.

**Deliverable:** `integrations/tutorials/agent-workflow.md` — a single file, ~1000-1500 tokens, designed to fit in an agent's context alongside SKILL.md. Not a replacement for SKILL.md (which stays a command reference) but a companion that teaches sequencing and judgment.

**Follow-up assessment (2026-06-23):** a skill file is already effectively an
agent tutorial, so a separate static document would largely duplicate
`integrations/skills/SKILL.md`. We already have SKILL.md (comprehensive skill
file covering the `catalog -> context -> metadata -> query` workflow), `qdo
tutorial agent` (13 interactive lessons for human-guided onboarding), and
AGENTS.md (development context). Rather than a new duplicating document, the
higher-value moves are: (1) **workflow recipes in the skill file** — 3-5 named
investigation patterns (freshness check, migration safety audit, join
validation, data quality triage) as step-by-step sequences with expected
outputs, so agents can pattern-match; (2) **"commonly follows" hints in `qdo
overview`** so agents chain commands without memorizing the skill file; (3) a
**compact skill file variant** for smaller context windows (Haiku-class models
or tight system-prompt limits). Do not embed workflow logic in qdo itself — the
agent harness is the orchestrator.

### Cherry-picked ideas from competitors

Ideas worth stealing from the competitive landscape (2026-06-23 research). Each has a note on fit.

**From qsv:**
- **Preflight SQL scoring (`scoresql` concept)** — score a query *before* running it using cached stats/freq data, suggest optimizations. Natural fit for `qdo plan` or `qdo explain --preflight`. Medium lift. Would need cached profile data to score against. Very agent-friendly: "don't run this, it'll scan 2B rows; add a WHERE on event_date."
- **Stratified / weighted sampling** — qdo currently does simple random sampling at >1M rows. Stratified sampling (sample proportionally across a grouping column) would give more representative previews. Small-medium lift. Upgrade to `--sample-strategy stratified --sample-by region`.
- **JSON Schema inference from data** — qsv's `schema` infers validation rules from column data. Could feed into `assert` or `metadata` as auto-generated constraints. Medium lift.

**From sqlite-utils / llm:**
- **Auto-log every invocation to local SQLite** — llm's `llm logs` pattern. Every qdo invocation records: timestamp, command, connection, table, flags, duration, row_count, whether sampled, exit code. Queryable with `qdo log` or raw SQL. HIGH VALUE for debugging agent loops (what did it run? what failed? how long did it take?). Overlaps with session log but lower-ceremony — sessions are explicit, the auto-log is ambient. Small lift (just log to `~/.config/qdo/history.db` on every invocation).
- **`memory`-style ad-hoc file query** — sqlite-utils lets you `memory data.csv "select ..."`. qdo already supports Parquet-as-connection via DuckDB pass-through. Could extend to CSV/JSON/NDJSON with `qdo query -c data.csv --sql "..."` using DuckDB's auto-detection. Small lift — DuckDB already handles this; we'd just relax connection resolution.

**From dbt:**
- **Lightweight metrics manifest** — a YAML file defining measures and dimensions over tables, separate from metadata descriptions. Agents query metrics (governed, typed) instead of raw columns. Aligns with semantic-layer trend. Would NOT be a full dbt-style semantic layer — just a simple `metrics.yaml` that `context` can surface. BIG lift to do well. Defer unless there's real pull.

**From VisiData:**
- **Session as replay script** — VisiData saves sessions as replayable command logs. Our session system already captures structured steps; the gap is a `qdo session replay <id>` that re-executes. Medium lift. Mentioned elsewhere in deferred ideas.

More from the 2026-06-23 pass, organized by source (some sources also described in the Positioning section):

**More from qsv** ([github.com/jqnatividad/qsv](https://github.com/jqnatividad/qsv)):
- **Stats cache** — `qsv stats` produces a reusable stats cache consumed by `frequency`, `schema`, `tojsonl`. qdo's `profile` output could be cached and reused by `template`, `metadata refresh`, `context` to avoid re-scanning. More aggressive than generic cache improvements — make profile results a first-class cached artifact.
- **Schema inference + JSON Schema validation** — `qsv schema` generates JSON Schema from stats+frequency; `qsv validate` checks rows against it, emitting `.valid.csv` + `.invalid.csv`. The validate/quarantine pattern is gold for agent data-cleaning loops. Could map to `qdo schema` + `qdo validate`, or extend `qdo quality`.

**From datasette** ([datasette.io](https://datasette.io)):
- **Canned queries** — named SQL in YAML, parameterizable via `:param`. qdo could store named queries in `.qdo/queries/<conn>/<name>.sql` and invoke via `qdo query -c mydb --name monthly-revenue --param month=2024-06`. Agents discover available queries and reuse validated SQL instead of generating from scratch. Docs: https://docs.datasette.io/en/stable/sql_queries.html#canned-queries

**From xsv** ([github.com/BurntSushi/xsv](https://github.com/BurntSushi/xsv)):
- **Column selection mini-language** — `1,3,5`, `name,age`, ranges `1-3`, negation `!`. A uniform `--columns` spec across every subcommand would be a significant agent UX win. Currently qdo accepts comma-separated names; consider adding index-based and range-based selection.

**From datacontract-cli** ([cli.datacontract.com](https://cli.datacontract.com/)):
- **Breaking change detection** — `breaking` command detects changes that break downstream consumers (column removals, type narrowings, nullable→non-nullable). Could map to `qdo diff --breaking-only`.

**From Great Expectations / Soda** ([docs.soda.io](https://docs.soda.io/), [dbt-expectations](https://github.com/calogica/dbt-expectations)):
- **Expectation vocabulary** — GX naming (`expect_column_values_to_not_be_null`) is de-facto standard. If qdo adds `qdo expect`, adopting this vocabulary means agents that know GX map directly.
- **SodaCL-style YAML assertions** — clean input format for `qdo assert` or new `qdo expect`:
  ```yaml
  checks for orders:
    - row_count > 0
    - missing_count(status) = 0
    - values in (status): [pending, shipped, delivered, cancelled]
    - freshness(created_at) < 24h
  ```

**From DuckDB CLI** ([duckdb.org/docs/stable/clients/cli/overview](https://duckdb.org/docs/stable/clients/cli/overview)):
- **`SUMMARIZE` delegation** — `qdo profile` could delegate to `SUMMARIZE` on DuckDB backend for the fast path and add qdo extras (top-k, classification) on top.
- **Glob patterns and URL support** — `FROM 'data/*.parquet'`, `FROM 'https://...'`. qdo handles single Parquet files; consider passing globs and URLs through to DuckDB.
- **`ATTACH` for cross-DB diff** — `qdo diff` could attach two databases in-process for in-engine comparison.

**From Metabase / Mathesar:**
- **FK hydration in catalog/inspect** — always surface FK constraints where the backend exposes them. Makes `qdo joins` authoritative when FKs exist.
- **dbt manifest.json ingestion** — `qdo context` could read dbt `manifest.json` when present and enrich catalog output with model descriptions and tests.

**From Recap** ([recap.build](https://recap.build/docs/quickstart/)):
- **Canonical type normalization** — agents see `VARCHAR` (DuckDB), `TEXT` (SQLite), `STRING` (Snowflake) for the same concept. A normalized type vocabulary in `--format compact` output would reduce agent confusion.

**Not stealing:**
- qsv's CSV-stream transforms, row-level processing, file-format converters — SQL engines handle this
- datasette's web publishing, auth, GraphQL, plugin marketplace — not our model
- VisiData's interactive-only design — we need scriptability
- dbt's project scaffolding, ref() DAG, heavy YAML ceremony — too much overhead for ad-hoc analysis
- Great Expectations' Python-class expectation authoring — our `assert` is SQL-native and lighter

### Token-efficient output mode (agent-focused)

**Status:** deferred, research completed 2026-06-23. See also the `-f agent` TOON
format in "Rejected Or Dropped" — that specific envelope was built then cut
(2026-07-06); this note captures the underlying research and a lighter TSV-based
alternative. Don't re-propose without evidence that JSON token cost is an actual
adoption blocker.

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
- **`CREATE SEMANTIC VIEW` export** — **shipped 2026-07-06**: `qdo snowflake
  semantic` now emits `create semantic view` DDL instead of stage-based Cortex
  Analyst YAML (Snowflake calls the YAML path the "legacy stage API" and
  recommends semantic views for all new implementations; Snowflake-Labs'
  semantic-model-generator is deprecated in favor of the Snowsight generator).
  The legacy YAML builder survives only behind `qdo template --format yaml`.
  Refs:
  https://docs.snowflake.com/en/user-guide/views-semantic/semantic-models-vs-views,
  https://github.com/Snowflake-Labs/semantic-model-generator.

### Portability and external surfaces

- **MCP thin wrapper** — still deferred; keep the CLI MCP-ready instead of building a large parallel surface. See the MCP tradeoffs analysis in Positioning above for the recommended 6-tool shape and the "don't build until there's pull" recommendation.

  Auto-generation sketch (2026-06-23 research): if built, it should be
  *generated* from `qdo overview --format json` rather than hand-written, keeping
  it near-zero maintenance. The official Anthropic Python SDK (`pip install
  "mcp[cli]"`) bundles FastMCP
  ([python-sdk](https://github.com/modelcontextprotocol/python-sdk),
  [gofastmcp.com](https://gofastmcp.com)). A ~100-line wrapper would: parse the
  overview manifest on startup; `FastMCP.add_tool()` per command (name,
  description, JSON Schema derived from the overview); each handler converts
  kwargs to CLI flags and `subprocess.run(["qdo", ...])`, returning stdout; mark
  read-only commands `readOnlyHint: true` and mutating ones
  `destructiveHint: true`; expose `--include`/`--exclude` globs to trim the tool
  list (20 tools × ~200 tokens = 4k baseline); stdio transport only for v1.
  Reference servers in the data space: MotherDuck/DuckDB
  ([mcp-server-motherduck](https://github.com/motherduckdb/mcp-server-motherduck)),
  Snowflake Labs ([mcp](https://github.com/Snowflake-Labs/mcp)), dbt
  ([dbt-mcp](https://github.com/dbt-labs/dbt-mcp), literally subprocess calls),
  the DuckDB community `duckdb_mcp` extension, and Google's [MCP Toolbox for
  Databases](https://github.com/googleapis/mcp-toolbox). Keep it a thin shim: no
  hand-written per-tool wrappers, no parallel feature surface, no MCP-specific
  features.
- **Browser / Pyodide demo (`querido-lite`)** — only worth doing if there is a real adoption or embedding pull.
- **Ad-hoc CSV/JSON/NDJSON connection** — extend connection resolution so `qdo query -c data.csv --sql "..."` works via DuckDB auto-detection. Small lift since DuckDB already handles these formats; we'd just relax the file-extension-to-type mapping in `config.py`. Currently only `.parquet`, `.duckdb`, `.ddb` and SQLite files are auto-detected.

### High-value near-term ideas (small lift, big impact)

Ideas specifically flagged as worth considering now because the implementation cost is low relative to the value. Not committed — just called out for easy promotion to PLAN.md.

1. **`--for-agent` behavior profile** — env var `QDO_AGENT=1` or flag that implies JSON format + suppressed spinners + deterministic key ordering + token-efficient defaults + `next_actions` hints in output. The single highest-leverage agent adoption improvement per 2026 research. Small-medium lift: most of the machinery exists (`QDO_FORMAT`, structured errors, `--top`, `--rows` defaults). Main new work: `next_actions` hint generation and deterministic ordering audit.

2. **Auto-log invocations to local SQLite** — every qdo command records timestamp, command, connection, table, flags, duration, row_count, exit code to `~/.config/qdo/history.db`. Queryable via `qdo log` (show recent) or raw SQL. Invaluable for debugging agent loops. Small lift: ~50 lines in a decorator or CLI callback. Does not replace sessions (which are explicit and structured) but complements them as ambient telemetry.

3. **CSV/JSON/NDJSON as ad-hoc connections** — extend file-path connection resolution to `.csv`, `.json`, `.jsonl`, `.ndjson` via DuckDB auto-detection. Small lift: relax `config.py` extension mapping + test.

4. **Deterministic JSON output** — audit all JSON output paths for stable key ordering (sorted keys or schema-defined order). Tiny lift. Matters for agent tool-calling where output diffs should be meaningful.

5. **`next_actions` field in JSON output** — each command's JSON output includes a list of suggested follow-up commands based on what the agent just learned. Example: `profile` output includes `next_actions: ["qdo dist -c X -t Y -C high_null_column", "qdo values -c X -t Y -C low_cardinality_column"]`. Medium lift — requires per-command heuristics. Very high value for agent discoverability and workflow coherence.

6. **`--format json-min`** — minified JSON (`indent=None`, or adopt `orjson`). Saves 60-90% of whitespace tokens versus pretty JSON. Near-zero implementation effort; agents should default to this. Overlaps with the "Token-efficient output mode" research above.

7. **FK metadata in `inspect` / `catalog`** — surface foreign-key constraints from `PRAGMA foreign_key_list` (SQLite), `duckdb_constraints()` (DuckDB), `information_schema.referential_constraints` (Snowflake). Makes `qdo joins` authoritative when FKs exist.

8. **Accept SQL from stdin** — `echo "SELECT ..." | qdo query -c mydb`. Useful for agent piping where SQL is generated in one step and executed in another.

9. **Glob patterns for Parquet** — `qdo preview -c 'data/*.parquet' -t data`. DuckDB handles this natively; qdo passes the glob through.

10. **`qdo profile` → `SUMMARIZE` delegation on DuckDB** — delegate to the built-in `SUMMARIZE` for the fast path and add qdo extras on top. Could halve profile time.

### Convenience / team ergonomics

- **Opt-in polars Arrow→DataFrame convenience** — not committed; capture only. qdo today has *no* DataFrame layer by design: connectors return Arrow (`fetch_arrow_batches` for Snowflake, `to_arrow_table()` for DuckDB) → `to_pylist()` → `list[dict]`, and all profiling / dist / pivot / quality compute is pushed down to SQL and run in the engine. There is **zero pandas** in the tree, so there is nothing to *migrate*; the pandas-vs-Snowflake efficiency concern (implicit conversion) is already avoided at the Arrow fast path. The only gap polars would fill is *handing data back* for local post-processing — e.g. an `export` that goes Arrow → polars → parquet/csv without the dict round-trip, or a command path that returns a `pl.DataFrame`. Treat as an *addition*, not a replacement: a thin Arrow→polars helper behind a `[polars]` extra, lazily imported inside the function (preserving "pay for what you use"), pandas kept only as a fallback for features polars lacks. **Trigger to promote:** dogfooding surfaces a concrete "I exported and immediately wanted a DataFrame" moment. Until then, the Arrow layer already captures the efficiency win and no code is warranted.
- **Audit log / SQL history / command history** — possibly useful, but likely only if sessions do not already cover the need well enough.
- **`qdo sniff`** — detect ad hoc file types / encodings more explicitly.
- **`qdo to`** — format conversion via the engine, e.g. CSV -> Parquet.
- **`qdo catalog functions`** — surface built-in SQL functions for DuckDB and Snowflake.

---

## Notes Worth Preserving

These are not active ideas by themselves, but they are useful filters for future planning:

1. **Prefer one mechanism over two.** If workflows can express a thing, avoid inventing a second parallel extension system.
2. **Prefer files over services.** Sessions, bundles, workflows, reports, and metadata should stay file-native unless there is overwhelming evidence otherwise.
3. **Prefer deterministic improvements over cleverness.** Better defaults, summaries, status signals, and next-step hints beat speculative AI features.
4. **Preserve "pay for what you use."** New features should not impose startup, install, or runtime costs on users who do not use them.
