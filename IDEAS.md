# Ideas

Unimplemented ideas from earlier planning. Not committed to — just possibilities.

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

We already have `qdo tutorial agent` (13 lessons) and `integrations/skills/SKILL.md`. Different purposes:

- **SKILL.md** — reference dropped into the agent's context. Static. Tells the agent *what* commands exist and *when* to use which. This is the right artifact for "teach an agent how to use querido."
- **tutorial agent** — interactive, step-by-step, runs actual commands against a sample DB. Good for humans learning alongside an agent, or for a human verifying the agent understands.

**Gap to consider:** a **playbook doc** (not interactive, not reference) — "How to answer common questions with querido." E.g., *"How do I check if table X is fresh?"*, *"How do I find the join key between two tables?"*, *"How do I validate a migration didn't change row counts?"* Each entry is a named recipe with the exact command sequence. This is different from SKILL.md's command listing and would be genuinely useful for agents. Could live at `integrations/playbooks/agent-recipes.md`.

**Recommendation:** don't duplicate the skill file. Add a recipes doc instead. Low-cost, high-value.

---

## High-value quick wins (implementable now)

Ordered by (value / effort):

1. **`-f agent` output format** — TOON or compact TSV+YAML hybrid. Biggest differentiation for agent use. ~2–3 days.
2. **`qdo search "<intent>"`** — BM25-style ranking over our 27 commands' docstrings. No external dependency (simple scoring in Python). Helps discovery. ~half day.
3. **SQL history log** — append `~/.qdo/history.jsonl` for every `query`/`assert`/`pivot`. ~2 hours.
4. **Audit log flag** — `QDO_AUDIT_LOG=path.jsonl` captures every command invocation. ~2 hours.
5. **Agent recipes doc** — 10–15 named playbooks. ~half day.
6. **`qdo catalog functions`** — list DuckDB/Snowflake SQL functions so agents know what's available. ~half day.

Items 1–4 could be a single 1-week push that meaningfully sharpens the agent story before qsv's MCP work becomes the default answer.

---

## qdo freshness — row freshness / staleness

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

## Web UI polish

- SQL workspace tab with CodeMirror editor
- WebSocket for live query execution progress
- Multiple connection switching (dropdown in nav)
- Saved pivot queries / bookmarks
- Chart rendering for distributions (e.g., Chart.js or Observable Plot)

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
