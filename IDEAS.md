# Ideas and decisions

This is the index for **uncommitted** candidates and decisions worth preserving.
It is not a roadmap. Work becomes committed only when it moves to
[PLAN.md](./PLAN.md), ideally after dogfood supplies a concrete problem.

Detailed research and superseded lists are preserved in the
[archived ideas notebook](./docs/archive/IDEAS-2026-07-13.md). Focused research
notes remain under [`docs/research/`](./docs/research/).

## Filter before promoting anything

1. Does it tighten the discover → understand → capture → answer → hand-off
   loop?
2. Is there evidence from use, rather than competitive anxiety or novelty?
3. Can non-users avoid its install and runtime cost?
4. Does it keep files as primitives and LLM calls outside qdo?
5. Can it extend the existing CLI instead of creating a parallel surface?

The full product boundary is in
[DIFFERENTIATION.md](./DIFFERENTIATION.md#filter-for-future-changes).

## Rejected or removed

Do not re-propose these without new evidence that invalidates the decision.

- **In-product natural-language-to-SQL or other LLM calls.** The agent is the
  brain; qdo is deterministic memory and tooling.
- **Hosted service or plugin marketplace.** Metadata, sessions, reports,
  bundles, and workflows remain portable files.
- **Broad Rust rewrite.** Database engines own the hot path; a second language
  would add contributor cost without solving a measured bottleneck.
- **Top-level workflow aliases.** `qdo workflow run <name>` is the only workflow
  invocation pattern.
- **Turning primitive commands into workflows.** Fused scans and validated
  command contracts remain Python primitives; workflows orchestrate them.
- **`qdo search` for command discovery.** Root help and agent instructions cover
  the need without another command surface.
- **`-f agent` / TOON serialization.** It was built, unpromoted, unmeasured in
  real use, and removed. JSON remains the agent contract.
- **A full terminal SQL IDE or web viewer.** `explore` is a supplement, not the
  product center.

## Candidates awaiting dogfood

These are questions, not promises, and are intentionally unranked.

### Strengthen the compounding loop

- **Change over time:** snapshots and `diff --since` for “what changed since I
  last looked?”
- **Branch from recorded SQL:** explicit, deterministic filters or projections
  over a structured session query without turning sessions into a notebook DAG.
- **Read existing semantic context:** selectively ingest dbt manifests or
  foreign-key metadata when present instead of inventing a semantic-authoring
  system.
- **Metadata search:** consider embeddings only if lexical search fails on real
  corpora.

### Reduce real execution cost

- **Snowflake `RESULT_SCAN` reuse** for related session steps.
- **Stratified sampling** if simple samples prove misleading.
- **Profile-cache reuse** if repeated scans show up in dogfood traces.
- **DuckDB `SUMMARIZE` delegation** only after profiling proves it materially
  improves the current path.

### Reach clients without a shell

- **Thin MCP adapter:** a small curated set of tools that invokes the CLI and
  returns its envelope verbatim. Build only if users need Claude Desktop,
  Cursor, or another client without shell access. The dated design draft is
  [research, not a committed 0.3.0 plan](./docs/research/mcp-wrapper-design.md).

### Broaden file convenience carefully

- CSV/JSON/NDJSON direct connections through the optional DuckDB backend.
- Parquet glob and URL pass-through where DuckDB already supplies the behavior.
- A DataFrame hand-off only after users repeatedly export and immediately load
  results; keep it behind an optional extra.

### Agent ergonomics

- A behavior profile that composes existing JSON output, quiet progress, and
  token-conscious defaults—only if agent traces show repeated flag/setup cost.
- A smaller installed skill for constrained context windows, generated from the
  same normative source rather than maintained as another fork.
- Named investigation recipes inside the skill when agents need sequencing
  examples more than command reference.

### Data-science primitives

Workflow examples intentionally expose gaps such as outlier detection,
correlation matrices, target-aware feature ranking, and grouped multi-aggregate
statistics. Add a primitive only when it is deterministic, useful outside one
workflow, and better delegated to qdo than expressed as SQL. Until then, `# gap`
comments in examples are honest documentation, not an implementation queue.

## How to use this file

- A **bug** goes straight to a fix or issue.
- Repeated **friction** can be promoted to PLAN with the observed workflow and
  a smallest useful outcome.
- A new **desire** starts here with the evidence that prompted it.
- Detailed investigation belongs in a dated research note, linked from the
  candidate—not inline as another multi-page mini-plan.
