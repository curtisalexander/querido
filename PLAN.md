# Plan

Committed todo list for making querido the agent-first data exploration CLI. Items here are scoped, sequenced, and ready to work on.

> **PLAN.md vs IDEAS.md.** This file is the commitment record — current status, what shipped, and what's actionable next. [IDEAS.md](IDEAS.md) is the speculative archive (competitive analysis, format research, architecture notes, unpromoted features). Ideas promote from IDEAS.md into PLAN.md when we commit to building them; after they ship, the detail in PLAN.md collapses to a summary while the code becomes the authoritative record.

---

## Status (as of 2026-04-23)

**Tests:** 1177 passing, 25 skipped. Full-suite `pytest`, `ruff check`, and `ty check` are green. Zero `TODO` / `FIXME` tags. CI green on all three OSes (Ubuntu, macOS, Windows).

**Polish pass complete.** Phases 1–4 + 6 + 7 are shipped; Phase 5 was dropped by design. R-series (R.1–R.26) all done or intentionally dropped. Sharpening pass (Waves 1–4) done. The Pre-release polish pass (items 0–6) landed 2026-04-22 — see summary under "Phases shipped" below.

**Current eval baseline: 42/45 passing (93%)** across haiku / sonnet / opus on 15 tasks — up from the previous 33/33 on 11 tasks once the task set was expanded and the harness began isolating metadata state per run. The three remaining failures are all `model-mistake` (strict required-command grading), zero `qdo-bug`.

**Pre-beta audit pass in flight (2026-04-23).** A multi-agent audit simulated first-contact across docs, CLI help + error messages, tutorials + SKILL files, and release artifacts. Findings are tracked as a tiered punch list under "Pre-beta audit pass — active" below. Item 7 of the pre-release pass (real dogfood) is still to follow; the audit is a pre-dogfood sanity sweep, not a replacement.

Positioning and "what sets qdo apart" live in [DIFFERENTIATION.md](./DIFFERENTIATION.md). That's the cold-start doc for humans and agents re-entering the project.

---

## Pre-beta audit pass — active

A multi-agent audit on 2026-04-23 simulated first-contact with the project across five angles: fresh-user Quick Start walkthrough, public-docs consistency, CLI help + error-message quality, tutorials + agent-integration polish, and release-artifact completeness. Tier ordering is by damage to the first-contact story, not implementation cost.

Convention: each item has what's wrong, where (file:line when known), and a one-line fix sketch. Tick `[x]` when shipped. **Deferred** items stay on the list with a rationale so we don't forget the decision.

### Tier 1 — Bugs in the documented happy path

Users will hit these in the first ten minutes of following the README if we don't fix them.

- [x] **README Quick Start `--from scratch:1` example fails out of the box.** `README.md:144-148` records a rich-format query then replays it — `--from` rejects the step because only structured (`-f json`) steps carry canonical SQL. Fixed by adding `-f json` to the recording step in both `README.md` and `docs/cli-reference.md` (same broken pattern at 179-181), with a one-line lead-in explaining why. Verified end-to-end: recording + replay + export from session step all work.
- [x] **`metadata suggest --apply` missing-extra hint renders as `uv pip install 'querido' or 'querido'`.** Rich was eating `[duckdb]` / `[snowflake]` as markup tags. Fixed by wrapping the hint / try_next cmd / try_next why strings in `rich.markup.escape` at the display site (`src/querido/cli/_errors.py::_emit_rich_error`). Added regression test `test_emit_rich_error_preserves_bracketed_text_in_hints` so the bug can't return silently.
- [x] **`qdo metadata list` reports 0% completeness right after `metadata suggest --apply` writes fields.** Verified: two scoring paths disagreed — `metadata list` used a private `_calc_completeness` counting only human fields (descriptions, owner), while `metadata score` used the newer `score_table` rubric crediting valid_values + freshness too. Fixed by converging `list_metadata` on `score_table` and removing the dead helper. Post-`init` now reads 20% (freshness-only); post-`suggest --apply` jumps to 50% as valid_values are credited. Test updated to pin the new behavior and document the regression.

### Tier 2 — Credibility drift

Low-effort trust fixes. Every mismatch between docs costs a reader's confidence.

- [x] **Eval score stale in DIFFERENTIATION.md and SKILL.md.** Updated `DIFFERENTIATION.md:167` and `SKILL.md:11` to "42/45 (93%) on 15 tasks" with the note that the three failures are `model-mistake`, not `qdo-bug`. `DIFFERENTIATION.md:163` updated to 1177 passing tests.
- [x] **DIFFERENTIATION.md snapshot block stale.** Refreshed the entire "Current state" section: snapshot date → 2026-04-23, tests → 1177, eval → 42/45, and dropped the stale "gaps worth closing: sql, snowflake" line since those now emit envelope (pre-release polish item 5).
- [x] **`ARCHITECTURE.md:65,106` still lists `search` in `metadata.py` comments.** Resolved as not-a-bug: the `search` reference is to `qdo metadata search` (a real subcommand that still exists), not the cut top-level `qdo search` (removed in 068c09e). Audit agent conflated the two. The actual issue — `metadata search` being undocumented in public docs — is tracked separately as Tier 3 item 1.
- [x] **`pyproject.toml` missing metadata for a public listing.** Added `authors`, `[project.urls]` (Homepage / Repository / Issues / Changelog / Documentation), 12-item `keywords`, 15-item `classifiers` (Beta dev status, MIT license, Python 3.12/3.13, Typed, etc.), and sharpened the `description` to match DIFFERENTIATION's agent-first framing. `uv sync` still green.
- [x] **No `CHANGELOG.md`.** Added Keep-a-Changelog-style `CHANGELOG.md` with a curated v0.1.0 entry framing the compounding-loop story, enumerating the major capabilities (context, metadata, bundles, workflows, agent output, sessions, reports, TUI), and listing the polish passes that shaped it. `[Unreleased]` section captures the Tier 1 audit fixes. Added `Changelog` entry to `pyproject.toml` `[project.urls]` pointing at it.
- [ ] README badges (CI / PyPI / license / Python version) — **deferred**. Revisit if/when the project publishes to PyPI. The decision is to launch without badges rather than add placeholder ones.

### Tier 3 — Surface inconsistencies

Small mismatches where two surfaces disagree with each other.

- [ ] **`qdo metadata search` is a real command but undocumented.** Missing from `README.md`, `docs/cli-reference.md`, `integrations/skills/SKILL.md`, `AGENTS.md`, `integrations/continue/qdo.md`. Separate from the already-cut top-level `qdo search`. Fix: document in all five, or hide / remove if it's effectively unfinished.
- [ ] **`integrations/continue/qdo.md` drifts from `SKILL.md` on `-f json` promotion.** SKILL harmonized to explicit `-f json` per call; continue.md still leads with `export QDO_FORMAT=json`. Fix: align continue.md, or add a short note flagging the divergence and why.
- [ ] **`--connection` help text inconsistent across commands.** Some commands say "Named connection or file path"; others say just "Named connection" (e.g. `src/querido/cli/metadata.py:69` for `metadata show`). Fix: standardize on "Named connection or file path" everywhere the command accepts both.
- [ ] **`--sample-values` help text drift.** `src/querido/cli/context.py:25-28` explains non-numeric-column scope; the metadata init variant just says "Number of sample values per column". Align to the context wording.
- [ ] **Sampling / write flags weak on side effects.** `--quick` doesn't say it disables detailed stats; `--plan` doesn't say it requires `--write-metadata`; `--write-metadata` doesn't mention the YAML file write or the `confidence: 1.0` preservation rule. Fix: one-sentence additions to the Typer `help=` strings on `profile`, `quality`, `values`, `metadata suggest`.
- [ ] **Error "Session step is not structured" is jargon with no `try_next`.** `src/querido/core/session.py:271` raises a plain `ValueError`. Fix: rewrite to say the step was recorded as rich output — rerun the source step with `-f json` (or `QDO_FORMAT=json`) so `--from` can replay it. Promote to a structured error with a stable `code` so the envelope includes `try_next`.
- [ ] **SKILL.md "Gotchas" section mixes agent concerns and operator concerns.** Currently lumps table-name case, Parquet syntax, `QDO_METADATA_DIR`, and metadata merge behavior. Fix: split into agent-gotchas (case, Parquet, Snowflake, merge) and operator-gotchas (metadata dir, refresh-vs-init, wide-table thresholds).

### Tier 4 — Real gaps before beta

Actual product-surface changes. Each warrants a brief think before diving in; consider promoting any of these to its own tracked item if scope grows.

- [ ] **No `qdo config remove`.** `add` + `clone` exist; removing a connection means hand-editing `connections.toml`. Fix: add `qdo config remove --name <n>` with a confirmation prompt + `-y/--yes` bypass.
- [ ] **`qdo config add --type duckdb` succeeds silently without the `[duckdb]` extra installed.** Every subsequent use of that connection then fails. Fix: at `config add` time, probe importability of the backend and print a warning (not an error — user may install the extra next) pointing at `uv pip install 'querido[duckdb]'`. Same for `[snowflake]`.
- [ ] **SKILL.md has no dedicated `quality` section.** `context` gets a full treatment with JSON shape; `quality` is only mentioned in the drill-down list. Agents don't learn when to reach for it. Fix: add a `## quality — detect data issues` section with syntax, JSON output shape, and when to pick it over `context` + `values`.
- [ ] **`qdo tutorial explore` still teaches the old single-command tour.** 15 lessons run `catalog → inspect → preview → profile → dist → values → query → pivot → export`. Skips `context` (which does inspect + preview + profile in one), never lands the `values --write-metadata → context → quality` compounding story, and doesn't point to `qdo tutorial agent` as the upgrade path. Fix: re-sequence around `context` early; add a lesson showing metadata capture with `suggest --apply`; finish with a pointer to `qdo tutorial agent`.
- [ ] **`qdo tutorial agent` Lesson 13 names SKILL files vaguely.** Current copy says "integrations/ directory". Fix: name Claude Code vs Continue.dev files explicitly — `integrations/skills/SKILL.md` and `integrations/continue/qdo.md` — so the learner knows which to load next.
- [ ] **`docs/examples/` metadata fixture may use outdated field names.** `orders.yaml` field names to cross-check against current `qdo metadata init` output. Fix: regenerate the example from current qdo and diff.
- [ ] **`qdo report table` without `-o` silently opens a tempfile.** Output currently just says `Opened /var/folders/.../qdo-report-orders-*.html`. Fix: add a one-line note: "Tempfile — pass `-o <name>.html` to keep a permanent copy."

### Tier 5 — Polish

Small nice-to-haves. Can run in parallel with the tiers above.

- [ ] **`.github/ISSUE_TEMPLATE/` + `.github/PULL_REQUEST_TEMPLATE.md` missing.** First reports will be unstructured. Fix: add `bug-report.md`, `feature-request.md`, and a short PR template.
- [ ] **`qdo --help` tagline is weaker than the README's.** Currently "Agent-first data exploration CLI". Bring the value prop forward — e.g. "Accumulate understanding of your data. Agent-first." Fix: update the root Typer app `help=`.
- [ ] **`--from <session>:<step>` help doesn't explain valid step indices.** Fix: extend help to `"<session_name>:<step_index>, e.g. 'my-session:3' or 'my-session:last'"`.
- [ ] **`AGENTS.md` is ~506 lines and overlaps ARCHITECTURE.md.** Fix: tighten to <250 lines focused on contributor workflow + invariants, delegating implementation detail to ARCHITECTURE.md.
- [ ] `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md` — **deferred** until there's concrete pull to add them (outside contributor appears, or a wider announcement).

### Progress tracker

- Tier 1: 3 / 3 ✅
- Tier 2: 5 / 5 ✅ (+1 deferred)
- Tier 3: 0 / 7
- Tier 4: 0 / 7
- Tier 5: 0 / 4 (+1 deferred)

**Total: 8 / 26 shipped, 2 deferred.** Update these counts as items tick.

---

## Picking up after dogfood

When you return from dogfooding, start here. In order:

1. **Triage dogfood findings first.** Anything that made you wince while using qdo on a real project is signal. Drop each finding into one of three buckets and record it:
   - **Bug** — something obviously wrong. Open an issue or write the fix; high priority.
   - **Friction** — workflow was technically possible but awkward. Add to this file as a new line in the relevant place (either promote to an active track if it's small, or queue under "Deferred / future phases" with a one-sentence description of the frustration).
   - **Desire** — "wish qdo could do X." Add to [IDEAS.md](./IDEAS.md) under the appropriate subsection; don't promote until there's a second data point that confirms it matters.

2. **If nothing major surfaced, tighten the known follow-ups below.** The Pre-release polish eval surfaced three small items worth picking up before any new feature work. See "Known non-blocker follow-ups" under the Pre-release polish pass section.

3. **If you want to ship a real next feature, these are the top candidates** (ordered by differentiation payoff, not implementation cost):
   - **Snowflake `RESULT_SCAN` reuse for chained queries** — meaningful perf win for the Snowflake depth story (one of qdo's ranked differentiators).
   - **`qdo freshness` + `qdo diff --since <snapshot>`** — "what changed since last time?" is a recurring agent question that qdo is uniquely positioned to answer cheaply (freshness is already shipped; `--since` on diff is the promotion).
   - **MCP thin wrapper** — unlocks a whole new integration surface without fragmenting the CLI. Keep the CLI MCP-ready meanwhile (stable flags, structured errors, no TTY-required behaviors).
   - **Embedding layer on `metadata search`** — only if the lexical baseline shows actual user pain. Not speculative.

4. **Re-run the eval** after any SKILL.md change or command-surface change: `unset ANTHROPIC_API_KEY; uv run python scripts/eval_skill_files_claude.py --models all --budget 7 --confirm-spend`. Current baseline is 42/45 (93%); any regression is signal.

5. **Re-read [DIFFERENTIATION.md](./DIFFERENTIATION.md)** before agreeing to anything large. The "filter for future changes" there is the first thing to apply to any proposed feature.

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

### Phase 7 — Human-facing output polish (done)

The agent-first core is in good shape. This track is about making the human experience feel intentional and high-signal too, especially in `qdo explore` and Rich terminal output.

**7.1 — TUI foundation / information hierarchy**

- Shipped: the `explore` sidebar is now a compact selected-column facts panel: type, null rate, distinct count, min/max, sample values, metadata description, allowed values, and quality flags.
- Shipped: the status bar now carries connection, table, displayed/total rows, filtered state, sampled/exact state, sort state, metadata presence, and focused-column triage context.
- Shipped: semantic highlighting in the main `DataTable` now makes PKs, sorted columns, null-heavy columns, and null cells visually obvious.
- Shipped: the main grid, sidebar, and status bar now share the same triage story for the selected column (category + recommended/background emphasis) instead of acting like separate surfaces.
- Outcome: the structural hierarchy work is complete; any further changes here would be optional aesthetic follow-up, not unfinished scope.

**7.2 — Human-readable scan output**

- Shipped: Rich output for `quality`, `profile`, `catalog`, `inspect`, `preview`, `values`, and `dist` now uses compact headers, summary panels, and clearer section titles.
- Shipped: `context` now matches the same summary-panel / detail-table standard as the rest of the human-facing scan commands.
- Outcome: the main presentation gap is closed. Lightweight inline bars / sparklines can stay a future nice-to-have unless a concrete use case appears.
- Keep the JSON / agent shapes unchanged; this phase is about human presentation, not output-contract churn.

**7.3 — Wide-table and triage UX**

- Shipped: the wide-table profile path now explains quick triage, shows recommendation defaults, and labels the selector so the fast-path/full-path transition is legible.
- Shipped: the profile modal now explains whether the user is in quick mode or a full profile, and whether full stats are scoped to all columns or a chosen subset.
- Shipped: the main `explore` grid now orders wide tables recommended-first, pushing sparse/constant columns to the back instead of treating every field as equal-weight.
- Outcome: the missing workflow problem is solved; further work here would be small ergonomic tuning only.

**7.4 — Visual coherence**

- Shipped: the TUI and Rich terminal output now share more of the same emphasis rules (summary-first framing, status badges, triage language, recommended/background distinctions).
- Shipped: reproducible `qdo explore` screenshots now live under `docs/examples/screenshots/`, and the README / examples / cheatsheet reference them directly.
- Shipped: the docs consistency sweep removed stale `serve` / `web` references and brought the public TUI descriptions in line with the current product.
- Outcome: the obvious cross-surface inconsistencies are gone. A later aesthetic pass is optional, not part of the committed Phase 7 tranche.
- Preserve the existing CLI / workflow surface; this is a presentation pass, not a redesign of command semantics.

---

## Pre-release polish pass — done

Items 0–6 shipped 2026-04-22. The goal was closing the gap between the product and how it's described, not adding features.

- **0. Unblock CI** — PR #59 left CI red on all three OSes. Two root causes: ruff 0.15.5 line-wrap reformatting 10 files, and a Windows-specific `UnicodeEncodeError` where `cp1252` stdout can't encode Rich's bullets. Fixed by running `ruff format` and reconfiguring stdout/stderr to UTF-8 with `errors="replace"` at the CLI entrypoint — benefits any Windows user piping qdo output, not just the eval.
- **1. Docs accuracy audit** — `ARCHITECTURE.md` file trees refreshed (added `freshness`, `argv_hoist`, `estimate`, `plan`, `sql_safety`, `metadata_score`, `metadata_write`; dropped `search`). `README.md` "Investigate Deeper" restored the 5 missing commands. `docs/cli-reference.md` + `docs/qdo-cheatsheet.html` gained `freshness`. `SKILL.md` harmonized on explicit `-f json` per invocation (env-var `QDO_FORMAT` is a supported shortcut, not the promoted default).
- **2. "Why qdo" block** — added to top of `README.md` and `SKILL.md`: the compounding-loop pitch, a small ASCII diagram, and the self-hosting eval cited as credibility. See also [DIFFERENTIATION.md](./DIFFERENTIATION.md).
- **3. Marginal command decisions** — `qdo search` CUT (removed from code and docs); `qdo overview` KEEP (docs generator); `qdo tutorial agent` KEEP (teaches the differentiating metadata workflow). See IDEAS.md "Rejected Or Dropped" for the search rationale.
- **4. Sampling-flag harmonization** — `--no-sample` and `--sample` help text aligned across `context` / `profile` / `quality`. `--sample-values` stays unique to `context` (only context emits sample values). `-s` is now `--sample` (rows) everywhere — previously ambiguous between `--sample-values` on context and `--sample` on the other two.
- **5. Envelope on `sql` + `snowflake`** — `sql select/insert/ddl/task/udf/procedure/scratch` now wrap generated SQL in the standard envelope under `-f json` / `-f agent`. `snowflake semantic/lineage` envelope their YAML / object payloads. Rich / csv / markdown still print raw SQL / YAML for piping. Envelope contract tests extended to cover `sql select/insert/ddl/udf/scratch`.
- **6. Re-run the eval** — **42/45 (93%)** across haiku / sonnet / opus on 15 tasks, up from 39/45 on the first re-run. The bump came from isolating `QDO_METADATA_DIR` into the eval scratch dir (D2 stopped spuriously failing on leftover fixture metadata) and filtering non-qdo tool errors from the qdo-bug category (D4 stopped failing when models ran `unzip` as a sanity check). The three remaining failures (B1 on sonnet, C1 on opus, D4 on haiku) are all `model-mistake` — strict required-command grading against valid alternative paths.

**Item 7 — dogfood — is the only remaining pre-release item.** It's owned by the project maintainer, not the code.

Key commits from this pass (`main`):
- `f8153b8` — Windows UTF-8 stdout + ARCHITECTURE.md trees
- `500bd08` — README / cli-reference / cheatsheet missing commands
- `d6f94e6` — Why qdo block in README and SKILL
- `505bc97` — SKILL `-f json` harmonization
- `068c09e` — Cut `qdo search`
- `88b6ba9`, `abf7dbf` — Sampling flag + `-s` harmonization
- `e2ce1ed` — Envelope on sql + snowflake
- `d8e1a2d` — Eval metadata isolation + non-qdo error filter + SKILL values/dist sentence

### Known non-blocker follow-ups from the eval

Surfaced by the final 42/45 run. None are release blockers. Pick up opportunistically, ideally alongside related work.

- **Strengthen `values` vs `dist` guidance further.** The SKILL.md sentence landed in `d8e1a2d` helped haiku pass B1 but didn't shift sonnet off `dist` for an enum-listing task. If the next eval re-run still has sonnet on B1, consider a concrete "for enum-style tasks, `qdo values --counts` is the answer" phrasing — or teach `values` to emit counts natively so the path ambiguity disappears.
- **`quality` vs `context+values+query` on quality-issue prompts.** Opus regressed from 15/15 to 14/15 by taking a manual answer path (context → values → query) instead of `qdo quality` on C1. This is run-to-run model variance more than a SKILL bug, but if it repeats the fix is either a stronger "for anomaly-oriented review use `quality`" nudge in SKILL, or loosening C1's `required_commands` to accept any of `[quality, context, values]`.
- **Bundle workflow completeness on haiku.** D4 requires `qdo bundle inspect` as a workflow step after `export`. Haiku skipped it. SKILL could spell out "bundles are meaningful to hand off only after `inspect` confirms the contents" — a one-sentence tweak in the bundles section.
- **Eval task definitions — alternative-command support.** Currently `required_commands` is a hard list. A `required_any_of` / `required_one_of` primitive would let us accept `values` OR `dist` for B1-style questions without losing the gate. Cheap harness change.
- **`QDO_SESSION_DIR` env var.** The eval harness currently isolates metadata via `QDO_METADATA_DIR` but can't isolate sessions the same way — the session recorder uses `Path.cwd()`. Adding a parallel env var would close the last remaining cross-run-pollution hole in the eval; also useful for any tool that spawns qdo.

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

- Optional embedding/reranker layer for `qdo metadata search` if the lexical baseline proves insufficient.
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
