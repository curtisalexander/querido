# Ideas

Unimplemented ideas from earlier planning. Not committed to — just possibilities.

> **Active work lives in [PLAN.md](PLAN.md).** This file is the speculative / research archive: competitive analysis, format research (TOON, tokenization), architecture notes (Rust/WASM, MCP), and features that haven't been promoted to a plan yet. Items move from here into PLAN.md when we commit to building them. Don't work from this file directly — use PLAN.md for the current todo list.

---

# Strategic direction: agent-first data exploration tool

Research notes from comparing querido to qsv, datasette, visidata, harlequin, duckdb CLI (2026-04-13).

## What we are (positioning)

Querido sits in a niche between:
- **qsv** ([github.com/dathere/qsv](https://github.com/dathere/qsv)) — 50+ commands, CSV/Parquet/Excel-centric, Rust+Polars, streaming, row-oriented. As of v19 (2026-04-06) is "AI-native" with an `qsvmcp` binary.
- **datasette** ([datasette.io](https://datasette.io/)) — web-first SQLite/Parquet explorer, 90+ plugin ecosystem, publish-and-share workflow.
- **visidata** ([visidata.org](https://www.visidata.org/)) — interactive terminal spreadsheet multitool, keyboard-driven EDA.
- **harlequin** ([harlequin.sh](https://harlequin.sh/)) — SQL IDE for the terminal (DuckDB/SQLite/Postgres/MySQL), editor+catalog+results.
- **duckdb CLI** — SDK/shell, no opinions about workflow.

**Querido's differentiator:** CLI-native, multi-backend (SQLite/DuckDB/Snowflake/Parquet), agent-grade JSON, metadata-aware, tiered profiling for wide tables, and "pay for what you use" extras. We are the only one in this list that goes deep on **Snowflake** and on **compounding metadata** across sessions.

## Lean into (differentiate)

1. **Agent-first, but not agent-only.** qsv just added MCP — we can leapfrog by treating agents as the primary user from the ground up (not as a wrapper retrofitted onto a human CLI). This means: stable flags, structured errors with codes, next-step hints in output, coherent command chains, idempotent commands.
2. **Metadata that compounds.** The `.qdo/metadata/<conn>/<table>.yaml` system is unique. Lean into it: auto-merge across commands, embed-based semantic search (already in ideas), metadata lineage, and `qdo metadata suggest` (let an agent propose descriptions from profile results).
3. **Snowflake depth.** Nobody else in this list treats Snowflake as a first-class backend. Cortex Analyst YAML generation, lineage graphs, RESULT_SCAN chains, warehouse cost awareness in output.
4. **Tiered profiling for wide tables.** Quick mode + classify + column sets is genuinely novel vs. qsv's `stats` and datasette's facets. Push further: per-column-set profiles saved as named snapshots agents can diff.
5. **Coherent command chains.** `catalog → context → metadata → query → assert` is a named, teachable pattern. Nobody else has this.

## What NOT to do

- **Don't become qsv.** Row-oriented CSV wrangling (filter/slice/sort/join/apply/fetch/geocode/luau scripting) is their turf and they are in Rust. We query databases; we don't transform row streams.
- **Don't become datasette.** Publishing, hosting, and a plugin ecosystem are an enormous ongoing commitment. Our `serve` should stay a thin local UI, not a platform.
- **Don't become harlequin.** We already have a TUI via `explore`; turning it into a full SQL IDE (multi-buffer tabs, CodeMirror-style editor, saved workspaces) is scope creep away from the agent story.
- **Don't rewrite in Rust.** See performance section below. Our hot path is DuckDB/Snowflake, which are already native.
- **Don't add a plugin system yet.** Datasette has 90+ plugins because it's been at it since 2017. Adding hooks prematurely locks us into an API before we know the shape.
- **Don't add AI-powered natural-language-to-SQL inside querido.** Let the agent (Claude, Cursor, Continue) do that, using our outputs as context. We are the eyes and hands; the LLM is the brain. (`qdo ai` remains in ideas but low priority.)
- **Don't bloat `qdo freshness`-style heuristics into "smart" commands that guess intent.** Agents prefer predictable tools.

## Ideas adopted from the competitive landscape

### From qsv
- **[HIGH VALUE, LOW COST] Tool discovery / self-documentation output.** qsv uses BM25 over tool descriptions so an agent can do `qsv_search_tools("find duplicates")`. We already have `qdo overview -f json`; add `qdo search "<intent>" -f json` that ranks our 27 commands against the phrase. Pure local, no embeddings needed.
- **Audit log.** qsv has `qsv_log` so agents leave a trail. A `--audit-log FILE` flag (or `QDO_AUDIT_LOG` env) that appends JSONL of every command+args+duration+row_count would be useful for debugging agent sessions and for reproducibility.
- **`qdo sniff`** — detect file type/encoding/delimiter for paths passed as ad-hoc sources (Parquet vs CSV vs JSON). Already partly covered by connector autodetection, but surfacing it as a command helps agents.
- **`qdo to`** — convert between formats via the engine (e.g., CSV→Parquet via DuckDB COPY). Small command, useful glue.

### From datasette
- **Facets / value distributions alongside previews.** Datasette shows top-N values for low-cardinality columns next to any query result. Our `dist` does this on demand; consider an auto-facet in `preview --facet` for the top 3 low-cardinality columns. Useful for agents to understand a slice without a second call.
- **Custom SQL functions surfaced in catalog.** Datasette's `datasette-jellyfish` (fuzzy match) and `datasette-haversine` are loaded into SQL. We could surface DuckDB's rich built-in functions (`regexp_matches`, `list_*`, `struct_*`) in `qdo catalog functions` so an agent discovers them.
- **Enrichments pattern.** Not copying the plugin model, but the idea of "run a transform over every row" could inform a `qdo apply` — though this veers into qsv territory and likely should not be done.

### From visidata
- **In-terminal histograms.** Our `dist` outputs numbers; a small sparkline-style histogram in rich mode (not json) would make the TUI and rich output more useful for humans without affecting agent paths.
- **Frequency-aware column ranking.** VisiData highlights high-variance / interesting columns first. Our profile/quality already computes this; could add a `--rank` flag that orders output by "interestingness" (non-null, non-constant, moderate cardinality).

### From harlequin
- **SQL history.** Harlequin keeps a local history file. `~/.qdo/history.jsonl` of executed queries (with conn, duration, row_count, status) would help agents learn what's been tried and help humans recall past work. Tiny to implement.
- **Data catalog sidebar UX.** Our TUI `explore` could borrow this layout pattern. Not urgent.

---

## Token efficiency for LLM/agent output

**This is high priority.** JSON is verbose; every token costs latency and money in an agent loop. Research:
- CSV uses ~56% fewer tokens than JSON for tabular data ([David Gilbertson](https://david-gilbertson.medium.com/llm-output-formats-why-json-costs-more-than-tsv-ebaf590bd541)).
- **TOON** (Token-Oriented Object Notation, [toon-format/toon](https://github.com/toon-format/toon)) uses ~40% fewer tokens than JSON and scores *higher* accuracy (74% vs 70%) in agent benchmarks because its explicit row counts and column order reduce misalignment.
- Markdown-KV topped one accuracy study at 60.7% ([improvingagents.com](https://www.improvingagents.com/blog/best-input-data-format-for-llms/)).

### Proposed: `qdo ... -f agent` (or `-f compact`)

> **[IMPLEMENTED — Phase 2.1.]** `-f agent` ships as a TOON-for-tabular / YAML-for-nested hybrid. `QDO_FORMAT=agent` sets the default. See `src/querido/output/envelope.py::render_agent` + `src/querido/output/toon.py`.

A new output format tuned for LLM consumption:

- **Tabular results** → TSV or TOON (pick one; TOON is more future-proof and preserves types)
- **Metadata/schema** → compact YAML-ish key:value (not JSON) with no quoting noise
- **Headers** → minimized; use short keys (`n` for row_count, `d` for distinct, etc.) with a legend printed once per session or documented in `qdo overview`
- **Error objects** → single-line: `ERR TABLE_NOT_FOUND path=...`
- **Omit redundant fields** — don't repeat table/connection name on every row when it's in the header

**Implementation sketch:**
- Add `AgentFormatter` next to existing JSON/rich/csv formatters.
- `export QDO_FORMAT=agent` → default for agent sessions.
- Benchmark: pick 5 representative commands and measure tokens via tiktoken for `-f json` vs `-f agent`. Target 50%+ reduction.

Follow-up ideas:
- **Pagination by default for wide outputs** — agent format caps at N rows (configurable) and emits `... +K more rows (use --limit to expand)`. JSON format keeps full output for programmatic consumption.
- **Token budget flag** — `--max-tokens 500` that trims output to fit. Complex but powerful for in-loop use.

Docs needed: a "writing for agents" page explaining the legend and how to reconstruct full data.

### Is TOON actually accurate? (follow-up research, 2026-04-13)

> **[IMPLEMENTED — Phase 2.1.]** Verdict adopted: TOON for tabular, YAML for nested. Encoder is vendored in-tree under `src/querido/output/toon.py` with 118 parametrized conformance cases in `tests/test_toon.py`.

The headline "40% fewer tokens + higher accuracy" oversells it. Digging in:

- **Official benchmark** ([toonformat.dev/guide/benchmarks](https://toonformat.dev/guide/benchmarks)): 76.4% vs JSON 75.0% — a 1.4pt edge, essentially a wash on accuracy, real win on tokens (~40%).
- **Tabular / uniform array "sweet spot":** ~90.5% accuracy. This is our bread and butter — `catalog`, `preview`, `profile`, `dist`, `values` all return uniform rows. TOON should win cleanly here.
- **Nested data:** TOON ranks *last* at 43.1% vs YAML 62.1%, Markdown 54.3%, JSON 50.3% ([independent critique](https://dev.to/ikaganacar/toon-benchmarks-a-critical-analysis-of-different-results-5h66)). Our `context` and `metadata show` are nested — TOON would be a bad fit.
- **Model-dependent:**
  - Claude Haiku: TOON 59.8% vs JSON 57.4% (small TOON win)
  - Gemini Flash: TOON 96.7% vs JSON 97.1% (JSON slight win)
  - GPT-5 Nano: TOON 90.9% vs JSON 89.0%
  - Results vary by ~2pts per model — the format effect is small relative to model variance.
- **Tokenizer-dependent:** reported token savings (30–60%) depend on which tokenizer you measure with. Anthropic's tokenizer may not give the same numbers as OpenAI's.

**Verdict:** TOON is worth adopting for our **tabular** outputs (most of them) where it's both more compact and at least as accurate. For **nested** outputs (`context`, `metadata show`), use YAML — it beat TOON, JSON, and Markdown on nested data, and is already our metadata format on disk.

**Concrete proposal for `-f agent`:**
- Tabular results (rows): TOON
- Nested/hierarchical results (schema trees, metadata with valid_values, etc.): YAML
- Scalar/status results (assert pass/fail, single counts): one-line `key=value key=value`
- Errors: one-line `ERR CODE key=value message="..."`

This is hybrid on purpose — it matches format to shape, which is the actual accuracy driver.

### Recording agent output and reading it back into other subcommands

> **[IMPLEMENTED — Phase 1.2 + 6.1.]** `qdo session start`, `QDO_SESSION=<name>` auto-recording, `qdo session show`, `qdo session note`, and `qdo report session <name>` (single-file HTML narrative) all ship. The `--from session.step_N` cross-reference flag is still deferred. See `src/querido/core/session.py`, `src/querido/cli/session.py`, `src/querido/core/report.py::build_session_report`.

Yes, genuinely valuable — and it's the right way to think about the CLI as a pipeline, not a set of independent commands.

**Today:** `-f json` is round-trippable. You can `qdo catalog -c db -f json > cat.json` and a subsequent tool (or command) can parse it. We don't currently have commands that *accept* querido's own output as input, but agents effectively do this by re-reading stdout.

**Is TOON round-trippable for this?** Yes — there's a TypeScript SDK and the grammar is small enough to parse in Python. But JSON is universal and free; TOON is a second dependency. For **agent-to-agent** context passing (stuff we expect an LLM to read), TOON's compactness wins. For **tool-to-tool** piping where a human or script is the reader, JSON is strictly better.

**Recommendation:**
- Keep `-f json` as the canonical machine-readable format (unchanged).
- Add `-f agent` as the LLM-optimized format (TOON/YAML hybrid above).
- Design any future `--input FILE` flags to accept `-f json` — it's the lingua franca. Don't parse TOON as input.
- Design commands so agent workflows don't *need* to pipe structured output between them — the metadata system is the persistence layer (written once by one command, read by any subsequent command). This is a better primitive than file-piping because it survives across sessions, and it's already in place.

**Higher-leverage idea from this question:** a `qdo session` concept — a named work unit that records every command run, its output, and lets later commands reference prior results by step number. Like Snowflake's `RESULT_SCAN` but at the CLI level. E.g., `qdo catalog -c db --session investigation1` then `qdo context --from investigation1.step1 --table orders`. Compounds nicely with the audit-log idea. Medium-effort, high agent-value. Add to quick-wins list at medium priority.

---

## MCP server

> **[DEFERRED.]** Tracked in PLAN.md "Deferred / future phases" as a thin wrapper over the CLI. Not started; CLI surface is kept MCP-ready (stable flags, structured JSON errors, no TTY-required behaviors).

Preference: **only a thin wrapper over the CLI, if at all.**

**What it would take** (via [FastMCP](https://github.com/jlowin/fastmcp), stdio transport):
- A small `querido-mcp` entry point (optional extra: `uv pip install 'querido[mcp]'`) that:
  - Exposes each qdo subcommand as an MCP tool by reading our Typer command tree
  - Forwards args/flags verbatim, returns stdout as text (agent format preferred)
  - Structured errors from stderr
- Lazy tool loading (qsv's trick): only expose 5–8 core tools initially (`catalog`, `context`, `query`, `assert`, `metadata_show`, `search_tools`) and let agents discover the rest via a BM25 `qdo_search_tools`. qsv reports ~80% token reduction from this.
- Effort estimate: ~1–2 days for a minimal version, ~1 week for polish (auth passthrough, working directory, result size caps).

**Reasons to do it:** Claude Desktop and other MCP clients become first-class. qsv just shipped this (2026-04-06) and is making noise about it. Standing still loses mindshare.

**Reasons to skip:** MCP tools are often just shells over existing CLIs. If the CLI is good enough (clear flags, JSON output, discoverability), agents that can call shell already work. An MCP server is additional maintenance for a marginal win over `Bash(qdo ...)`.

**Recommendation:** defer, but keep the CLI surface MCP-ready (stable flag names, structured JSON errors, no TTY-required behaviors). Then a thin wrapper becomes trivial if demand materializes. **Don't fork a `qdomcp` binary with divergent UX.**

---

## Rust: two separate questions

> **[DROPPED.]** Both paths rejected. (a) Rust+PyO3 skipped — our hot path lives in DuckDB/Snowflake. (b) Rust→WASM skipped — if browser querido ever happens, Pyodide reuses our existing Python; a Rust rewrite would double the codebase for marginal gain.

### (a) Rust+PyO3 for CLI hot paths → **skip.**

The Rust+PyO3 pattern (Polars, Ruff, Pydantic v2) works when Python's interpreter overhead dominates — tight loops over many small objects. Typical speedups: 3–15x, up to 100x for hot inner loops ([ohadravid.github.io](https://ohadravid.github.io/posts/2023-03-rusty-python/)).

Our hot paths are:
1. **SQL execution** — already native in DuckDB/Snowflake/SQLite C code. Rust adds nothing.
2. **Template rendering** — Jinja2 is fast enough; never a bottleneck.
3. **JSON serialization of results** — could be faster with `orjson` (pure Python drop-in, no Rust work needed). One-line win if measured as a bottleneck.
4. **Concurrent fanout of per-column queries** (`core/_concurrent.py`) — bottleneck is the database, not the Python thread pool.

**Verdict:** low ROI for high complexity cost (build system, per-platform wheels, contributor barrier). If a hot path shows up in benchmarking, first try `orjson`, `pyarrow` zero-copy, or pushing more work into SQL. Revisit only if a profiler identifies a clear Python-side bottleneck — which is unlikely given DuckDB/Snowflake do the heavy work.

### (b) Rust → WASM for in-browser querido → **considered carefully; the better path is Pyodide, not Rust.**

**The compelling use case:** a "try querido on your data, zero install, nothing leaves your browser" experience. Upload a Parquet or CSV, get `context`/`profile`/`quality`/`catalog` output. Good for marketing/adoption, good as an embeddable widget in data catalogs, good for privacy-sensitive data.

**The reality check:**

- **DuckDB-WASM already exists** ([motherduck.com/blog/duckdb-wasm-in-browser](https://motherduck.com/blog/duckdb-wasm-in-browser/)). The engine is solved. Whatever we ship in-browser would sit on top of it.
- **Datasette-lite already exists** ([github.com/simonw/datasette-lite](https://github.com/simonw/datasette-lite)) — the full Python Datasette server compiled to WASM via Pyodide. Proof that our model (Python orchestrator + SQL engine) can run in-browser without any Rust rewrite.
- **DuckDB Python client itself compiles via Pyodide** ([duckdb.org/2024/10/02/pyodide](https://duckdb.org/2024/10/02/pyodide)). So querido's Python code + DuckDB could, in principle, run in-browser *today* with no rewrite.
- **Snowflake can't run in-browser.** Half the product (the differentiated half) is gone. Browser querido = DuckDB + Parquet/CSV only.
- **A Rust rewrite would mean maintaining two codebases** (Python CLI for real use + Rust WASM for the browser demo), every command implemented twice. For a tool of querido's scope, this is a years-long tax.

**Three feasible paths, ranked:**

1. **Pyodide bundle** (`querido-lite`): static site, Pyodide + DuckDB-WASM + querido Python, Parquet/CSV drag-and-drop. Payload is ~10MB (Pyodide is heavy) but acceptable for a "try it" page. Reuses all our existing code. **~1–2 weeks for a demo site.** This is the path if we want browser querido.
2. **Thin JS wrapper over DuckDB-WASM** that reimplements just the most-viewed commands (`context`, `profile`, `quality`, `catalog`) in TypeScript. Smaller payload (~1–2MB), fast startup, but it's a second implementation to maintain. Only worth it if the Pyodide payload is unacceptable in practice.
3. **Full Rust rewrite of querido core → WASM.** Most compelling technically (smallest payload, fastest, same code runs natively via PyO3). But enormous effort, unclear differentiation vs. DuckDB-WASM directly, and kills our iteration velocity. **Not recommended.**

**Is it compelling?**
- As a product feature: **moderately** — datasette-lite, observable notebooks, and [DuckDB shell on the web](https://shell.duckdb.org) already cover "SQL in browser." Our angle would be "metadata-aware exploration, not just SQL" — profile/quality/context views.
- As an adoption/marketing play: **yes** — a one-click "try qdo" page with a sample Parquet dramatically lowers the try-it friction. This is probably the strongest reason to invest.
- As a differentiator vs qsv/datasette: **weak** — datasette-lite exists; qsv has a Web Beta ([qsv.dathere.com/web](https://qsv.dathere.com/web)). We'd be catching up, not leading.

**Recommendation:** if/when we pursue browser, do **Pyodide, not Rust**. Build a `querido-lite` static site that embeds our existing Python. Defer unless we have a concrete adoption or embedding use case pulling for it. **Don't do a Rust rewrite for WASM.**

---

## Agent tutorial: separate from skill file?

> **[IMPLEMENTED — Phase 4.5 + Wave 3.]** Both artifacts kept and deepened. `qdo tutorial agent` survives for human+agent pairing; `SKILL.md` is the agent-context reference. The "playbook doc" idea is partially covered by `WORKFLOW_AUTHORING.md` + bundled workflows serving as the worked-example corpus. Self-hosting eval (`scripts/eval_skill_files.py`, `scripts/eval_workflow_authoring.py`) is the quality signal — 33/33 on the first live baseline.

We already have `qdo tutorial agent` (13 lessons) and `integrations/skills/SKILL.md`. Different purposes:

- **SKILL.md** — reference dropped into the agent's context. Static. Tells the agent *what* commands exist and *when* to use which. This is the right artifact for "teach an agent how to use querido."
- **tutorial agent** — interactive, step-by-step, runs actual commands against a sample DB. Good for humans learning alongside an agent, or for a human verifying the agent understands.

**Gap to consider:** a **playbook doc** (not interactive, not reference) — "How to answer common questions with querido." E.g., *"How do I check if table X is fresh?"*, *"How do I find the join key between two tables?"*, *"How do I validate a migration didn't change row counts?"* Each entry is a named recipe with the exact command sequence. This is different from SKILL.md's command listing and would be genuinely useful for agents. Could live at `integrations/playbooks/agent-recipes.md`.

**Recommendation:** don't duplicate the skill file. Add a recipes doc instead. Low-cost, high-value.

---

## High-value quick wins (implementable now)

> **[SUPERSEDED.]** This list was revised by the "Consolidated quick-wins" further down, then by "Updated consolidated quick-wins". Item 1 (`-f agent`) shipped as Phase 2.1. Items 2–6 (`qdo search`, SQL history, audit log, recipes doc, `qdo catalog functions`) remain deferred — see PLAN.md "Deferred / future phases".

Ordered by (value / effort):

1. **`-f agent` output format** — TOON or compact TSV+YAML hybrid. Biggest differentiation for agent use. ~2–3 days.
2. **`qdo search "<intent>"`** — BM25-style ranking over our 27 commands' docstrings. No external dependency (simple scoring in Python). Helps discovery. ~half day.
3. **SQL history log** — append `~/.qdo/history.jsonl` for every `query`/`assert`/`pivot`. ~2 hours.
4. **Audit log flag** — `QDO_AUDIT_LOG=path.jsonl` captures every command invocation. ~2 hours.
5. **Agent recipes doc** — 10–15 named playbooks. ~half day.
6. **`qdo catalog functions`** — list DuckDB/Snowflake SQL functions so agents know what's available. ~half day.

Items 1–4 could be a single 1-week push that meaningfully sharpens the agent story before qsv's MCP work becomes the default answer.

---

---

# Pit of success: making the next step obvious

Framing: a user (human or agent) should never be stuck wondering "what command do I run next?" The tool itself should carry that knowledge. Every output is a jumping-off point, not a dead end. This is the single biggest lever we have over qsv/datasette/harlequin — they are toolkits; we can be a *workflow*.

The principles below are the unifying theme. Individual ideas slot under them.

## Principle 1 — Every output ends with a pointer to the next step

> **[IMPLEMENTED — Phase 1.1.]** Every scanning command emits `next_steps`; errors emit `try_next`. See `src/querido/core/next_steps.py` and the `_ENVELOPE_CASES` contract test in `tests/test_next_steps.py`.

**`next_steps` field in every JSON response.** A ranked list of commands the caller is likely to want, based on what was just returned. Not prose — concrete invocations.

Examples of what this looks like in practice:

- `catalog` returns 50 tables → `next_steps: [{"cmd": "qdo context -c mydb -t orders", "why": "largest table (50k rows)"}, {"cmd": "qdo metadata list -c mydb", "why": "23/50 tables have no metadata"}]`
- `quality` finds `status` column with 12 distinct values and 0% nulls → `next_steps: [{"cmd": "qdo values -c mydb -t orders -C status", "why": "small distinct set — likely an enum, capture as valid_values"}]`
- `joins` returns 3 candidate join keys → `next_steps: [{"cmd": "qdo query -c mydb --sql \"select count(*) from a join b on a.user_id=b.user_id\"", "why": "validate top candidate"}]`
- `query` against a table with no metadata → hint to run `metadata init`
- Any error → `try_next` alternatives (`TABLE_NOT_FOUND` → `qdo catalog --pattern <fuzzy>`)

**Implementation:** a small `NextSteps` helper per command that knows the shape of its own output and the typical follow-ups. Keep it deterministic — no LLM needed. Agents get predictable graph edges to traverse; humans see a visible trail.

**Token cost:** 2–4 lines of compact JSON per call. Worth it.

## Principle 2 — Sessions as first-class, not a flag

> **[IMPLEMENTED — Phase 1.2 + 6.1.]** Session MVP ships (`.qdo/sessions/<name>/steps.jsonl` + per-step stdout). `QDO_SESSION` auto-records. `qdo session show/list/start/note`. The `--from session.stepN` cross-reference and `qdo session replay` are still deferred.

Expanding line 128's `qdo session` from a paragraph into the centerpiece.

A **session** is a named directory under `.qdo/sessions/<name>/` that captures every command, its args, stdout, stderr, duration, exit code, and any metadata writes. It is:

- **The audit log** (line 213's idea — collapse these into one feature, don't ship two)
- **The replay substrate** — `qdo session replay <name>` re-runs every command; diff against prior run to spot drift
- **The context for handoff** — pass a session name to Claude, and it has the full investigation trail
- **The input for `--from`** — later commands can reference earlier step outputs: `qdo query --sql-from session1.step3` uses the SQL that `sql select` generated in step 3
- **Resumable** — `qdo session resume name1` re-loads env (conn, table, column-set) from last step so `qdo context` alone works

**Auto-session for agent harnesses:** if `QDO_SESSION` is set, every command appends transparently. Agent harnesses set it once at launch. Human users opt in with `qdo session start investigate-orders`.

**Tiny implementation MVP:** a JSONL append per command, plus a `sessions/<name>/step_<n>/stdout` file. No daemon, no DB. ~1 day of work for the MVP; `--from` and `replay` are follow-ups.

**Why this is better than piping:** sessions survive across agent turns, across machines (commit `.qdo/sessions/` to a repo), and across humans-and-agents handoff. Piping requires the whole investigation to live in one shell.

## Principle 3 — Metadata is the shared memory, and commands should feed it automatically

> **[IMPLEMENTED — Phase 1.3 + 1.4.]** `--write-metadata` on `profile`/`values`/`quality` with provenance + confidence. Auto-fill rules are deterministic (low-cardinality enum → `valid_values`, high null → `likely_sparse`, temporal column names → `temporal`). Human fields (`confidence: 1.0`) never overwritten without `--force`. `qdo metadata score` + `qdo metadata suggest --apply` shipped. Metadata undo is deferred.

Today metadata is populated by `metadata init` + human edits + `refresh`. That's a cliff. Flatten it:

- **`--write-metadata` on every scanning command.** `qdo profile -t orders --write-metadata` merges computed stats (null_pct, distinct_count, min/max) into the YAML with `source: profile, confidence: 0.7`. `qdo values -C status --write-metadata` proposes `valid_values: [...]` when distinct count is small.
- **Auto-fill rules, not LLM guesses.** Low-cardinality (<20 distinct) + string type → candidate enum → write to `valid_values` with `confidence: 0.8, source: profile`. High null rate (>95%) → `likely_sparse: true`. Column name matches `*_at/*_date` + timestamp type → `temporal: true`. Deterministic, explainable, undoable.
- **Provenance on every field:** `source: human | profile | agent | inferred`, `confidence: 0–1`, `written_at: <session_id>`. Never overwrite human-authored fields without `--force`.
- **Metadata as answer cache.** An agent asks "what are valid statuses?" once, the answer lives in metadata, subsequent `context` calls include it for free. Don't re-query what we already know.
- **`qdo metadata score`** — a completeness score per table and per-connection. Tells an agent which tables need attention before writing SQL. "Pit of success" pressure without being preachy.
- **`qdo metadata suggest`** — takes recent profile/quality/values output and proposes metadata additions as a diff to review. Non-interactive `--apply` mode for agent loops.
- **Metadata undo.** `qdo metadata undo -t orders` reverts the last write, keyed on session_id. Makes aggressive auto-fill safe.

This turns metadata from a separate chore into a byproduct of normal exploration. The more the user/agent uses qdo, the richer the metadata gets, which makes the next agent's SQL-writing better. That's the compounding loop.

## Principle 4 — A visible command graph agents can traverse

> **[DEFERRED.]** Partial coverage exists via per-command `next_steps` (Principle 1) and the `qdo overview` command reference, but `--graph`, `qdo next`, and `qdo explain <command>` are not shipped.

**`qdo overview --graph -f json`** returns the command DAG: nodes are commands, edges are typical transitions, each edge annotated with the trigger (`if row_count > 1M → suggest --sample`). An agent can load this once at session start and plan.

Complements existing `overview`; doesn't replace it. Static data, trivial to maintain.

**`qdo next`** — given current session state (last command + output signature), suggest what to run next. Useful at the keyboard, trivial for agents to poll.

**`qdo explain <command>`** — not `--help` text; a short "when to reach for this" with one-line examples and predecessor/successor commands. Complements SKILL.md but lives with the binary so it's always current.

## Principle 5 — Investigations as named workflows

> **[FOLDED INTO Phase 4.]** Principle 11's workflows absorbed this — bundled workflows under `src/querido/workflows/` are how canonical investigations are expressed and shared. A dedicated `qdo investigate <table>` convenience command is still deferred; it would be a thin wrapper around `qdo workflow run` for a specific bundled workflow.

`qdo investigate table <name>` runs the canonical loop: `catalog → context → profile --classify → quality → joins` and writes a consolidated agent-friendly report plus auto-metadata updates. One command, correct defaults, reproducible.

Other canned investigations:
- `qdo investigate freshness -c mydb` — loop over all tables, detect timestamp columns, compute staleness, write to metadata
- `qdo investigate migration --source v1 --target v2` — row-count diff, schema diff, value-distribution diff on key columns
- `qdo investigate join -t a -t b` — candidate keys + validation queries + cardinality check

These are not magic; they're named scripts baked in. The value is that the *name* is the documentation. An agent hears "check migration safety" and maps to a single command. This is where qdo becomes opinionated in a way that competitors are not.

## Principle 6 — Progressive disclosure and cost awareness

> **[DEFERRED.]** All four items (`--level 1..3`, `--estimate`, read-only-by-default on `query`, `--plan` dry-run) are in PLAN.md's deferred list. Read-only-by-default is the highest-leverage next pick.

- **`--level 1..3`** on expensive commands. Level 1 is schema-only (free/cached), level 2 is profile (one scan), level 3 is full quality + joins + value frequencies (multi-scan). Agents start cheap, drill in only where needed.
- **Cost/time estimate before running.** `qdo query --estimate` returns predicted credits (Snowflake) / duration (DuckDB via EXPLAIN cardinality) / bytes scanned. Agents can set a policy: skip if >$0.10.
- **Read-only by default.** `qdo query` refuses DML/DDL without `--allow-write`. No accidental agent mutation. Show this in the output so users know the guardrail exists.
- **`--plan` / dry-run** on `export`, `query`, `metadata write` — preview without executing.

## Principle 7 — Change detection across time

> **[PARTIAL.]** `qdo diff` ships for schema comparison between two tables (see `src/querido/cli/diff.py`). The time-aware variants — `qdo diff --since <session|timestamp>` and `qdo cache snapshot` — are deferred.

- **`qdo diff --since <session|timestamp>`** — what tables appeared, disappeared, gained/lost columns, changed row counts since a prior session. Uses cache snapshots. Returning agent immediately knows what's new.
- **`qdo cache snapshot <name>`** — freeze a schema+row-count snapshot. `qdo diff --since snap:release-42` for release-boundary comparison.

This is one of the best agent UX wins: a returning agent that already knows a DB should not re-explore from scratch.

## Principle 8 — Stable identifiers for outputs

> **[DEFERRED.]** `result_id` and `--from-result` not shipped. The session substrate (Principle 2) covers the "reference a prior output" use case at a coarser granularity.

Every structured output carries a `result_id` (hash of command + args + connection + schema_version). Later commands can reference it (`--from-result <id>`), and sessions use it to deduplicate replays. Cheap to generate, enables the `--from` patterns above.

---

## Consolidated quick-wins (supersedes the list higher in this file)

> **[LARGELY IMPLEMENTED.]** 1–5 shipped (Phases 1.1, 1.2, 1.3, 1.4, 2.1). 6 (`qdo investigate`) is deferred as a thin wrapper over bundled workflows. 7 (`qdo diff --since`) and 8 (`--estimate`) are in PLAN.md's deferred list. See "Updated consolidated quick-wins" further down for the revised list with items 9–11 (report table, bundles, workflows).

Ordered by leverage on the pit-of-success story:

1. **`next_steps` field in every JSON output** — 2–3 days. Biggest single UX lever; unlocks the rest.
2. **`qdo session` MVP** (append JSONL per command, `QDO_SESSION` env) — 1 day. Collapses the audit-log and history-log ideas into one.
3. **`--write-metadata` on `profile`, `values`, `quality`** with provenance + confidence — 2–3 days. Starts the compounding loop.
4. **`qdo metadata score` + `qdo metadata suggest`** — 1 day combined. Gives agents a target to work toward.
5. **`-f agent` format (TOON/YAML hybrid)** — already in quick-wins; keep at priority. 2–3 days.
6. **`qdo investigate table <name>`** — 1 day for the canonical loop; lives on top of existing commands.
7. **`qdo diff --since <session>`** — 1–2 days; requires snapshot machinery but high return for returning agents.
8. **Cost/time `--estimate` flag on `query` / `export`** — 1 day for DuckDB, more for Snowflake. Safety rail with real teeth.

Items 1–4 together are the project's competitive moat: they make qdo the tool that **gets better as it's used**, which neither qsv nor datasette has. If we pick one week of work, it is these four.

## Things to resist under this framing

- **LLM-in-the-loop suggestions.** All "next step" and metadata auto-fill logic stays deterministic. Agents bring the brain; we bring the memory and the map. The minute we embed an LLM in the suggestion path we inherit eval burden and model drift. Keep rules simple and inspectable.
- **Clever sessions.** No server, no state machine, no reconciliation. Append-only JSONL + directory of outputs. If it can't be cat'd and grepped, it's too clever.
- **Opinions outrunning evidence.** Canned investigations are valuable only if they encode patterns we've seen work. Resist adding `qdo investigate X` commands speculatively; add one when we've watched an agent or human do the same three-command sequence twice.

---

# Sharing: learnings compound across a team, not just one session

Metadata + sessions are already valuable to one user. They get dramatically more valuable when **team members can import each other's work**. This is the network effect qsv/datasette/harlequin don't have at all — they don't capture investigation state, so there's nothing to share. We do. Lean in.

## Principle 9 — Knowledge bundles as the unit of exchange

> **[IMPLEMENTED — Phase 3.]** `qdo bundle export/import/inspect/diff` all ship. Schema-fingerprint checks catch drift on import; merge strategies preserve provenance (auto-fills break ties by confidence + recency; human `confidence: 1.0` fields never auto-overwritten). See `src/querido/core/bundle.py` and `src/querido/cli/bundle.py`.

A **knowledge bundle** is a portable archive of what one user/agent has learned about some part of a database. It should be:

- **A single file** (`.qdobundle`, a zip/tar) or a directory that can be committed to a repo
- **Connection-agnostic** — references tables by a schema fingerprint, not by the local connection name. Bob imports Alice's `orders.qdobundle` into his own connection where `orders` may live under a different name
- **Versioned against schema** — each table's metadata records the `schema_fingerprint` it applies to (hash of column names + types). On import, qdo warns if the local schema has drifted
- **Provenance-preserving** — every field carries `source`, `confidence`, `written_at`, and now `author` (git user or env var `QDO_AUTHOR`). Imports never silently overwrite higher-confidence local fields
- **Partial** — Alice can export metadata for 3 tables, or just the enum `valid_values` she confirmed, without shipping her whole `.qdo/` directory

**Commands:**
- `qdo bundle export -c mydb -t orders,customers -o knowledge.qdobundle` — package metadata + optional session(s) + saved column-sets + saved workflows
- `qdo bundle import knowledge.qdobundle --into mydb` — preview diff by default; `--apply` writes; `--strategy [keep-higher-confidence|theirs|mine|ask]`
- `qdo bundle diff local.qdobundle remote.qdobundle` — show what would change
- `qdo bundle inspect knowledge.qdobundle` — summary: N tables, M columns with metadata, included sessions, authors, created_at

**Merge semantics (the only hard part):**
- Auto-fill fields (confidence < 1.0) — take the higher-confidence value, break ties by newest
- Human-authored fields (confidence = 1.0) — never auto-overwrite; surface as a conflict for review
- `valid_values` lists — union by default, configurable
- Record the import itself in the session log so provenance survives the handoff

**What's in a bundle:**
```
knowledge.qdobundle/
  manifest.yaml         # author, created_at, qdo_version, contents
  metadata/
    orders.yaml         # with schema_fingerprint, provenance per field
    customers.yaml
  workflows/            # optional — shared workflows (see Principle 11)
    migration-check.yaml
  sessions/             # optional — sanitized session exports (see Principle 10)
    q1-close.html
  column-sets/          # optional
    orders.default.yaml
```

**Team registry pattern (no platform needed):** a plain git repo `company-qdo-knowledge/` holds bundles. `qdo bundle import github.com/acme/qdo-knowledge#orders` is sugar for "clone + import that path." No server, no auth beyond git. This is datasette-style sharing without the datasette-style hosting commitment.

**Privacy guardrail:** bundles never include raw row data unless the user explicitly opts in. `sample_values` is fine for enums; drop it for PII-flagged columns by default. `--redact` strips anything tagged `pii: true` in metadata.

**Why this matters:** the agent that inherits a well-populated bundle writes better SQL on its first call than an agent starting cold would on its tenth. Shipping that handoff as a file is the whole game.

---

# Reporting: make the output shareable with humans who don't use qdo

The agent and the analyst know the data. Their stakeholders don't. We should make it trivial to hand a PM, exec, or non-technical teammate a polished artifact that answers "what did you find out about this table?" — without asking them to install anything.

## Principle 10 — HTML report as the shareable primitive

> **[IMPLEMENTED — Phase 2.2 + 6.1.]** `qdo report table` and `qdo report session` both ship as single-file HTML (no JS, inline SVG, print-friendly). `qdo report connection` multi-table overview is deferred. See `src/querido/core/report.py`, `src/querido/output/report_html.py`, `src/querido/cli/report.py`.

**`qdo report table -c mydb -t orders -o orders.html`** — a single self-contained HTML file (inline CSS, inline SVG, no CDN, no JS required for reading; small vanilla JS only for optional interactivity like sortable tables). Works offline. Opens in any browser. Easy to email, attach in Slack, commit to a repo.

Content (from one table):
- Header: table name, connection, generated at, row count
- Metadata summary: description, owner, freshness, PII flags
- Schema table: columns, types, null %, distinct counts, sample values / valid_values
- Quality callouts: columns with anomalies highlighted
- Related tables: from `joins` output, as a small graph/list
- Footer: "Generated with qdo" with a collapsed `<details>` showing the command that produced it. Subtle, not preachy

**`qdo report session -n investigation1 -o investigation1.html`** — the "what we learned along the way" artifact. Each step in the session becomes a card:
- Step title (agent-authored or command-derived)
- One-line context ("we ran this because the catalog showed 50k rows and no metadata")
- Collapsed command (`<details>` opens to show the exact `qdo ...` invocation)
- Rendered output: small table for catalog/profile, highlighted JSON for metadata, chart for distributions
- Optional commentary — if the session was run with `--note`, each step's note is rendered above its output

This is the narrative artifact. Run an investigation, share the HTML, the recipient understands the story *and* can reproduce any step. The subtle embedded commands are the nudge: "oh, I could have run this myself."

**`qdo report connection -c mydb -o overview.html`** — multi-table overview. Table list with metadata completeness, quality scores, freshness status. Good for team onboarding docs.

**Styling:** borrow from the existing TUI color scheme for brand coherence. Use a restrained, documentation-ish aesthetic — think GitHub READMEs or Stripe docs, not a dashboard. Dark mode via `prefers-color-scheme`. Print-friendly CSS so `Cmd+P → Save PDF` produces a clean handout.

**Implementation:** Jinja2 templates (we already use Jinja). One base template, one per report type. Charts via inline SVG (no dependency). ~2–3 days for a credible v1 of `report table`; `report session` is another 2 days.

**What to resist:**
- **JS-heavy dashboards.** Those are harlequin/datasette/observable territory. Our reports are *static artifacts*, not interactive apps. If the recipient wants to explore, they should install qdo.
- **A hosted viewer.** No server. File-on-disk only. This keeps the "send to a PM" story frictionless.
- **Branding that screams.** A small "Generated with [qdo](https://...)" footer and collapsed reproduction commands. The goal is that a reader notices qdo because the output is clean, not because we planted a logo on every section.

**Composition with bundles:** a session's HTML report can be dropped into a knowledge bundle, so importing `orders.qdobundle` also gives Bob a human-readable story of *how* Alice learned what she learned.

---

# Extensibility: workflows as user-authored, agent-authored, shareable extensions

The user is right to point at Claude Code's skills model: the tool ships primitives, the agent writes extensions, users share them. That pattern is *exactly* right for querido. Workflows are the extension mechanism — not plugins, not Python hooks, not an ABI. Files.

## Principle 11 — Workflows as the extensibility surface

> **[IMPLEMENTED — Phase 4.]** Workflow spec (JSON Schema), runner, lint, list, `show`, `spec --examples`, `from-session` all ship. See `src/querido/core/workflow/`, `src/querido/cli/workflow.py`, `integrations/skills/WORKFLOW_AUTHORING.md`. The "CLI sugar shim" (`qdo <workflow-name>` as a top-level alias) was **dropped** — canonical invocation is always `qdo workflow run <name>`.

A **workflow** is a declarative YAML file describing a named, parameterized sequence of qdo commands. It's:

- **Declarative, not code.** No Python, no sandbox, no RCE risk. Only `qdo` subcommand invocations, with parameters, simple conditionals (`when: row_count > 1M`), and output bindings (`capture: preview_result` → reference later as `${preview_result.row_count}`)
- **Authored by agents, polished by humans.** A coding agent reading a recent session + a documented spec can produce a workflow file. That's the Claude Code analogue
- **Shareable as a single file.** Commit it, email it, bundle it, pull from a git repo
- **Discoverable.** `qdo workflow list` shows bundled + user + project workflows with descriptions

**File shape:**
```yaml
name: check-freshness
description: "Validate that a fact table has been loaded in the last N hours"
version: 1
inputs:
  table: {type: string, required: true}
  threshold_hours: {type: int, default: 24}
  connection: {type: string, required: true}
steps:
  - id: inspect
    run: qdo inspect -c ${connection} -t ${table} -f json
    capture: schema
  - id: find_ts_col
    when: ${schema.has_timestamp_column}
    run: qdo freshness -c ${connection} -t ${table} --threshold ${threshold_hours}
    capture: fresh
  - id: alert
    when: ${fresh.staleness_hours > threshold_hours}
    run: qdo assert -c ${connection} --sql "..." --expect 0
outputs:
  staleness_hours: ${fresh.staleness_hours}
  passed: ${fresh.staleness_hours <= threshold_hours}
```

**Commands:**
- `qdo workflow run check-freshness -t orders -c mydb` — execute
- `qdo workflow list` / `qdo workflow show <name>` / `qdo workflow lint <file>`
- `qdo workflow spec -f json` — the authoritative JSON schema, so agents can author correctly without guessing
- `qdo workflow from-session <session> -o draft.yaml` — generate a first-draft workflow from the last N commands in a session, parameterizing obvious inputs (table name, connection). The agent (or human) then edits to finalize
- `qdo workflow validate <file>` — dry-run against the spec; report unresolved references, unknown commands, unsafe patterns

**Search paths (most-specific first):** `./.qdo/workflows/*.yaml` → `$XDG_CONFIG_HOME/qdo/workflows/*.yaml` → bundled. Local project overrides user overrides built-in.

**The built-in "investigations" from Principle 5 become workflows themselves.** We ship `investigate-table.yaml`, `investigate-freshness.yaml`, `investigate-migration.yaml` as bundled workflows. Users learn by reading them. They copy, modify, share. Nothing is magic, everything is inspectable. This collapses Principle 5 into a special case of Principle 11 — one mechanism, not two.

**Safety invariants:**
- Workflows may invoke only `qdo` subcommands (no shell, no network, no filesystem beyond qdo's normal scope)
- `--allow-write` must be declared in the workflow manifest for any step that can mutate (matches the query-command guardrail)
- Inputs are typed and validated before execution — no string interpolation surprises
- A workflow always runs inside a session (auto-created if none), so every run is replayable and auditable

**Authorship loop (the thing that makes this pit-of-success):**
1. User investigates table X interactively with a coding agent; session records every step
2. User: "turn what we just did into a workflow called *check-reference-integrity* that works on any fact table"
3. Agent reads the spec (`qdo workflow spec`), reads the recent session, generates `check-reference-integrity.yaml`, runs `qdo workflow lint` + `qdo workflow run` to verify
4. User commits it. Next week, teammate runs `qdo workflow run check-reference-integrity -t new_fact_table` and gets the same investigation for free
5. Team commits to a shared `company-qdo-knowledge` repo; everyone benefits

This loop is the whole feature. It only works if (a) the spec is documented well enough for an agent to author from cold, (b) sessions record enough to reconstruct intent, (c) workflows can be validated without running, (d) sharing is a copy-file operation. All four are tractable.

**Versioning:** each workflow declares `version: N` and `qdo_min_version: X.Y.Z`. Breaking spec changes require bumping the workflow version. `qdo workflow lint` enforces compatibility.

**What to resist (critical for this to stay simple):**
- **No embedded Python / scripting / lambdas.** The moment we allow arbitrary code, we inherit a security story, a sandbox story, and an ecosystem-lock-in story. Declarative + parameterized qdo calls is enough for 95% of real workflows. If someone needs more, they write a shell script that calls `qdo workflow run`
- **No plugin registry service.** Sharing is git + files. If popular workflows emerge, curate a list in README; don't build a marketplace
- **No workflow-to-workflow unlimited composition.** Allow a workflow to call one other workflow as a step (for reuse), but not arbitrary recursion. Keeps the execution graph inspectable
- **Don't ship many bundled workflows early.** Two or three that encode genuinely common patterns. Resist the urge to build a "stdlib" of workflows before watching what users/agents actually want

---

## Updated consolidated quick-wins (revises the earlier list)

> **[IMPLEMENTED.]** Items 9 (report table, Phase 2.2), 10 (bundles, Phase 3), and 11 (workflows, Phase 4) all shipped. The earlier eight items are annotated individually above. The suggested week-by-week sequencing below was followed, with `report session` landing as Phase 6.1 (2026-04-20).

The earlier eight items still stand. These three additions rank against them:

9. **HTML `qdo report table` (single file, Jinja, inline CSS)** — 2–3 days. Immediate "show it to your boss" value; low risk
10. **Knowledge bundle export/import MVP** (just metadata + column-sets; no merge strategies beyond "prompt on conflict") — 3–4 days. Unlocks team compounding
11. **Workflow spec + run + lint + from-session** — 1 week for a credible v1. Biggest long-term play; also most prone to scope creep

**Suggested sequencing if we commit to this direction:**
1. `next_steps` + sessions + `--write-metadata` + metadata score (week 1)
2. `-f agent` format + `report table` HTML (week 2)
3. Knowledge bundle export/import (week 3)
4. Workflow spec + run + `from-session` (week 4–5, with buffer for the spec to settle)
5. `report session` HTML (week 6)

This is roughly the order where each step's value is unlocked by the prior step: sessions make `report session` possible; `--write-metadata` gives bundles something worth exporting; `from-session` needs sessions to exist. The ordering isn't negotiable; the timing is.

---

## qdo freshness — row freshness / staleness

> **[DEFERRED.]** In PLAN.md's deferred list. `qdo context` already surfaces `temporal: true` metadata hints for timestamp columns; `qdo freshness` would build on that.

"Is this table still being loaded?" is one of the most common analyst questions. The agent needs to answer it without the analyst knowing the column names.

- `qdo freshness -c CONN -t TABLE [--column updated_at]`
- Auto-detect timestamp column if not specified: scan columns for date/timestamp types, prefer names matching `updated_at`, `modified_at`, `created_at`, `loaded_at`, `_date`, `_timestamp`, `_at`
- Returns table, column, min, max, now, staleness_hours, row_count
- `--threshold N` — exit code 1 if staleness exceeds N hours (agent can use for assertions)

## Snowflake RESULT_SCAN for chained queries

Commands like `template` run count → profile → sample sequentially, each re-scanning the table. Snowflake's `RESULT_SCAN()` could let later steps reuse earlier result sets. Needs research into whether the connector can hold session state across calls.

## Embedding-based semantic search across metadata

Embed table/column metadata and descriptions using an embedding model, cache embeddings locally, and do cosine similarity search to find relevant tables/columns from a natural language query.

- `qdo embed build` — generate embeddings for all table/column metadata and store in local SQLite/DuckDB
- `qdo embed search "<query>"` — cosine similarity search using numpy
- Embedding sources: table names, column names, comments, business definitions (from metadata)
- Model options: OpenAI `text-embedding-3-small` (API), or local models via `sentence-transformers`
- Cache: store embeddings as numpy arrays in local database (BLOB) or `.npy` files
- Search: pure numpy cosine similarity — no vector DB dependency needed
- Optional dependency group: `uv pip install 'querido[embeddings]'`

## Local LLM for SQL generation

Use an open-weight local LLM to generate SQL from natural language, informed by table metadata, semantic descriptions, and example queries. Must work on CPU (slow) and GPU (fast).

- `qdo ai "<question>"` command
- Feed context: table schemas, column descriptions, example queries, semantic model info
- Model options: `llama-cpp-python` for CPU/GPU inference, or `mlx` on Apple Silicon
- Optional dependency group: `uv pip install 'querido[ai]'`

## Cache-backed column resolution

`resolve_column()` queries the database for column metadata just to do case-insensitive name matching. Could check MetadataCache first and fall back to a live query if stale. Deferred because within-session memoization already covers most cases.

## Should some subcommands be workflows instead of Python primitives?

> **[DROPPED by design.]** Originally "Phase 5" in PLAN.md, then dropped. The "no workflow shim" principle prevails — agents and humans learn one invocation pattern (`qdo workflow run <name>`), not two. Subcommands that earn rule 1 or 2 (direct connection access, cross-query optimization like `context`/`quality`) stay primitives; new user-authored composition lives as workflows. The dual-surface CLI sugar alias this proposal relied on is explicitly out.

**Yes. This is a direct consequence of Principle 11** — once workflows are a first-class authoring surface, the bar for a built-in Python subcommand goes up. Anything that's "run these qdo commands in this order and format the result" should be a workflow, not hidden code.

### The decision rule

A command earns its place as a **Python primitive** if any of these are true:
1. **Direct connection/DB access it owns** — it holds a session, runs a query the workflow layer couldn't express, or negotiates a protocol (e.g., Snowflake auth)
2. **Cross-query optimization** — it fuses what would otherwise be N queries into one scan (context, quality). Losing this to a workflow would be a meaningful perf/cost regression
3. **Management / state mutation** — config, cache, metadata CRUD, session control
4. **Pure I/O or formatting** that doesn't compose — export, completion, serve

Otherwise it should be a **bundled workflow** in `workflows/` — a file shipped with querido, inspectable and forkable, executed via `qdo workflow run <name>` with a CLI sugar alias that preserves the existing command name.

### The "subcommand as sugar for a bundled workflow" pattern

This is the unlock. We don't have to remove a command to convert it — we can keep `qdo template -t orders` working while its *implementation* is `workflows/template.yaml`. Discoverability and UX stay; hidden Python goes away. The bundled file becomes a teaching artifact: users read it to learn the pattern, copy it to make their own.

Mechanism: Typer dispatcher falls back to `workflow run <name>` if no Python handler is registered. One shim, and any workflow can be a top-level subcommand. Built-ins and user-authored workflows become indistinguishable at the CLI — exactly the Claude Code skills pattern.

### Proposed classification of current commands

**Stay as Python primitives** (earn it by rule 1, 2, 3, or 4):
- `catalog`, `inspect`, `preview`, `profile`, `dist`, `values` — direct scan + fused SQL
- `context`, `quality` — cross-query fused scans; converting loses the single-scan optimization on DuckDB/Snowflake (rule 2)
- `query`, `explain`, `assert`, `export` — direct DB/IO
- `config *`, `cache *`, `metadata *` — management/state (rule 3)
- `completion show`, `tutorial`, `explore`, `overview` — fall outside workflow semantics
- `snowflake lineage` — thin SQL-function wrapper, but Snowflake-specific auth state makes it rule-1

**Convert to bundled workflows** (with CLI sugar preserving the name):
- **`template`** — explicitly runs count → profile → sample; perfect workflow. Users often want to customize the template output shape anyway; workflow makes that a file edit, not a PR
- **`sql scratch`** — composes `inspect` + `preview` + SQL assembly. Straight-line workflow
- **`sql task`** / **`sql procedure`** — Snowflake SQL-string templates parameterized by table metadata. Workflows
- **`snowflake semantic`** (Cortex Analyst YAML) — most users will want to customize the generated YAML shape. A workflow makes the generation logic visible and editable, which matters because Cortex Analyst's spec is still evolving
- **`view-def`** — if it's just `SHOW CREATE VIEW` + format, workflow. If it does more (dialect-specific reconstruction), keep
- **`pivot`** — generates GROUP BY SQL and runs it. Workflow with two steps (generate + query)
- **`joins`** — heuristic key discovery. The heuristic itself is worth making visible/editable rather than buried in Python. Workflow

**Borderline — needs a closer look before deciding:**
- **`diff`** (schema comparison) — if it's just `inspect` twice + compare, workflow. If it does smart type-coercion comparison, primitive
- **`profile --classify`** — the classification *rules* are opinions and belong in a readable file; the scan is optimized SQL. Best answer: keep `profile` primitive, move the classification *rules* into a workflow or a readable YAML the primitive loads. Makes the opinions inspectable without losing the scan perf

### Commands to remove outright (not workflow-ify)

Small list, and I'd want to confirm usage before pulling anything:
- **`qdo serve`** — already covered above
- **Deprecate the `sql` subgroup once its members (`select`, `ddl`, `scratch`, `task`, `procedure`) are workflows.** Promote `select` and `ddl` to top-level (still primitives, since they're SQL assembly from introspection). The `sql` group mostly exists to namespace string-generators; if string-generators become workflows, the group shrinks to nothing

### Why this is a win, not a loss

1. **Codebase gets smaller.** Roughly 8–10 commands move out of Python. Test surface shrinks. Contributor onboarding gets easier
2. **Opinions become inspectable.** "Why does `template` produce this shape?" stops being an answer buried in Python and becomes `cat workflows/template.yaml`. This is the same reason Claude Code ships skills as markdown, not compiled code
3. **Users get an authoring pattern for free.** Want a custom `template-for-fact-tables`? Copy the bundled one, edit. No PR, no fork, no Python
4. **The spec gets battle-tested internally first.** If 8–10 of our own commands are workflows, the spec must be expressive enough to handle real needs before any external user depends on it. This is exactly how Claude Code's skill format matured — internal use surfaced the gaps
5. **Discoverability is unchanged.** The CLI sugar means `qdo template` still works; `qdo workflow list` *also* shows `template` alongside user-authored workflows. Unifies the surface

### Risks and how to mitigate

- **Workflow-as-primitive perf regression.** Biggest real risk. Mitigation: the conversion rule explicitly excludes fused-scan commands (`context`, `quality`, `profile`). For `template` / `sql scratch` / `pivot`, run a benchmark before converting — if workflow overhead is >50ms on typical tables we redesign, not migrate
- **Workflow spec has to carry more weight.** Converting 8–10 built-ins up-front is a forcing function for the spec. If the spec can't express what `template` does today, we've learned something important before shipping. Plan for one spec revision mid-conversion
- **Breaking change risk for `--format`/`--flag` shape.** A converted command must preserve its CLI surface byte-for-byte, including JSON output shape. Snapshot tests for each converted command's output, compared against pre-conversion output, gate the migration
- **Feature gaps in workflow execution** (e.g., conditional logic, output post-processing) may surface. Track these as inputs to the spec rather than reasons to back off — the alternative is every edge case becoming new Python

### Sequencing

Fits after Principle 11 lands:
1. Workflow spec + `workflow run/lint/list` + CLI sugar shim (from Principle 11)
2. Convert **one** low-risk command first — `template` or `sql scratch` — end-to-end with snapshot tests. Validates the spec and the sugar
3. Convert the rest in priority order: `pivot`, `joins`, `sql task`, `sql procedure`, `snowflake semantic`, `view-def`
4. Only after that, revisit borderline cases (`diff`, `profile --classify` rules externalization)

This is roughly one additional week on top of Principle 11's week, assuming no spec rework. If spec gaps emerge during step 2, add a second spec-revision week before proceeding.

### What this is not

- **Not** a push to remove user-visible commands. Sugar aliases preserve every current `qdo <cmd>` invocation
- **Not** a rewrite. Python primitives that earn their place by the decision rule stay Python. Maybe 8–10 commands move; ~20 don't
- **Not** dependent on any external workflow engine. Querido's workflow runner, querido's spec, querido's files. Self-contained

---

## Agent-authoring documentation: the prerequisite for workflow extensibility

> **[IMPLEMENTED — Phase 4.5 + Wave 3 + Wave 4.]** `WORKFLOW_AUTHORING.md`, `SKILL.md`, bundled workflows as worked examples, `qdo workflow spec [--examples]` all ship. Self-hosting eval shipped twice: `scripts/eval_workflow_authoring.py` (Phase 4.6) and the broader `scripts/eval_skill_files.py` (Wave 3, 11 tasks × 3 models). Option 1 (claude -p single-shot) is what's wired; Option 2 (Agent SDK with restricted tools) and Option 3 (hermetic Docker) remain available if the doc gap shifts.

The Claude Code skills pattern only works if the agent has *everything it needs to author a correct extension on the first try*. For querido, that means a dedicated, authoritative body of documentation aimed at agents writing workflows — not aimed at humans reading prose about workflows. This is a feature, not a chore. Without it, Principle 11 degrades to "agents generate plausible-looking YAML that doesn't run."

This is the single most underestimated dependency in the whole workflow story. Put it on the critical path, not after.

### What an agent needs, specifically

1. **An authoritative spec, machine-readable** — `qdo workflow spec -f json` returns a JSON Schema for the workflow file format. Every field documented inline. No "see the docs" references. This is the thing an agent loads first
2. **A worked-example corpus** — 5–10 canonical workflows, each annotated with *why* it's shaped the way it is. Not just "here's a workflow," but "here's why this step uses `capture:` instead of a second workflow, here's why this input is typed `string` not `table_ref`, here's why this uses `assert` and not a `when:` guard." Agents pattern-match; good patterns are the teaching signal
3. **A linter whose error messages are prescriptive** — `qdo workflow lint` must return structured errors an agent can act on: `{code: UNKNOWN_CAPTURE_REFERENCE, message: "...", fix: "add capture: <name> to step 'inspect'"}`. The lint loop is where agents actually learn the spec. Every lint error is a teaching moment
4. **A "from-session" bootstrap** — `qdo workflow from-session` produces a draft that's *already structurally valid*. Agents edit/parameterize rather than author from scratch. Lowers the cold-start difficulty by an order of magnitude
5. **A negative-example section** — "here is YAML an agent commonly generates that *doesn't work*, and why." Explicit counter-examples prevent the most common failure modes. This is what's missing from most agent-docs in the wild
6. **Stable invariants the agent can rely on** — which commands accept `-c/-t/-C/-f`, which flags have changed between versions, which outputs guarantee a stable JSON shape. Agents fail when they assume a flag exists because a similar command has it. Document the uniformities and the exceptions

### What needs to change in this repo

Concrete artifacts to create or update (not speculative — this is the deliverable):

- **`integrations/skills/SKILL.md`** — extend with a "Writing workflows" section that links to the spec and lists the authoring loop (draft → lint → run → iterate). Keep the existing "using qdo" content; this is an addition
- **`integrations/skills/WORKFLOW_AUTHORING.md`** (new) — the agent-facing authoring guide. Structured as: spec reference → worked examples → common patterns → anti-patterns → lint-error catalog. This is the single file an agent loads to extend qdo
- **`integrations/continue/qdo.md`** — add a "workflows" section mirroring SKILL.md's additions, sized for Continue's rules format
- **`integrations/playbooks/agent-recipes.md`** (new, already proposed earlier in this doc) — update to include "recipe: author a workflow from a recent investigation" as one of the named playbooks
- **Bundled workflows as canonical examples** — the 2–3 workflows we ship (and the ~8 converted from subcommands) *are* the worked-example corpus. They need inline comments aimed at agents, not just humans. Every non-obvious step gets a `# why:` comment
- **`qdo workflow spec` command** — emit JSON Schema. Ship alongside `qdo workflow spec --examples` that dumps all bundled workflows as reference. Agents fetch both in one call at session start
- **`AGENTS.md` at repo root** — update to document the agent-authoring loop and point at `WORKFLOW_AUTHORING.md`. This is the file coding agents working *on querido itself* read; it needs to know workflows are a first-class extension point so future work treats them that way

### Self-hosting as the quality signal

The test of "is our agent documentation good enough?" is:

**Can a cold-start agent, given only `WORKFLOW_AUTHORING.md` + `qdo workflow spec -f json` + `qdo workflow spec --examples`, author a correct workflow for a new task on the first try?**

Run this test in CI, or at minimum before each release:
- Pick 3 target workflows the model has not seen
- Give the model only the documented context (no repo access, no internet)
- Score: does `qdo workflow lint` pass? Does `qdo workflow run` succeed on a fixture database? Does the output match expectations?

If the answer is "no," the gap is in *our documentation*, not in the model. Fix the docs, re-run. This is the same eval pattern that shipped Claude Code's skills to a usable state — self-hosted agent authoring as the acceptance test.

### What "only the documented context" means, concretely

The test is only meaningful if the agent can't cheat by reading the source code, browsing other workflows in the repo, or searching the web. If we let those in, a pass tells us nothing about whether the *documentation* is sufficient — maybe the model just read `src/querido/workflows/runner.py` and inferred the spec from it.

**What the agent is allowed to see:**
- The contents of `integrations/skills/WORKFLOW_AUTHORING.md`
- Output of `qdo workflow spec -f json` (the JSON schema)
- Output of `qdo workflow spec --examples` (the bundled worked examples — the agent *is* supposed to learn from these)
- Output of `qdo --help`, `qdo workflow --help` (public CLI surface is fair game)
- A fixture database it can run `qdo` commands against
- Its own scratch directory to write the draft workflow file

**What the agent is NOT allowed to see:**
- The querido source tree (`src/`, `tests/`)
- Other workflow files in the repo outside the `--examples` output
- `IDEAS.md`, `README.md`, `AGENTS.md`, or any other prose docs not explicitly in the authoring guide
- The internet (no WebFetch, no WebSearch, no package index)
- Any previously authored workflows from prior conversation turns (each run is a cold start)

**What the agent IS allowed to do:**
- Call `qdo workflow lint <file>` and iterate on lint errors (this is the real authoring loop; restricting it would be testing the wrong thing)
- Call `qdo workflow run <file>` against the fixture DB to verify behavior
- Read/write files in its scratch directory

### Three setup options, ranked by effort

**Option 1 — Minimum viable: Claude Code headless, single-shot.**

Shell out to `claude -p` (Claude Code's non-interactive mode) with the docs and task in the prompt. Score by running `qdo workflow lint` against the returned YAML and `qdo workflow run` against a fixture DB.

```python
import subprocess
docs = open("integrations/skills/WORKFLOW_AUTHORING.md").read()
spec = subprocess.check_output(["qdo", "workflow", "spec", "-f", "json"]).decode()
examples = subprocess.check_output(["qdo", "workflow", "spec", "--examples"]).decode()
prompt = f"{docs}\n\n# JSON Schema\n{spec}\n\n# Examples\n{examples}\n\n# Task\n{TASK_PROMPT}"

result = subprocess.run(
    ["claude", "-p", "--model", "claude-opus-4-6", prompt],
    capture_output=True, text=True, check=True,
)
# Write result.stdout to scratch/draft.yaml, then:
# subprocess.run(["qdo", "workflow", "lint", "scratch/draft.yaml"])
# subprocess.run(["qdo", "workflow", "run", "scratch/draft.yaml", ...])
```

Pros: ~20 lines of Python, no containers, no harness. Runs in CI trivially.
Cons: No lint-iterate loop — the agent gets one shot. This is a strict test; the "real" authoring loop includes iteration on lint errors.

**Billing note:** `claude -p` uses your Claude Pro/Max subscription quota. Using the Anthropic Python SDK directly (`anthropic.Anthropic().messages.create(...)`) is an alternative, but it requires a separate `ANTHROPIC_API_KEY` from console.anthropic.com with pay-as-you-go credits — the Max subscription does NOT cover SDK calls. **Gotcha:** if `ANTHROPIC_API_KEY` is set in your environment, Claude Code prefers it over the subscription and silently charges API credits. `unset ANTHROPIC_API_KEY` before running the eval to stay on Max billing. Use the SDK path only if you need fine-grained control `claude -p` doesn't expose (streaming callbacks, custom tool-use plumbing).

**Option 2 — Realistic: Claude Agent SDK with a restricted tool set.**

Use the [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk) and register *only* the tools the authoring loop actually needs. The SDK's `allowed_tools` controls what the model can call.

Allowed tools:
- A custom `qdo_workflow_lint(file)` tool that shells out to `qdo workflow lint`
- A custom `qdo_workflow_run(file, args)` tool that shells out to `qdo workflow run` against the fixture DB
- A custom `write_file(path, contents)` restricted to a scratch dir
- A custom `read_file(path)` restricted to the scratch dir

Disallowed (do not register): Read/Glob/Grep (filesystem), Bash (arbitrary shell), WebFetch, WebSearch.

The docs go in the system prompt exactly as in Option 1. The agent now has the real authoring loop — draft, lint, fix, run — but its filesystem view is a tmpdir with nothing in it except what it writes.

Pros: Mirrors real agent-authoring behavior. Exposes doc gaps that only show up during iteration (e.g., lint errors the agent can't resolve from the docs alone).
Cons: More setup (~200 lines). Need to maintain the tool shims.

**Option 3 — Hermetic: Docker container with no network.**

For the strictest version and easiest reproducibility across contributors and CI:

```dockerfile
FROM python:3.12-slim
RUN pip install querido[all]
COPY fixture.duckdb /work/fixture.duckdb
COPY WORKFLOW_AUTHORING.md /work/docs/
RUN qdo workflow spec -f json > /work/docs/spec.json \
 && qdo workflow spec --examples > /work/docs/examples.yaml
WORKDIR /work/scratch
```

Run with `docker run --network=none --rm -v $(pwd)/scratch:/work/scratch ...` and invoke the agent harness from outside the container, shipping commands in via stdin. The `--network=none` is the hermeticity guarantee: no internet, full stop. The container image has no copy of the querido source, so "no repo access" is enforced by absence, not by permissions.

Pros: Truly hermetic. Same test runs identically on every contributor's machine and in CI. Impossible for the agent to cheat
Cons: Slower (container startup), heavier lift to run, requires the agent harness to talk to a container over stdio. Worth it for release gates; overkill for day-to-day

### Recommended path

Start with **Option 1** during the workflow-spec-drafting phase — cheapest, fastest feedback, catches the biggest doc gaps. Move to **Option 2** before the first public release of workflow support, because the real doc gaps show up during the lint-iterate loop and Option 1 can't test that. Keep **Option 3** available for release-gate CI runs; don't require it for every PR.

### Scoring

Per target task, a run passes if all three are true:
1. `qdo workflow lint draft.yaml` exits 0
2. `qdo workflow run draft.yaml <params>` exits 0 against the fixture DB
3. The output matches a golden file (for deterministic tasks) or a schema-level check (for non-deterministic tasks like "profile this table")

Track pass rate per model and per task over time. If pass rate drops after a docs change, something regressed. If pass rate is stuck below ~80% for the frontier model, the docs are the bottleneck.

### Sequencing note

This work parallels Principle 11's implementation, not follows it. Specifically:
1. As the workflow spec is drafted, `WORKFLOW_AUTHORING.md` is drafted alongside it — the doc *is* part of the spec's acceptance criteria
2. As bundled workflows are written (for the ~8 subcommand conversions), each gets agent-targeted comments and is added to `--examples`
3. Before shipping workflow support publicly, run the self-hosting test above against at least two models (Claude, and one smaller/faster model) to confirm the docs generalize

Skipping this section is the single fastest way to ship workflow support that doesn't land. The extensibility story is only real if agents can actually author extensions. The docs are what makes that real.

---

## Should we remove `qdo serve` (the interactive web UI)?

> **[IMPLEMENTED — R.13, 2026-04-17.]** `qdo serve` removed outright (no deprecation step; no users). `tests/test_web.py` deleted. HTML reports (`qdo report table` / `qdo report session`) + the TUI (`qdo explore`) cover the use cases `serve` was straddling.

**Tentative recommendation: yes, deprecate and remove in the next minor release.** Reasoning below; this is a note to revisit before acting.

### Why it made sense originally
`serve` was a reasonable bet when the product's identity was still "three surfaces that share a core: CLI, TUI, web." It gave browser-preferring users a path in and hedged against the TUI being underpowered.

### Why it no longer fits the direction
1. **Agent-first positioning** — Principles 1–11 above are about making querido the best CLI for humans-with-agents. A web UI is an inherently human-only surface; time spent polishing it is time not spent on `next_steps`, sessions, bundles, and workflows
2. **HTML reports supersede the "share with a non-user" use case** (Principle 10). A static self-contained HTML file emailed to a PM is strictly better than "install qdo, run the server, open localhost" — no install, no process, no port, no firewall story, works offline, commits to a repo. `report` wins that job
3. **The TUI covers interactive exploration** (`qdo explore`) for keyboard-driven humans. It's lighter than the web UI, has no dependency on a browser, and composes naturally with the terminal workflow
4. **The strategic section (line 33) already warned against becoming datasette.** Every item under the old "Web UI polish" (CodeMirror editor, WebSockets, saved bookmarks, chart rendering) is a step toward exactly that. Keeping `serve` creates pressure to invest there
5. **Maintenance cost is real and asymmetric** — any new feature that wants to be visible to users has to consider three surfaces instead of two. Sessions/workflows/bundles/reports are complex enough without also threading through a web UI
6. **We have no evidence of meaningful web-UI usage.** Before removing, confirm (e.g., via informal user check-in). Removing something with real users is costlier than carrying it

### What removal looks like
- Deprecate in release N with a stderr notice on `qdo serve` pointing at `qdo report` and `qdo explore`
- Remove in release N+1 (one cycle later)
- Drop the `web` optional extra, the `serve` command, templates under `src/querido/web/`, and related tests
- Keep the Jinja infrastructure (we use it for templates elsewhere and will use it for `qdo report`)
- README updates: remove `serve` from the command list; point at `report` for sharing and `explore` for interactive use

### What could change this recommendation
- If someone shows that a meaningful fraction of users reach for `serve` and wouldn't be served by `report` + `explore`
- If a concrete use case emerges that *requires* a server (live dashboards, team-shared session browser) — though that use case is closer to datasette/superset and probably shouldn't be ours anyway
- If we want `serve` as the substrate for interactive HTML *reports* (linked navigation, live filtering). Probably doesn't justify the surface by itself; static HTML is fine for 90% of report use

### If we keep it
Constrain scope hard: `serve` stays a thin read-only viewer of existing commands' output. No SQL editor, no WebSockets, no bookmarks, no charts beyond what `report` renders statically. Treat it as "HTML reports, but served live from a local process instead of written to disk" — essentially a demo/preview of what `report` produces. This is the only framing under which `serve` survives without pulling us toward datasette.

### Delete this list either way
The earlier "Web UI polish" wishlist (CodeMirror editor, WebSockets, bookmarks, Chart.js) is explicitly off the roadmap regardless of whether `serve` stays. It's the scope-creep gravity well we called out in the strategic section.

## TUI enhancements

- Pivot/group-by mode
- Plot panel
- Multi-table joins
- Column selector: pattern filtering (glob/regex) in addition to checkbox selection
- Column selector: persist default pre-selection per table

## Fuzzy matching improvements

- Use `thefuzz` or edit-distance for higher-quality fuzzy matching in search and column resolution
- Optional dependency to avoid adding weight for basic usage

## Parquet/Arrow metadata

- Read Parquet/Arrow file-level metadata via `pyarrow.parquet.read_schema().metadata`
- Surface in `qdo inspect --verbose` for Parquet files

## Cache improvements

- Background cache refresh
- Incremental sync via `information_schema.tables.last_altered`
- Use DuckDB instead of SQLite for cache to enable analytics on cached metadata

## Data-science primitives

Notes drafted while authoring the bundled `feature-target-exploration` workflow (2026-04-14). The workflow ships today with `# gap:` comments pointing at missing statistical primitives; this section captures the feasibility analysis if we decide to fill those gaps.

**Use case.** A data scientist sits down with a table containing candidate features and a target column they plan to model. Before touching a notebook or a trainer, they want: univariate distributions per feature, outlier counts, feature-feature correlations, feature-target relationship ranking, and group-wise target statistics for categorical features. Today qdo covers univariate (via `profile`/`quality`/`dist`) but nothing downstream.

### Gap primitives

| Primitive | What it does | SQL feasibility | New deps |
|---|---|---|---|
| `qdo outliers -C <col>` | IQR flags per numeric column (Q1, Q3, bounds, flagged-row count) | DuckDB/Snowflake: `PERCENTILE_CONT`. SQLite: unsupported — declare and error clearly. | None |
| `qdo correlate --x A --y B` | Pearson / Spearman correlation between two columns | `CORR()` built-in on DuckDB/Snowflake; Spearman via ranked window. SQLite: manual formula. | None |
| `qdo correlate --matrix --columns A,B,...` | N×N correlation matrix | One SQL scan returns N² pairwise sums; Python assembles the matrix from aggregates (no row materialization). | None (numpy optional for matrix ops) |
| `qdo groupby-stats -g <col> -a <col>` | Per-group count, mean, stddev, percentiles (extends `pivot` to multi-aggregate) | Pure SQL. | None |
| `qdo feature-rank --target T` | Per-feature score vs target, sorted; dispatches by (target_type × feature_type) | Per-group stats in SQL; F-stat / chi² / IV math in Python from O(k) rows. | `querido[stats]` (numpy + scipy) for distribution functions (`scipy.stats.f.sf`, `scipy.stats.chi2.sf`) |
| `qdo info-value -t T --target Y --feature F` | Information Value (IV) and Weight of Evidence (WoE) for a feature against a binary target | SQL (binning + aggregates). | None |
| `qdo cramer-v --columns A,B,...` | Cramér's V matrix over categoricals | Contingency table per pair in SQL; ratio math in Python. | `querido[stats]` (chi² critical values) |

### Feasibility summary

- **Tier 1 (zero-dep, SQL-only):** `correlate` (pairs + matrix), `outliers`, `groupby-stats`, `info-value` for binary-target/categorical-feature case. ~3–4 days. Defensible as "qdo speaks basic statistics against live DBs" without crossing into scipy territory.
- **Tier 2 (`querido[stats]`):** `feature-rank` with full type-aware dispatch, `cramer-v` matrix, ANOVA F-tests, KS tests. ~1–2 weeks. Adds numpy + scipy (~35 MB). Real differentiator — nobody currently owns "feature ranking against a live Snowflake/DuckDB without materializing rows."
- **Tier 3 (`querido[viz]`):** correlation heatmaps, feature-importance bars as inline HTML/PNG. Speculative; qdo is text-first.

### Alignment with qdo's identity

**Fits:** deterministic (no ML-in-the-loop), SQL-first, file-based output, agent-readable. Unique position vs. pandas-profiling / ydata-profiling (those require DataFrames; qdo would operate on warehouse-scale data with only aggregate round-trips).

**Tension:** adds a new persona (data scientist). Partial commitment is worse than no commitment — a DS who uses `feature-rank` will immediately want train/test splits, target encoding preview, and feature engineering, none of which fit qdo's "exploration" frame. If we pursue this, be intentional about where we stop.

**Decision deferred.** The `feature-target-exploration` workflow with `# gap:` comments is the MVP: costs nothing, surfaces demand, gives future contributors a clear spec. Revisit in 2–3 months based on whether anyone reaches for the workflow and hits the gaps.
