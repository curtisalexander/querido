# Changelog

All notable changes to querido (`qdo`) are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic
Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-07-06

First PyPI release. Install with `uv tool install querido` or `pip install
querido` — the package is `querido`, the command is `qdo`.

### Added

- **Auto-capture** — `context --write-metadata`, a capture hint at the end of
  `context` / `quality` rich output when derived fields aren't stored yet, and
  opt-in `QDO_AUTO_CAPTURE=1` to auto-persist from `context` / `profile` /
  `values` / `quality`.
- **On-disk contract versioning** — metadata YAML documents now carry a
  `schema_version`, the metadata cache stores its schema version in SQLite's
  `user_version` (mismatches rebuild the cache), and `bundle import` refuses
  bundles with a newer `format_version` instead of silently misreading them.
- **PyPI publishing** — the release workflow publishes to PyPI via trusted
  publishing (OIDC) after the build + wheel smoke test.
- Release-readiness review document (`RELEASE_READINESS_REVIEW.md`) capturing
  the beta blockers (since resolved), verification evidence, and clean-room
  install checklist.

### Changed

- CI now tests Python 3.12, 3.13, and 3.14 across all three OSes (previously
  3.13 only).
- Install docs across README, CLI reference, and SKILL files point at PyPI
  instead of GitHub Release wheel URLs (wheels are still attached to releases).
- `qdo overview` output is byte-identical to `docs/cli-reference.md` (no
  extra trailing newline).
- Internal layering: the `-f/--format` argv hoist moved to `querido._argv`
  and the root-context format lookup to `querido._runtime`, so `core/` and
  `output/` no longer import from `cli/`.
- The sdist no longer ships internal process docs (PLAN, IDEAS,
  REVIEW_FINDINGS, RELEASE_READINESS_REVIEW).

### Fixed

The 2026-06-10 multi-agent review pass (7 high / 19 medium / 35 low findings,
tracked in `REVIEW_FINDINGS.md`) landed in full. Highlights:

- DuckDB mixed-case table names resolve correctly across all catalog lookups.
- The `--allow-write` guard can no longer be bypassed with CTE-prefixed writes
  (`with x as (...) delete ...`), and now also classifies `copy` / `export` /
  `attach` / `detach` / `install` / `load` / `call` / `vacuum` as destructive —
  `copy ... to` writes files even on a read-only DuckDB handle.
- SQLite databases open read-only by default (`mode=ro`) — no more silent WAL
  journal-mode mutation; DuckDB no longer creates an empty database file at a
  mistyped path.
- `qdo assert` honors its documented exit-code contract (0 pass / 1 fail /
  2 SQL error); `pivot` no longer rewrites `count(*)` to `count(<col>)`;
  `values` reports correct `total_rows` for columns with NULLs.
- Workflow docs and runner agree: step `id` binding, `qdo_min_version`
  enforcement, `-f` propagation, recursion depth guard, and quoted-`${ref}`
  lint warnings.
- Hallucinated `-f jsonl` examples removed from shipped agent docs.
- `~` expands in sqlite/duckdb/parquet connection paths; connection config
  errors return `CONNECTION_NOT_FOUND` with a correct hint.
- Identifier quoting hardened for schema-qualified and quoted names;
  Snowflake concurrent-query cancellation covers all active cursors.
- Migrated to typer 0.26+ (`typer>=0.26`), which vendors its own click fork
  and drops the standalone `click` dependency. qdo previously imported click
  directly and relied on typer providing it transitively, so a fresh install
  resolving typer 0.26 crashed with `ModuleNotFoundError: No module named
  'click'` — and with click installed manually, typer 0.26's *separate*
  context stack made `-f json` / `--show-sql` / session recording silently
  degrade to defaults. All click-shaped imports now route through
  `querido._click`, a single shim over typer's vendored click, and the
  standalone `click` package is no longer a dependency. Caught by the
  clean-room install check.

## [0.1.0] — 2026-04-22

Initial public beta release.

qdo is an agent-first data exploration CLI for SQLite, DuckDB, Snowflake, and
Parquet. It turns one-off investigations into reusable team knowledge through a
compounding loop: `discover → understand → capture → answer → hand off`. No
LLMs inside qdo — the agent brings the brain; qdo brings the memory and the map.

### Added — the compounding loop

- **`qdo context`** — schema, stats, and sample values in one scan, with stored
  metadata auto-merged when present. The anchor command for agent workflows.
- **Enriched metadata as plain YAML** — `qdo metadata init/show/list/search/edit/
  refresh/undo/score/suggest`. `suggest --apply` writes deterministic inferences
  (temporal, sparse, valid_values) with provenance tags; human-authored fields
  (`confidence: 1.0`) are never auto-overwritten.
- **`--write-metadata` on `profile`, `values`, and `quality`** — captured
  findings flow back into the next `context` / `quality` run automatically.
- **Knowledge bundles** — `qdo bundle export/import/inspect/diff` produce
  portable, connection-agnostic zip archives of metadata + sessions + workflows.
  Schema-fingerprint checks catch drift on import.
- **Declarative workflows** — YAML workflow spec + runner + lint (`qdo workflow
  run/list/show/lint/spec/from-session`), with bundled worked examples.
- **Agent output format** — `-f agent` emits TOON for tabular data and YAML for
  nested data. In-tree TOON encoder ships with vendored spec-conformance
  fixtures.
- **Structured error envelope** — CLI failures under `-f json` / `-f agent`
  return `{error, code, message, hint, try_next}` with stable codes agents can
  gate on.
- **Session recording** — `QDO_SESSION=<name> qdo ...` appends JSONL + stdout
  files to `.qdo/sessions/<name>/`. `qdo session start/list/note/show/replay`
  and `--from <session>:<step>` let agents rebuild and fork investigations.

### Added — exploration primitives

- **`catalog`, `inspect`, `preview`, `profile`, `quality`, `values`, `dist`,
  `freshness`, `joins`, `diff`** — scanning commands with shared envelope +
  `next_steps` contract.
- **`query`, `export`, `pivot`, `explain`, `assert`** — answer questions and
  verify invariants against SQLite / DuckDB / Snowflake / Parquet. Read-only by
  default; `--allow-write` opts into mutating SQL.
- **`sql select/insert/ddl/udf/procedure/task/scratch`** — dialect-aware SQL
  scaffolds with envelope output.
- **`snowflake semantic` and `snowflake lineage`** — Cortex Analyst YAML
  generation and `GET_LINEAGE`-based dependency discovery.
- **`report table` and `report session`** — single-file shareable HTML reports
  (no JS, no external assets, print-friendly).
- **`qdo explore`** — interactive Textual TUI with selected-column facts sidebar,
  semantic highlighting, wide-table triage mode, and shared triage story across
  grid + sidebar + status bar.

### Added — agent integrations

- **`qdo agent list/show/install`** — packaged coding-agent integration docs are
  available from the installed wheel. `qdo agent install skill` writes
  `skills/querido/SKILL.md` plus workflow references; `qdo agent install
  continue` writes `.continue/rules/qdo.md`.
- **Self-hosting eval** (`scripts/eval_skill_files_claude.py`) runs `claude -p`
  against the SKILL file and grades results across haiku / sonnet / opus on 15
  tasks. Current baseline: **45/45 (100%)** with zero `qdo-bug` failures.
- **Eval-harness runtime safeguards** — wall-clock cap, per-task and qdo command
  timeouts, per-task progress headers, and line-buffered stdout for long runs.
- **`integrations/skills/SKILL.md`** (Claude Code),
  **`integrations/continue/qdo.md`** (Continue.dev),
  **`WORKFLOW_AUTHORING.md`**, and **`WORKFLOW_EXAMPLES.md`** — ready-made agent
  context files.
- **GitHub Pages agent integration pages** generated from the canonical
  `integrations/` files.
- **Two built-in tutorials** — `qdo tutorial explore` (10-lesson compounding-loop
  walkthrough) and `qdo tutorial agent` (13 lessons, metadata + agent workflow).

### Added — packaging and project hygiene

- **`qdo config remove --name <n>`** — removes a named connection with a
  confirmation prompt by default and a `-y` / `--yes` bypass for scripts.
- **Backend-install warnings** for `qdo config add` / `qdo config clone` when a
  DuckDB or Snowflake connection is configured without the corresponding extra.
- **`--column` alias** on `values` / `dist` / `profile` for the singular form of
  `--columns` / `-C`.
- **Project metadata** in `pyproject.toml`: authors, URLs, keywords, classifiers,
  and typed-package marker.
- **GitHub issue and PR templates** aligned with qdo's release gates.

### Changed

- **`qdo tutorial explore`** now teaches the compounding loop directly:
  `catalog → context → values → metadata capture → quality → dist → query +
  pivot → report + agent pointer`. Metadata writes and generated reports go to a
  scratch temp dir so re-runs do not pollute the user's cwd.
- **`qdo metadata list` completeness now matches `qdo metadata score`** by using
  the same scoring rubric.
- **`qdo --help` tagline** now leads with the differentiator: accumulating
  understanding so subsequent investigations get sharper.
- **SKILL.md and Continue.dev docs** now promote the canonical `qdo -f json
  <cmd>` style, document `qdo metadata search`, include a dedicated `quality`
  section, and state that `bundle export` is never the last hand-off step.
- **`AGENTS.md`** was trimmed to contributor workflow, critical invariants, test
  philosophy, evals, release process, and style.
- **Help text polish** across write flags, sampling flags, `--from`, and
  connection options now spells out side effects and recovery paths.

### Fixed

- DuckDB nullable metadata now handles boolean `duckdb_columns().is_nullable`
  correctly.
- `uv run ty check` is green with the eval-harness stdout line-buffering code.
- README and CLI-reference session-replay examples record source steps with
  `-f json`, which `--from <session>:<step>` requires.
- Missing-extra install hints preserve bracketed extras (`querido[duckdb]`,
  `querido[snowflake]`) in Rich output.
- Session-step `--from` errors now explain how to re-record with `-f json` and
  include a targeted `try_next` suggestion.
- Removed a hallucinated `values --counts` reference from SKILL.md.
- `qdo report table` / `report session` without `-o` now call out that the
  opened file is temporary.
- Documentation snapshots were refreshed for the 45/45 eval, tutorial lesson
  count, and final pre-beta audit state.

### Polish & audits that shaped v0.1.0

- **Sharpening pass Waves 1–4** (2026-04-18 — 2026-04-20) — cold-start audit,
  docs/code consistency, eval design, first 33/33 baseline.
- **Pre-release polish pass items 0–6** (2026-04-22) — CI unblock, docs accuracy
  audit, sampling-flag harmonization, envelope coverage on `sql` + `snowflake`,
  metadata isolation in eval harness.
- **Pre-beta audit pass** (2026-04-23) — 26-item first-contact audit across quick
  start, docs consistency, CLI help + errors, tutorials + SKILL files, and
  release artifacts. All 26 items shipped; 2 deferred by design. Eval recovered
  from 42/45 to **45/45 (100%)**.

[Unreleased]: https://github.com/curtisalexander/querido/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/curtisalexander/querido/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/curtisalexander/querido/releases/tag/v0.1.0
