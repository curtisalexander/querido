# Changelog

All notable changes to querido (`qdo`) are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic
Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Pre-beta audit pass — a proxy-dogfood that simulated first-contact with the
project across five angles (quick-start walkthrough, docs consistency, CLI
help + errors, tutorials + SKILL files, release artifacts) and produced a 26-item
tiered punch list. All 26 items shipped, 2 deferred by design. Self-hosting
eval went from 42/45 → 44/45 (97.8%) across haiku / sonnet / opus.

### Added

- **`qdo config remove --name <n>`** — removes a named connection with a
  confirmation prompt by default and a `-y` / `--yes` bypass for scripts.
  `CONNECTION_NOT_FOUND` structured error under `-f json` when the name is
  unknown. Saved column sets referencing the connection are intentionally left
  in place (delete them separately with `qdo config column-set delete` if no
  longer needed).
- **`qdo config add` / `qdo config clone` backend-install warning** — when
  the user adds a connection whose backend extra isn't installed (DuckDB,
  Snowflake), the command succeeds and prints a yellow warning pointing at
  the exact `uv pip install 'querido[<extra>]'` command. Previously this
  silently succeeded, then every subsequent use of the connection would fail.
- **`--column` alias on `values` / `dist` / `profile`** — a Click alias for
  `--columns` / `-C`, so a singular-form typo no longer burns an eval retry
  or a real user's first attempt.
- **`.github/ISSUE_TEMPLATE/` + `PULL_REQUEST_TEMPLATE.md`** — structured
  bug / feature templates and a PR checklist aligned with the CI gate.
- **`CHANGELOG.md`** — this file. Curated v0.1.0 entry + ongoing
  `[Unreleased]` section.
- **`pyproject.toml` project metadata** — `authors`, `[project.urls]`,
  `keywords`, 15 classifiers (Beta, Python 3.12 / 3.13, MIT, Typed, …). A
  `uv tool info` or later PyPI page no longer looks unfinished.

### Changed

- **`qdo tutorial explore` re-sequenced** from a 15-lesson command-by-command
  tour to a 10-lesson walk through the compounding loop:
  `catalog → context → values → metadata capture → quality → dist → query +
  pivot → report + agent pointer`. `context` appears early and explicitly
  replaces separate inspect/preview/profile calls. A new "capture" lesson
  runs `metadata init` + `suggest --apply` so the user sees the YAML write
  happen; the next `quality` lesson then demonstrates stored `valid_values`
  driving `invalid_count`. Final lesson points at `qdo tutorial agent`.
  Tutorial's metadata writes + generated report now go to a scratch temp
  dir via `QDO_METADATA_DIR`, so re-runs leave no artifacts in the user's cwd.
- **`qdo metadata list` completeness now matches `qdo metadata score`.**
  The two commands used to compute different numbers for the same question.
  Converged on the `score_table` rubric (column descriptions + valid_values
  + freshness) so `suggest --apply` visibly moves the `list` number too.
- **`qdo --help` tagline** — "Agent-first data exploration CLI — accumulate
  understanding of your data so every subsequent investigation is sharper
  than the last." Leads with the compounding-loop differentiator.
- **SKILL.md restructured** — added a dedicated `## quality — detect data
  issues` section with JSON shape + decision rubric, split the Gotchas
  section into agent-facing vs operator-facing, documented `qdo metadata
  search` (lexical BM25 over stored metadata), and updated examples to use
  the canonical `qdo -f json <cmd>` placement. Landed a `bundle inspect`
  invariant: `bundle export` is never the last step of a hand-off.
- **`integrations/continue/qdo.md` aligned** with SKILL.md's canonical
  `qdo -f json <cmd>` pattern so a Continue.dev user sees the same primary
  invocation style as a Claude Code user.
- **`AGENTS.md` trimmed** from ~508 lines to ~156 — focused on contributor
  workflow + 8 critical invariants + the 7-rule test philosophy.
  Command-surface enumeration and agent-workflow walkthroughs now live
  in README / SKILL / ARCHITECTURE with explicit pointers.
- **Help-text polish across the scanning trio** — `--write-metadata`,
  `--quick`, `--apply`, `--sample-values`, and `--from` now each surface
  side effects and preservation rules in one sentence, not just a label.
  `--connection` text standardized to "Named connection or file path." on
  every command that accepts both.

### Fixed

- **README Quick Start session-replay example** (`--from scratch:1`) failed
  because `--from` needs the source step recorded as `-f json`. Added
  `-f json` to the recording step plus a one-line lead-in. Verified
  end-to-end. Same fix applied to the mirrored example in
  `docs/cli-reference.md`.
- **Missing-extra install hint** rendered as `uv pip install 'querido' or
  'querido'`. Rich was eating `[duckdb]` / `[snowflake]` as markup tags.
  `rich.markup.escape` now wraps the try_next `cmd` / `why` / hint text.
  Regression test in `tests/test_errors.py`.
- **"Session step is not structured" error** was jargon with no `try_next`
  hint. Rewrote all four session-step `--from` errors to tell users what
  to do (re-record with `-f json`) while preserving structured error codes.
  `SESSION_STEP_UNSTRUCTURED` now gets a dedicated `try_next` branch that
  proposes the exact re-record command instead of the generic
  "show the session" fallback.
- **Hallucinated `values --counts` flag** surfaced by the eval — removed
  from SKILL.md and replaced with accurate `qdo values -c <conn> -t <table>
  -C <col>` wording plus an explicit "There is no `--counts` flag." note.
- **`qdo report table` / `report session`** without `-o` now print a
  "Tempfile — pass `-o <name>.html` to keep a permanent copy." note so
  first-time users aren't surprised when the file vanishes.
- **DIFFERENTIATION.md / SKILL.md eval-stat drift** — refreshed from stale
  "33/33 perfect / 1174 tests" to the current numbers. Snapshot date,
  command-count, and envelope-coverage statements in DIFFERENTIATION.md
  also refreshed.
- **`ARCHITECTURE.md` tutorial description** updated to reflect the 10-lesson
  re-sequence.

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
