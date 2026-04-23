# Changelog

All notable changes to querido (`qdo`) are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic
Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Pre-beta audit, Tier 1** — three bugs a user following the README would hit
  in the first ten minutes:
  - The `--from <session>:<step>` example in `README.md` and
    `docs/cli-reference.md` now records the source step with `-f json`, so
    `--from` has canonical SQL to replay. Previously the second command failed
    with `Session step is not structured`.
  - Missing-extra install hint no longer renders as
    `uv pip install 'querido' or 'querido'`. Rich was eating the
    `[duckdb]` / `[snowflake]` tokens as markup tags;
    `rich.markup.escape` now wraps the displayed cmd / why / hint text.
  - `qdo metadata list` now reports the same composite completeness score as
    `qdo metadata score`. Previously two scoring rubrics disagreed, so
    `metadata suggest --apply` could write real `valid_values` without moving
    the `metadata list` number. Post-`init` now reads 20% (freshness credit);
    post-`suggest --apply` jumps to 50% as applied fields are credited.

## [0.1.0] — 2026-04-22

Initial public release.

qdo is an agent-first data exploration CLI for SQLite, DuckDB, Snowflake, and
Parquet. It turns one-off investigations into reusable team knowledge through a
compounding loop: `discover → understand → capture → answer → hand off`. No
LLMs inside qdo — the agent brings the brain; qdo brings the memory and the
map.

### Added — the compounding loop

- **`qdo context`** — schema, stats, and sample values in one scan, with
  stored metadata auto-merged when present. The anchor command for agent
  workflows.
- **Enriched metadata as plain YAML** — `qdo metadata init/show/list/search/
  edit/refresh/undo/score/suggest`. `suggest --apply` writes deterministic
  inferences (temporal, sparse, valid_values) with provenance tags;
  human-authored fields (`confidence: 1.0`) are never auto-overwritten.
- **`--write-metadata`** on `profile`, `values`, and `quality` — captured
  findings flow back into the next `context` / `quality` run automatically.
- **Knowledge bundles** — `qdo bundle export/import/inspect/diff` produce
  portable, connection-agnostic zip archives of metadata + sessions +
  workflows. Schema-fingerprint checks catch drift on import.
- **Declarative workflows** — YAML workflow spec + runner + lint (`qdo
  workflow run/list/show/lint/spec/from-session`), with bundled worked
  examples under `src/querido/core/workflow/examples/`.
- **Agent output format** — `-f agent` emits TOON for tabular data and YAML
  for nested — 30–70% fewer tokens than JSON for LLM consumption. In-tree
  TOON encoder with vendored spec-conformance fixtures.
- **Structured error envelope** — every CLI failure under `-f json` /
  `-f agent` returns `{error, code, message, hint, try_next}` with stable
  codes agents can gate on.
- **Session recording** — `QDO_SESSION=<name> qdo ...` appends JSONL + stdout
  files to `.qdo/sessions/<name>/`. `qdo session start/list/note/show/replay`
  and `--from <session>:<step>` let agents rebuild and fork investigations.

### Added — exploration primitives

- **`catalog`, `inspect`, `preview`, `profile`, `quality`, `values`, `dist`,
  `freshness`, `joins`, `diff`** — the drill-down trio of scanning commands
  with shared envelope + `next_steps` contract.
- **`query`**, **`export`**, **`pivot`**, **`explain`**, **`assert`** — answer
  questions and verify invariants against SQLite / DuckDB / Snowflake /
  Parquet. Read-only by default; `--allow-write` opt-in for mutating SQL.
- **`sql select/insert/ddl/udf/procedure/task/scratch`** — dialect-aware SQL
  scaffolds with envelope output.
- **`snowflake semantic`** and **`snowflake lineage`** — Cortex Analyst YAML
  generation and `GET_LINEAGE`-based dependency discovery.
- **`report table`** and **`report session`** — single-file shareable HTML
  reports (no JS, no external assets, print-friendly).
- **`qdo explore`** — interactive Textual TUI with selected-column facts
  sidebar, semantic highlighting (PKs, sorted, null-heavy), wide-table triage
  mode, and shared triage story across grid + sidebar + status bar.

### Added — agent integrations

- **Self-hosting eval** (`scripts/eval_skill_files_claude.py`) that runs
  `claude -p` against the SKILL file and grades results across haiku / sonnet
  / opus on 15 tasks. Current baseline: **42/45 (93%)**; three failures are
  `model-mistake`, not `qdo-bug`. Billing guardrails + per-model timeouts
  ship in-repo.
- **`integrations/skills/SKILL.md`** (Claude Code) and
  **`integrations/continue/qdo.md`** (Continue.dev) — ready-made context
  files for coding agents.
- **`WORKFLOW_AUTHORING.md`** and **`WORKFLOW_EXAMPLES.md`** — the docs an
  agent needs to author a valid workflow without repo access.
- **Two built-in tutorials** — `qdo tutorial explore` (15 lessons) and
  `qdo tutorial agent` (13 lessons, metadata + agent workflow).

### Infrastructure

- **Pay for what you use** — SQLite-only install has no optional
  dependencies. DuckDB, Snowflake, and TUI extras are opt-in. All heavy
  imports live inside functions; command startup cost is bounded.
- **Cross-platform CI** — `pytest`, `ruff check`, `ruff format`, and `ty
  check` run green on Ubuntu, macOS, and Windows. Windows `cp1252` stdout is
  reconfigured to UTF-8 at the CLI entrypoint so Rich output pipes safely.
- **Pre-built wheels** via GitHub Releases (`uv tool install querido
  --find-links https://github.com/curtisalexander/querido/releases/expanded_assets/v0.1.0`).

### Polish & audits that shaped v0.1.0

- **Sharpening pass Waves 1–4** (2026-04-18 — 2026-04-20) — cold-start audit,
  docs/code consistency, eval design, first 33/33 baseline.
- **Pre-release polish pass items 0–6** (2026-04-22) — CI unblock, docs
  accuracy audit, sampling-flag harmonization, envelope coverage on `sql` +
  `snowflake`, metadata isolation in eval harness. Ended at 42/45 on 15
  tasks.

[Unreleased]: https://github.com/curtisalexander/querido/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/curtisalexander/querido/releases/tag/v0.1.0
