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
