# Plan

Committed todo list for making querido the agent-first data exploration CLI. Items here are scoped, sequenced, and ready to work on.

> **PLAN.md vs IDEAS.md.** This file is the commitment record — current status, what shipped, and what's actionable next. [IDEAS.md](IDEAS.md) is the speculative archive (competitive analysis, format research, architecture notes, unpromoted features). Ideas promote from IDEAS.md into PLAN.md when we commit to building them; after they ship, the detail in PLAN.md collapses to a summary while the code becomes the authoritative record.

---

## Status (as of 2026-04-21)

**Tests:** 1085 passing, 25 skipped. `ruff check` and `ty check` are green. Zero `TODO` / `FIXME` tags.

**Every planned phase is shipped.** Phases 1–4 + 6; Phase 5 dropped by design. R-series (R.1–R.26) all done or intentionally dropped. Sharpening pass (Waves 1–4) done — the first live self-hosting eval baseline is **33/33 perfect** across haiku / sonnet / opus.

Remaining work is the open-ended backlog in [Deferred / future phases](#deferred--future-phases).

**Pick up next session with one of these:**

1. **Start Phase 7.** Human-facing output / TUI polish now has an explicit plan below. Natural first slice: richer `explore` sidebar + status bar, then semantic highlighting in the main table.
2. **Re-run the eval** after any SKILL.md or command-surface change: `unset ANTHROPIC_API_KEY; uv run python scripts/eval_skill_files_claude.py --models all --budget 5 --confirm-spend`. Expect 33/33; regressions are signal.
3. **Treat structured errors as maintenance, not a phase.** The high-value validation paths are now on stable codes under `-f json` / `-f agent`; only promote additional cases opportunistically when the failure shape is durable and agent-actionable.

---

## Phases shipped

Each phase is now documented by the code itself. These summaries exist for cold-start context; follow the file pointers for specifics.

### Phase 1 — Agent-first foundations (done)

The four pieces that create the "tool gets better the more it's used" compounding loop:

- `next_steps` on every scanning command + `try_next` on structured errors (`src/querido/core/next_steps.py`, exercised by `_ENVELOPE_CASES` in `tests/test_next_steps.py`).
- Session MVP — `QDO_SESSION=<name>` appends JSONL to `.qdo/sessions/<name>/steps.jsonl` plus per-step stdout files (`src/querido/core/session.py`, `src/querido/cli/session.py`).
- `--write-metadata` on `profile` / `values` / `quality` with provenance (`src/querido/core/metadata_write.py`). Deterministic auto-fill rules; never overwrites `confidence: 1.0` without `--force`.
- `qdo metadata score` + `qdo metadata suggest --apply` — measurable target + non-preachy nudge (`src/querido/core/metadata_score.py`).

### Phase 2 — Agent output + first shareable artifact (done)

- `-f agent` output format — TOON for tabular, YAML for nested, via shared `emit_envelope` dispatch. In-tree TOON encoder with vendored conformance fixtures (`src/querido/output/toon.py`, `tests/test_toon.py` — 118 parametrized cases). `QDO_FORMAT=agent` sets the default.
- `qdo report table` single-file HTML with schema + metadata + quality + joins (`src/querido/core/report.py::build_table_report`, `src/querido/output/report_html.py::render_table_report`, `src/querido/cli/report.py::report_table`). No JS, inline SVG, print-friendly CSS.

### Phase 3 — Team sharing via knowledge bundles (done)

`qdo bundle export` / `import` / `inspect` / `diff` — portable, connection-agnostic archives of metadata + optional sessions + workflows. Schema-fingerprint checks catch drift on import. Merge strategies preserve provenance: auto-fills break ties by confidence + recency; human-authored fields (`confidence: 1.0`) are never auto-overwritten. See `src/querido/core/bundle.py`, `src/querido/cli/bundle.py`.

### Phase 4 — Workflows as extensibility (done)

- Workflow spec (JSON Schema), runner, lint, list, `show`, `spec --examples`, `from-session` — `src/querido/core/workflow/`, `src/querido/cli/workflow.py`.
- `WORKFLOW_AUTHORING.md` + `SKILL.md` + `AGENTS.md` — the docs an agent loads to author a workflow without repo access.
- Bundled workflows under `src/querido/core/workflow/examples/` serve as the worked-example corpus.
- Self-hosting eval (`scripts/eval_workflow_authoring.py`, plus the broader `scripts/eval_skill_files_claude.py` added in Wave 3) — refuses to run with `ANTHROPIC_API_KEY` set; per-model timeouts; budget guardrails.

**Canonical invocation is `qdo workflow run <name>`.** The "CLI sugar shim" idea (Phase 4.4; `qdo <workflow-name>` as a top-level alias) was dropped — one invocation pattern is better than two parallel paths. See [IDEAS.md](IDEAS.md) "subcommand-to-workflow sugar" for the rejected analysis.

### Phase 5 — Subcommand → workflow conversions (dropped by design)

IDEAS.md proposed converting 8–10 subcommands (`template`, `sql scratch`, `pivot`, `joins`, etc.) to bundled workflows behind a sugar shim. Rejected: the "no workflow shim" principle prevails — agents and humans learn one invocation pattern (`qdo workflow run <name>`), and fused-scan primitives that own a perf optimization (`context`, `quality`) shouldn't be workflow-ified. Subcommands stay primitives; workflows stay workflows.

### Phase 6 — Session reports and cleanup (done)

- **6.1** — `qdo report session <name>` renders a session as single-file HTML. One card per step with status pills, alternating theme color, collapsed `<details>` for the full invocation, rendered stdout (JSON pretty-printed). Per-step commentary via `qdo session note <text>`, which rewrites the last record in `steps.jsonl`. Offline-readable invariants encoded as tests (no `<script>`, no `<iframe>`, no external stylesheet, no `<img src="http…">`). See `src/querido/core/report.py::build_session_report`, `src/querido/output/report_html.py::render_session_report`, `tests/test_report_session.py`.
- **6.2 + 6.3** — `qdo serve` removed (landed via R.13; deprecation step skipped since there were no users). `tests/test_web.py` deleted with it.

### Phase 7 — Human-facing output polish (planned)

The agent-first core is in good shape. The next committed track is making the human experience feel intentional and high-signal too, especially in `qdo explore` and Rich terminal output.

**7.1 — TUI foundation / information hierarchy**

- Upgrade the `explore` sidebar from a text dump into a compact facts panel: type, null rate, distinct count, min/max, sample values, metadata description, and quality flags for the selected column.
- Make the status bar carry more real context: connection, table, displayed/total rows, filtered state, sampled/exact state, sort state, metadata presence.
- Add semantic highlighting in the main `DataTable` so PKs, sorted columns, null-heavy columns, and warning states are visually obvious.

**7.2 — Human-readable scan output**

- Improve Rich output for `context`, `quality`, `profile`, and `catalog` so important signals are easier to scan: clearer section hierarchy, badges, callouts, small inline bars / sparklines where appropriate.
- Keep the JSON / agent shapes unchanged; this phase is about human presentation, not output-contract churn.

**7.3 — Wide-table and triage UX**

- Surface the existing tiered profiling story visually: category chips, recommended-first columns, clearer quick-mode vs full-mode transitions.
- Make `explore` feel useful on wide tables without dumping a wall of equal-weight columns.

**7.4 — Visual coherence**

- Align the TUI, Rich terminal output, and HTML reports so they feel like the same product: shared palette, badges, density choices, and emphasis rules.
- Preserve the existing CLI / workflow surface; this is a presentation pass, not a redesign of command semantics.

---

## Sharpening pass (Waves 1–4) — done

Four waves of audit + sharpening, shipped 2026-04-18 through 2026-04-20.

- **Wave 1** — cold-start + command-surface audit (CS.x + CA.x findings). Established the eval idea.
- **Wave 2** — docs + code consistency (DC.x + CC.x findings). Landed CC.6 and CC.10; scheduled CC.5 (TypedDicts).
- **Wave 3** — eval design + build. Shipped `scripts/eval_skill_files_claude.py` (EV.Build) — 11 tasks × 3 models, 39 harness unit tests, billing guardrails.
- **Wave 4** — first live baseline + scaffolding sharpening. Got to **33/33 perfect**. The tightenings:
  - `src/querido/cli/argv_hoist.py` + `cli/main.py::run` entrypoint — `-f/--format` now works anywhere in argv; workflow runner shares `split_format_flag`.
  - SKILL.md: six broken `-f json` examples corrected, flag-placement rule documented, `qdo export --format csv` → `-e csv`, `qdo diff` promoted into the Quick Exploration Workflow.
  - Eval harness: dropped `--bare` (was suppressing OAuth token → false auth-error); classifier splits click usage errors from real crashes; parser normalizes `cd X && qdo`, `export X=Y && qdo`, `-f json` mid-argv; pre-task runs with `cwd=scratch`.
  - Scan-result TypedDicts (CC.5): `ProfileResult` / `QualityResult` / `ContextResult` / `ValuesResult` landed; downstream `for_*` / `derive_from_*` / `write_from_*` signatures narrowed accordingly.

Commits from this pass: `2722748` (Wave 4 fixes), `c5ffb3c` (TypedDicts), `079128d` (Phase 6.1).

---

## Durable references

Content that outlasts any given phase and should stay findable.

### Where the test rubric lives

**`AGENTS.md` → "Writing tests"** — seven rules: name the failure mode, test behavior not framework, exit code is not an assertion, parametrize over copy-paste, scenario coverage ≠ redundancy, integration for invariants / unit for pure logic, don't string-match error prose. Enforce on every new test.

### Extensible contract tests to build on

Each is a parametrized case list; extending is a one-line addition:

- **`_ENVELOPE_CASES`** in `tests/test_next_steps.py` — asserts every scanning command emits the uniform `{command, data, next_steps, meta}` envelope. Add a new scanning command → wire through `emit_envelope()`, append a row, done.
- **`_READBACK_CASES`** in `tests/test_readback_loop.py` — asserts every `--connection`-accepting scan surfaces stored metadata on the next call. Template for future metadata-driven invariants.
- **`tests/test_errors.py` validation contract cases** — central place to extend structured error assertions as more commands gain stable codes. Prefer asserting on `code` / `try_next`, not human-readable prose.

### Don't touch — already good

Files to resist future pressure to shrink:

- **`tests/test_toon.py`** (118 tests) — one `@pytest.mark.parametrize` over vendored TOON spec-conformance fixtures. Model for spec-implementation suites.
- **Per-rule scenario tests in `tests/test_next_steps.py`** — three `for_inspect_*` tests each exercise a distinct branch (populated / empty / no-comment); not redundant.
- **Dialect-specific `sql` tests where outputs diverge** — DDL types (TEXT vs VARCHAR), UDF syntax (Python `create_function` vs SQL `CREATE FUNCTION`). Keep both dialects.
- **`tests/test_readback_loop.py`** — 7 tests on the R.1 compounding-loop invariant.

### Audit lessons worth keeping

1. **Scenario coverage ≠ redundancy.** The 2026-04-17 cleanup pitched ~145 deletions and delivered ~40. Three tests per lint rule / classifier branch / error path are each doing real work. Parametrize only when assertions are genuinely symmetric.
2. **Spec-conformance suites are honest.** A file with 118 tests may be one parametrize over 118 fixture entries — appropriate for the shape.
3. **The real wins weren't deletions.** Shared fixtures (T.1, −7s wall time), envelope contract (3→11 commands), readback contract (extensible) moved the needle more than any individual trim.
4. **Brittle-prose tests often reflect product gaps.** The right fix was routing common validation failures through the structured envelope for `-f json` / `-f agent`, then rewriting tests around stable codes instead of prose.

### Open items the test cleanup deferred

- Keep rewriting lingering prose-oriented validation tests against structured payloads whenever a command now emits a stable code under `-f json` / `-f agent`.
- Only promote additional validation failures from generic `VALIDATION_ERROR` into named codes when the failure shape is durable, actionable, and likely to matter to agents.

---

## Deferred / future phases

Capture but don't start. Each is standalone and non-blocking.

- `qdo investigate <table>` and friends — ship as bundled workflows on top of existing primitives.
- `qdo diff --since <session>` — change detection for returning agents (pairs well with Phase 6.1 session reports).
- `qdo freshness` — row freshness / staleness with auto timestamp-column detection.
- Cost / time `--estimate` flag on `query` / `export`.
- Read-only-by-default guardrail on `query` (`--allow-write` required).
- `--plan` dry-run flag on `export`, `query`, `metadata write`.
- `qdo search "<intent>"` — BM25 over command docstrings.
- `qdo catalog functions` — list DuckDB / Snowflake SQL functions.
- Embedding-based semantic search across metadata.
- `--from` flag to reference prior session step outputs (e.g., `qdo query --sql-from session1.step3`).
- Session replay (`qdo session replay <name>`).
- Metadata undo.
- Progressive disclosure `--level 1..3` on expensive commands.
- Snowflake `RESULT_SCAN` reuse for chained queries.
- Pyodide `querido-lite` browser demo (only if concrete adoption pulls for it).
- MCP thin wrapper (defer; keep CLI surface MCP-ready — stable flags, structured errors, no TTY-required behaviors).

---

## Principles that govern all work above

1. **Agent-first.** Every feature is evaluated on "does this make a coding agent's loop tighter, cheaper, or more correct?" If not, defer.
2. **Deterministic tools, not LLM-in-the-loop suggestions.** Agents bring the brain; querido brings the memory and the map.
3. **Files, not servers.** Sessions, metadata, bundles, workflows, reports — all plain files. No daemon, no platform.
4. **Declarative extensibility, not plugins.** Workflows are YAML, not Python. No sandbox, no ABI.
5. **Compose with the ecosystem.** DuckDB / Snowflake own execution. qsv owns row-oriented CSV wrangling. datasette owns hosted publishing. We own the agent-readable exploration + metadata + workflow loop.
6. **Don't break existing CLI surface.** Conversions and removals preserve invocation names; deprecation always precedes removal.

## Sequencing invariants

- Phase 1 before 2 / 3 / 4 — sessions + `next_steps` + metadata enable everything downstream.
- Phase 4.5 (agent-authoring docs) runs in parallel with 4.1–4.3, not after.
- Phase 5 skipped (see header).
- Phase 6.1 depends on 4.2 (sessions must exist); 6.2–6.3 independent.
