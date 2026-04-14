# Plan

Working todo list for making querido the agent-first data exploration CLI. Items are ordered by dependency; complete a phase before starting the next unless noted.

> **PLAN.md vs IDEAS.md.** This file is the committed, actionable todo list — items here have been scoped, sequenced, and are ready to work on. [IDEAS.md](IDEAS.md) is the speculative archive: research notes, competitive analysis, and features we haven't committed to yet. Promote ideas from IDEAS.md into PLAN.md when we decide to build them; don't duplicate between the two.

Each item: **what**, **why it matters**, **acceptance criteria**, **effort estimate**.

---

## Phase 1 — Agent-first foundations (~1 week)

The four items that together create the "tool gets better the more it's used" compounding loop. Do these first; everything else depends on them.

### 1.1 — `next_steps` field in every JSON output

- [x] Add a `next_steps: [{cmd, why}]` field to the JSON output of every scanning command (`catalog`, `context`, `inspect`, `preview`, `profile`, `dist`, `values`, `quality`, `diff`, `joins`, `query`)
- [x] Add `try_next: [{cmd, why}]` to structured error objects
- [x] Rules are deterministic (no LLM), based on output shape: row counts, null rates, distinct counts, metadata presence

**Why:** every command becomes a node in a traversable graph. Biggest single UX lever for agent workflows.

**Acceptance:** running any listed command with `-f json` returns a non-empty `next_steps` array whose entries are valid qdo invocations. Unit tests cover the rule for each command.

**Effort:** 2–3 days.

### 1.2 — Session MVP

- [x] `QDO_SESSION=<name>` env var — when set, every command appends a JSONL record to `.qdo/sessions/<name>/steps.jsonl` with: timestamp, cmd, args, duration, exit_code, row_count, stdout_path
- [x] Each step's full stdout saved to `.qdo/sessions/<name>/step_<n>/stdout`
- [x] `qdo session start <name>` / `qdo session list` / `qdo session show <name>`
- [x] No daemon, no DB, no server. Append-only files

**Why:** substrate for reports, bundles, workflow authoring, audit trail, and the `--from` patterns later. Collapses the separate audit-log and sql-history ideas into one feature.

**Acceptance:** running 5 commands under `QDO_SESSION=test` produces 5 JSONL rows and 5 stdout files; `qdo session show test` prints a readable summary.

**Effort:** 1 day.

### 1.3 — `--write-metadata` on scanning commands

- [x] Add `--write-metadata` flag to `profile`, `values`, `quality`
- [x] Flag writes computed stats to the table's metadata YAML with provenance fields per value: `source: profile|values|quality|human`, `confidence: 0.0–1.0`, `written_at: <session_id|timestamp>`, `author: $QDO_AUTHOR|git user`
- [x] Deterministic auto-fill rules: low-cardinality (<20) string → candidate `valid_values` (0.8); null_rate >95% → `likely_sparse: true`; column name matches `*_at/*_date` + timestamp type → `temporal: true`
- [x] Never overwrite a field with `confidence: 1.0` (human-authored) without `--force`

**Why:** turns metadata into a byproduct of normal exploration. Starts the compounding loop.

**Acceptance:** `qdo profile -t orders --write-metadata` updates `.qdo/metadata/<conn>/orders.yaml` with provenance-tagged entries; re-running doesn't duplicate; `--force` is required to overwrite human fields.

**Effort:** 2–3 days.

### 1.4 — Metadata scoring and suggestions

- [x] `qdo metadata score -c <conn>` — per-table completeness score (% of columns with description, % with valid_values where cardinality is low, freshness of profile stats)
- [x] `qdo metadata suggest -c <conn> -t <table>` — proposes additions as a diff from recent profile/values/quality runs; `--apply` writes them
- [x] Output includes a pointer in `next_steps` from commands that scan tables with low scores

**Why:** gives agents a measurable target and a non-preachy nudge toward improving metadata.

**Acceptance:** `qdo metadata score` produces a ranked report; `suggest --apply` writes provenance-tagged fields identical in shape to Phase 1.3's output.

**Effort:** 1 day.

---

## Phase 2 — Agent output + first shareable artifact (~1 week)

### 2.1 — `-f agent` output format

- [x] New agent renderer alongside JSON/rich/csv formatters (via `querido.output.envelope.render_agent` + the shared `emit_envelope` dispatch; no separate `AgentFormatter` class needed)
- [x] Tabular results → TOON (row-oriented, explicit row count, column header once; spec v3.0, in-tree encoder with vendored conformance fixtures)
- [x] Nested results (`context`, `metadata show`, `catalog`) → YAML fallback when TOON's v1 shape coverage doesn't fit
- [ ] Scalar results → single-line `key=value key=value` (deferred — everything has an envelope today; scalars roll up into nested object rendering)
- [x] Errors → structured payload rendered through the same TOON/YAML dispatch (includes `try_next` as a tabular array)
- [x] `QDO_FORMAT=agent` environment variable sets default

**Why:** TOON wins ~40% tokens on tabular data with equal-or-better accuracy; YAML wins on nested. Matching format to shape is the actual accuracy driver.

**Acceptance:** benchmark 5 representative commands with tiktoken; `-f agent` is ≥40% fewer tokens than `-f json` on tabular outputs. All outputs round-trip through a documented parser.

**Effort:** 2–3 days.

### 2.2 — `qdo report table` HTML

- [x] `qdo report table -c <conn> -t <table> -o <file.html>` — single self-contained HTML file (no `-o` opens in browser)
- [x] Inline CSS, inline SVG (null-rate bars), no JS required. Google Fonts via `@import` with system-font fallback
- [x] Content: header, metadata summary, schema table (PK/NOT NULL badges, null-rate bars, distinct counts, samples), quality callouts (fail/warn lists + emerald "all passed" panel), related tables from `joins`, collapsed "Generated with qdo" footer with the exact invocation
- [x] Dark mode via `prefers-color-scheme`; print-friendly CSS (`@media print`)

**Why:** gives users a polished artifact to hand to a PM or exec without asking them to install qdo. Strictly better than `serve` for the "share with a non-user" use case.

**Acceptance:** running the command produces a single HTML file that renders correctly offline in a fresh browser profile. Snapshot test on fixture DB.

**Effort:** 2–3 days.

---

## Phase 3 — Team sharing (~1 week)

### 3.1 — Knowledge bundle export/import MVP

- [x] `.qdobundle` format: directory or zip containing `manifest.yaml`, `metadata/*.yaml`, optionally `column-sets/*.yaml`
- [x] `qdo bundle export -c <conn> -t <tables> -o <file>` — package metadata with `schema_fingerprint` per table (hash of columns+types)
- [x] `qdo bundle import <file> --into <conn>` — preview diff by default, `--apply` writes; `--strategy keep-higher-confidence|theirs|mine|ask`
- [x] `qdo bundle diff a.qdobundle b.qdobundle`
- [x] `qdo bundle inspect <file>` — summary
- [x] `--redact` drops fields from PII-flagged columns

> Future: sessions in bundles.  IDEAS.md proposes shipping a session log alongside metadata so the "how we learned this" narrative travels with the facts.  Deferred — the `core/bundle.py` layout leaves a `sessions/` slot open for a follow-up phase.

**Why:** unlocks team-level compounding. One person's investigation makes the next person's agent smarter.

**Acceptance:** export from conn A, import into conn B with a different table name mapping, verify metadata appears on the matching table by schema fingerprint. Merge strategies behave per spec.

**Effort:** 3–4 days.

---

## Phase 4 — Workflows as extensibility (~2 weeks)

The biggest feature in the plan and the most prone to scope creep. Do Phase 1–3 first so the spec has real use cases to validate against.

### 4.1 — Workflow spec (JSON Schema)

- [x] Draft spec for YAML workflow files: `name`, `description`, `version`, `inputs` (typed), `steps` (with `run`, `capture`, `when`, conditional), `outputs`
- [x] `qdo workflow spec -f json` emits the JSON Schema
- [x] `qdo workflow spec --examples` emits bundled example workflows
- [x] Declarative only — no embedded code, no shell escape

**Acceptance:** spec is complete enough to express all conversions in Phase 5. Draft is reviewed before runner implementation begins.

**Effort:** 2 days for draft; revise as Phase 5 reveals gaps.

### 4.2 — Workflow runner and introspection

- [x] `qdo workflow run <name> [inputs...]` — execute, capture outputs, bind `${captures}`
- [x] `qdo workflow lint <file>` — structured errors with `{code, message, fix}` per issue
- [x] `qdo workflow list` — bundled + user + project workflows
- [x] `qdo workflow show <name>` — print the YAML
- [x] Every run auto-creates a session (auto-created if none)
- [x] Search paths: `./.qdo/workflows/` → `$XDG_CONFIG_HOME/qdo/workflows/` → bundled

**Acceptance:** `workflow run` executes a non-trivial example end-to-end; `lint` catches malformed YAML, unknown captures, and unsafe steps.

**Effort:** 3–4 days.

### 4.3 — `qdo workflow from-session`

- [x] Generate a draft workflow YAML from the last N steps of a session, parameterizing obvious inputs (connection, table)
- [x] Output passes `lint` on happy paths

**Why:** this is the agent-authoring bootstrap. Agents edit a draft instead of authoring from cold.

**Acceptance:** run a 5-step investigation, call `from-session`, resulting YAML lints clean and runs against the fixture DB.

**Effort:** 2 days.

### 4.4 — CLI sugar shim — **dropped**

**Decision (2026-04-14):** `qdo workflow run <name>` stays the canonical invocation. No top-level aliasing of workflows as `qdo <name>`.

**Rationale:**
- **Namespace collisions.** A user workflow at `./.qdo/workflows/profile.yaml` would either shadow `qdo profile` (confusing) or be shadowed by it (invisible). Either failure mode is silent.
- **Trust signal.** `qdo profile` today is a vetted, versioned, documented primitive. Sugar that lets any local YAML occupy the top-level namespace dilutes that signal.
- **Help bloat.** Mixing contract-stable commands with ad-hoc files in `qdo --help` hurts discoverability of the things we actually maintain.
- **Verbosity is a feature.** `qdo workflow run foo` tells the reader "this is a composition of primitives" — exactly what a workflow *is*. Hiding that in `qdo foo` obscures a useful distinction.

**Implications for Phase 5.** Conversions (see below) now each retain a thin Python entry point that delegates to the runner. The bounded boilerplate is acceptable and actually gives us a place to hang command-specific help text. If Phase 5 proves painful without the shim, revisit — but only for *bundled* workflows, never for user workflows.

### 4.5 — Agent-authoring documentation

- [x] `integrations/skills/WORKFLOW_AUTHORING.md` (new) — spec reference, worked examples, common patterns, anti-patterns, lint-error catalog
- [x] `integrations/skills/SKILL.md` — add "Writing workflows" section linking to the above
- [x] `integrations/continue/qdo.md` — mirror the additions for Continue
- [~] `integrations/playbooks/agent-recipes.md` — **dropped**; the "author from a recent investigation" recipe is in `WORKFLOW_AUTHORING.md`'s authoring loop instead. Avoids creating a directory for a single file.
- [x] `AGENTS.md` at repo root — document the agent-authoring loop, point at `WORKFLOW_AUTHORING.md`
- [x] Bundled workflows get inline `# why:` comments aimed at agents

**Why:** without these, agents produce plausible-looking YAML that doesn't run. This is on the critical path, not after it.

**Acceptance:** see Phase 4.6's self-hosting eval.

**Effort:** 2–3 days, parallel to 4.1–4.3.

### 4.6 — Self-hosting eval (Option 1, `claude -p`)

- [x] Script (`scripts/eval_workflow_authoring.py`) that feeds `WORKFLOW_AUTHORING.md` + `qdo workflow spec` + `qdo workflow spec --examples` + a task prompt to `claude -p --model claude-opus-4-6`
- [x] Writes result to scratch, runs `qdo workflow lint` + `qdo workflow run` against fixture DB (`data/test.duckdb`)
- [x] Pass = lint 0 + run 0 + shape assertion on the run envelope (golden files would flake on LLM nondeterminism; per-task shape check instead)
- [x] 3 target tasks the model has not seen (basic composition, conditional follow-up, diff→joins)
- [x] Billing guardrails: refuses to run if `ANTHROPIC_API_KEY` is set; 120s timeout per model call, 60s per workflow run
- [~] CI integration: **deliberately deferred.** `claude -p` needs a Max subscription and the eval isn't cheap. Documented in the script's module docstring; rerun locally after any docs/implementation revision. If we later automate, use `workflow_dispatch`-only GitHub Actions.

**Why:** the only objective signal that our agent docs are sufficient.

**Acceptance:** ≥2 of 3 tasks pass on frontier model; any failure drives a docs revision, not a model change.

**First run (2026-04-14, opus-4-6):** 2/3 passed. T1 and T3 passed cleanly. T2 (conditional `quality → context`) produced a lint-clean workflow that `qdo context` then crashed on (`TypeError: 'datetime.date' object is not subscriptable`). That's a qdo bug, not a docs issue — exactly the kind of signal the eval is meant to surface. File a tracking item; docs pass.

**Effort:** 1 day.

---

## Phase 5 — Subcommand conversions to workflows — **skipped**

**Decision (2026-04-14):** skip Phase 5 entirely.

**Rationale.** After Phase 4 landed, we looked hard at the conversion candidates (`template`, `sql scratch`, `pivot`, `joins`, `sql task/procedure`, `snowflake semantic`, `view-def`) and found none of them are natural compositions of existing qdo primitives. Every one is "fetch metadata, render it a specific way" — and the *rendering* is the differentiator, which workflows can't express. Converting them would require either adding a `qdo render` primitive (speculative, big design lift) or inserting a workflow layer that gathers data only to re-inject it into the existing Python rendering (performance regression, no ergonomic gain).

Workflows are better understood as a **composition layer for user investigations layered on top of primitives**, not as a replacement for renderer commands. The Phase 5 premise was wrong; we're closing the phase instead of forcing conversions through.

**What we did instead.** Authored four additional bundled workflows that showcase genuine composition patterns: `column-deep-dive`, `wide-table-triage`, `table-handoff`, `feature-target-exploration`. Each teaches a pattern not covered by the original two examples. See `src/querido/core/workflow/examples/` and `integrations/skills/WORKFLOW_EXAMPLES.md`.

**Related:** `feature-target-exploration` contains `# gap:` comments pointing at missing statistical primitives (outliers, correlate, feature-rank, etc.). The feasibility analysis lives in IDEAS.md → "Data-science primitives". **Decision deferred** — revisit based on real user demand.

---

## Phase 6 — Session reports and cleanup (~1 week)

### 6.1 — `qdo report session` HTML

- [ ] Session-as-narrative: each step = card with title, one-line context, collapsed command (`<details>`), rendered output
- [ ] Optional per-step `--note` captured during the session renders as commentary
- [ ] Same single-file, offline, print-friendly constraints as Phase 2.2

**Acceptance:** run a 5-step session, export to HTML, email to someone without qdo installed, they can read it in a browser offline.

**Effort:** 2 days.

### 6.2 — Deprecate `qdo serve`

- [ ] Stderr deprecation notice on `qdo serve` pointing at `qdo report` and `qdo explore`
- [ ] Before deprecation: confirm no meaningful user base via an informal check-in

**Effort:** 1 hour.

### 6.3 — Remove `qdo serve` (release N+1)

- [ ] Drop `serve` command, `web` optional extra, `src/querido/web/` templates, related tests
- [ ] Keep Jinja infrastructure (used by `report`)
- [ ] README updates

**Effort:** half day.

---

## Deferred / future phases (capture but don't start)

- `qdo investigate <table>` and friends — come for free once Phase 4 lands; ship as bundled workflows
- `qdo diff --since <session>` — change detection for returning agents
- `qdo freshness` — row freshness/staleness with auto timestamp-column detection
- Cost/time `--estimate` flag on `query` / `export`
- Read-only-by-default guardrail on `query` (`--allow-write` required)
- `--plan` dry-run flag on `export`, `query`, `metadata write`
- `qdo search "<intent>"` — BM25 over command docstrings
- `qdo catalog functions` — list DuckDB/Snowflake SQL functions
- Embedding-based semantic search across metadata
- `--from` flag to reference prior session step outputs (`qdo query --sql-from session1.step3`)
- Session replay (`qdo session replay <name>`)
- Metadata undo
- Progressive disclosure `--level 1..3`
- Snowflake RESULT_SCAN reuse for chained queries
- Pyodide `querido-lite` browser demo (only if concrete adoption use case pulls for it)
- MCP thin wrapper (defer; keep CLI surface MCP-ready)
- **Bug: `qdo context` on date/datetime columns.** Surfaced by the 4.6 self-hosting eval (2026-04-14, T2): running `qdo -f json context -c data/test.duckdb -t customers` raises `TypeError: 'datetime.date' object is not subscriptable`. Reproduce via the `customers` fixture.

---

## Principles that govern all work above

1. **Agent-first.** Every feature is evaluated on "does this make a coding agent's loop tighter, cheaper, or more correct?" If not, defer
2. **Deterministic tools, not LLM-in-the-loop suggestions.** Agents bring the brain; querido brings the memory and the map
3. **Files, not servers.** Sessions, metadata, bundles, workflows, reports — all plain files. No daemon, no platform
4. **Declarative extensibility, not plugins.** Workflows are YAML, not Python. No sandbox, no ABI
5. **Compose with the ecosystem.** DuckDB/Snowflake own execution. qsv owns row-oriented CSV wrangling. datasette owns hosted publishing. We own the agent-readable exploration + metadata + workflow loop
6. **Don't break existing CLI surface.** Conversions and removals preserve invocation names; deprecation always precedes removal

## Sequencing invariants

- Phase 1 before Phase 2, 3, 4 (sessions enable everything downstream)
- Phase 4.5 (docs) in parallel with 4.1–4.3, not after
- Phase 5 skipped (see phase header for rationale)
- Phase 6.1 depends on 4.2 (sessions must exist); 6.2–6.3 independent
