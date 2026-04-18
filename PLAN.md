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

## Review findings (2026-04-17)

Critical + tactical review conducted before starting Phase 6. One item (R.1) is a structural gap in the Phase 1 compounding loop; everything else is polish or consistency. Triage each bullet (do / defer / drop) before scheduling work.

### Resume point

R.1–R.22 are **done or dropped**. Also done via R.13: Phase 6.2 + 6.3 (`qdo serve` fully removed — `src/querido/web/`, `cli/serve.py`, `tests/test_web.py`, `tests/test_serve_cli.py`, `[web]` extra all gone).

Remaining review work: **R.23 through R.26 (traditional code quality)** — all small, none blocking. See the section of the same name below. Pick any of them up independently; R.23 will clean up the `except Exception` rationale comments R.22 left behind in `core/catalog.py` and `core/bundle.py`.

Outside the R-series: **Phase 6.1** (`qdo report session` HTML) is the next planned work after review items settle.

Test baseline as of this session: **894 passing, 24 skipped**. `ruff format`, `ruff check`, `ty check` all green.

### Critical — blocks Phase 6

#### R.1 — Close the metadata read-back loop — **done (2026-04-17)**

- [x] Added `load_column_metadata()` shared reader in `core/metadata.py` (unwraps provenance dicts, filters placeholders)
- [x] `core/profile.py`, `core/quality.py`, `core/values.py` accept `connection=` and merge stored `description` / `valid_values` / `pii` / `temporal` / `likely_sparse` onto their output
- [x] `core/quality.py` runs an enum-membership check when `valid_values` is stored; violating rows surface as `invalid_count` + an `issues` entry + elevated status
- [x] Fixed a latent bug in `core/context.py` that was reading `stored_metadata["columns"]` as a dict when it's actually a list; now uses the shared helper
- [x] `core/next_steps.py` no longer nags to capture `valid_values` when they're already stored; points at `qdo values --write-metadata` instead of `qdo metadata edit`
- [x] New `tests/test_readback_loop.py` covers the write→read compounding round-trip (profile / quality / values / context) including the enum-violation flagging

**Why:** metadata is written today but never read back by the commands that would benefit. Only `core/context.py:119-126` merges stored metadata into output. An agent running `profile` twice on the same table gets identical output regardless of what the first run wrote — the compounding thesis isn't actually compounding. Fixing this is what turns Phase 1 infrastructure into the moat.

**Acceptance:** run `qdo values -t orders -C status --write-metadata`, then `qdo profile -t orders`; `status.valid_values` appears in the profile envelope without a second `values` call. Test covers the round-trip.

**Effort:** 1–2 days.

### Strategic gaps

#### R.2 — Close envelope coverage gaps — **done (2026-04-17)**

- [x] Wired `assert`, `explain`, `pivot`, `view-def`, `template` through `emit_envelope()` with new `for_assert`/`for_explain`/`for_pivot`/`for_view_def`/`for_template` rules in `core/next_steps.py`
- [x] Documented `export` as an intentional bypass — its output IS its data (CSV/TSV/JSON/JSONL to file or stdout), not metadata about it; global `-f` is a no-op and it never reached `dispatch_output`
- [x] Replaced the silent `agent → json` downgrade in `cli/_pipeline.py:229-244` with a stderr warning naming the command; falls back to JSON so callers aren't broken. After the five wires above, the only commands that still trip the warning are `metadata show/list`, `snowflake` commands, and the internal `frequencies`/`classify` dispatches (out of R.2 scope)
- [x] Extended `_ENVELOPE_CASES` in `tests/test_next_steps.py` with four new rows (assert, explain, pivot, template); `view-def` gets its own envelope-contract test because it needs a view fixture the default `sqlite_path` doesn't provide
- [x] Added unit tests for each new rule — `for_assert` (pass vs fail), `for_explain` (duckdb analyze nudge vs sqlite skip), `for_pivot` (empty vs populated), `for_view_def` (with/without definition), `for_template` (with/without table comment)
- [x] Drive-by: `for_query`'s export suggestion was pointing at `--format csv`, which hits the global flag and is a no-op on export. Fixed to `--export-format csv` + a test guarding the fix

**Effort:** ~half day (under estimate).

#### R.3 — Gate the `-f agent` token-savings claim in CI — **dropped (2026-04-17)**

**Decision:** the `scripts/benchmark_agent_format.py` one-off is sufficient. Run it manually after any TOON encoder or envelope-shape change if you want a number. The "40%" figure was a Phase 2.1 acceptance target, not a product guarantee — drift within a few percent doesn't meaningfully change the tool. Not worth a CI-pinned tiktoken dep or maintenance overhead.

#### R.4 — Signal serialization format in envelope `meta` — **done (2026-04-17)**

- [x] `emit_envelope()` stamps `meta.serialization = "toon" | "yaml"` before printing the agent envelope (tentative-toon-then-fall-back-to-yaml so the optimistic path is one encode call)
- [x] `-f json` envelopes are unchanged — no redundant field (json is always json)
- [x] Routing rule documented in `emit_envelope()` docstring: tabular → TOON, nested / unsupported shapes → YAML. The underlying TOON v1 shape constraints live in `querido.output.toon`
- [x] `render_agent()` kept as a thin wrapper for the non-envelope callers (the error path in `cli/_errors.py`) — those payloads are flat dicts and don't need a serialization tag
- [x] Tests: `test_agent_meta_signals_toon_when_tabular`, `test_agent_meta_signals_yaml_when_falling_back`, `test_agent_meta_serialization_absent_on_json` in `tests/test_agent_format.py`

#### R.5 — Round-trip tests for `-f agent` — **done (2026-04-17)**

- [x] YAML-fallback round-trip: `test_yaml_round_trip_catalog` / `test_yaml_round_trip_context` parse the `-f agent` output back via `yaml.safe_load` and assert envelope shape + data preservation
- [x] Edge cases covered: unicode sample values (`test_yaml_round_trip_preserves_unicode`), null-heavy rows (`_handles_null_heavy_rows`), 0-row table (`_handles_empty_table`), values with colons/quotes/newlines (`_handles_special_characters_in_values`)
- [~] TOON round-trip: **intentionally skipped**. No in-tree decoder — writing one would share bugs with the encoder. Encoder correctness is already covered by the 118-case vendored spec fixtures in `tests/test_toon.py`. Documented in `tests/test_agent_format.py`'s R.5 section comment.

**Note:** the empty-catalog edge case (initially drafted) turned out to hit the TOON path, not YAML — an empty `tables` list on a flat envelope is TOON-expressible. Replaced with empty-table context, which still goes YAML because of the nested columns array.

#### R.6 — Workflow step timeout — **done (2026-04-17)**

Four layers of configurability, not just the per-step field originally spec'd:

- [x] JSON schema: top-level `step_timeout` + per-step `timeout`, both non-negative integers
- [x] Runner: `_resolve_step_timeout()` resolves effective timeout with precedence **CLI flag → `QDO_WORKFLOW_STEP_TIMEOUT` env var → step `timeout:` → workflow `step_timeout:` → 300s default**. `0` at any layer = unbounded, but higher layers still win
- [x] CLI: `qdo workflow run --step-timeout INT` flag (runtime override)
- [x] `StepFailed` grows `timed_out: bool` and `timeout: int | None` so callers distinguish timeout from normal failure; exit code is −1, message is `"Step 'x' timed out after 60s: ..."`
- [x] Lint: `INVALID_STEP_TIMEOUT` for negative values at either location; `UNKNOWN_STEP_FIELD` now accepts `timeout`
- [x] Docs: new "Step timeouts" section in `integrations/skills/WORKFLOW_AUTHORING.md` covers all four layers, precedence, `0 = unbounded` idiom, and when to opt up/down. Lint catalog row added
- [x] Tests (15 new): precedence across layers, zero-semantics, env-var parsing errors, `subprocess.TimeoutExpired` → `StepFailed(timed_out=True)`, CLI flag threads through, lint rejections

Note: the R.6 spec suggested 120s default. Moved to **300s** per user direction — Snowflake profiles on big tables legitimately take 2+ minutes, and the default should rarely fire on legitimate work.

#### R.7 — Structured workflow step-failure envelope — **done (2026-04-17)**

- [x] `cli/workflow.py:run` branches on `is_structured_format()` for `StepFailed` — emits a structured error payload to stderr with `{error, code, message, workflow, step_id, step_cmd, exit_code, stderr, session, try_next}`; raises `typer.Exit(1)` directly so `friendly_errors` doesn't double-render
- [x] Code values match the classifier convention: `WORKFLOW_STEP_FAILED` normally, `WORKFLOW_STEP_TIMEOUT` when `exc.timed_out` (adds `timed_out: true` + `timeout: <s>`)
- [x] Non-structured path is unchanged: stderr dumped verbatim, `WorkflowError` re-raised so `friendly_errors` renders the human-readable message
- [x] `StepFailed` now carries `session: str` (runner threads it in). `_emit_step_failure_envelope` uses it to offer a `qdo session show <name>` nudge as the first `try_next` entry
- [x] New `for_workflow_step_failed()` rule in `core/next_steps.py` produces deterministic follow-ups: session inspection, standalone step re-run, `--verbose` re-run, and (on timeout) `--step-timeout 0` escape hatch
- [x] `_STDERR_TAIL_BYTES = 4096` cap on the stderr copy into the envelope — generous enough for a traceback, tight enough to not blow agent context on runaway logs
- [x] Tests (7 new): CLI-level step-failure under `-f json`, under `-f agent`, non-structured mode unchanged, timeout case has `code=WORKFLOW_STEP_TIMEOUT` + `timed_out=true` + `timeout=1`, plus 3 unit tests for the new rule

### Consistency / interface

#### R.8 — Flag naming: `--column` vs `--columns` — **done (2026-04-17)**

Unified on `--columns` / `-C` everywhere. No deprecation aliases — clean break, since callers use the shared `-C` short form anyway.

- [x] `values.py` and `dist.py`: primary flag renamed to `--columns`; enforce exactly one column with a clear rejection (`--columns must name exactly one column for 'qdo values' (got 2: ...)`) when a CSV of length > 1 is passed
- [x] `profile.py` and `quality.py`: added `-C` short form to `--columns` (both previously had no short)
- [x] `core/next_steps.py`: 10 `--column` emissions in `for_context`, `for_profile`, `for_dist`, `for_values`, `for_quality` rules rewritten to `--columns`
- [x] Tests updated (`test_next_steps.py`, `test_readback_loop.py` — 8 sites) + 6 new tests: long-flag acceptance on values/dist, multi-value rejection on both, `-C` short on profile/quality
- [x] Docs/examples were already using the `-C` short form (SKILL.md, qdo.md, agent-workflow-example.md, bundled workflow YAMLs); no narrative changes needed

#### R.9 — Unify multi-action command groups — **done (2026-04-17)**

The real inconsistency was narrower than the PLAN text suggested: **metadata** was wrapping each of its 7 leaf actions in its own sub-`Typer` with `@callback(invoke_without_command=True)`, while every other group uses `@app.command()` directly. `config column-set save/list/show/delete` is a genuine CRUD sub-domain and earns its nesting.

- [x] `cli/metadata.py`: collapsed 7 sub-`Typer`s to `@app.command()` decorators. External CLI surface unchanged (`qdo metadata init`, `qdo metadata show`, etc. all work identically). ~43 lines removed.
- [x] `cli/config.py`: left alone. `config column-set save/list/show/delete` is a legitimate sub-domain — four CRUD verbs on a distinct resource (saved column sets vs connections).
- [x] `ARCHITECTURE.md` §8 — new "CLI Command Grouping" section documenting the rule: leaf actions use `@app.command()`; `add_typer` nesting is reserved for real CRUD sub-domains. The anti-pattern (wrapping every leaf in a sub-`Typer` for per-action help — which `@app.command()` already provides) is called out explicitly.
- [x] No test changes needed — 896 passing, external behavior identical.

#### R.10 — Envelope `command` field should match argv shape — **done (2026-04-17)**

Audit found every envelope emission already follows the convention: leaf commands = single token (`"inspect"`), nested = space-joined (`"bundle export"`, `"workflow list"`, `"metadata score"`), hyphenated = hyphen (`"view-def"`). All match `argv` exactly.

- [x] Formalized in `output/envelope.py:build_envelope` docstring — agents re-exec from this field, so the convention must match argv with no underscore/slash joining
- [x] `_MULTIWORD_COMMAND_CASES` contract test added in `tests/test_next_steps.py` (starts with `workflow list`; future nested commands are one-line additions to the parametrize list — analogous to the existing `_ENVELOPE_CASES` pattern)
- [x] No code changes needed — the convention was already being followed

#### R.11 — Apply `@friendly_errors` uniformly — **done (2026-04-17)**

AST-walk audit found 16 typer-decorated functions without `@friendly_errors`. All now decorated:

- [x] `config.py` — `add`, `list_connections`, `clone`, `test`, `column_set_{save,list,show,delete}` (8 functions)
- [x] `session.py` — `start`, `list_cmd`, `show` (3 functions)
- [x] `tutorial.py` — `tutorial` callback, `explore`, `agent` (3 functions)
- [x] `completion.py` — `show` (1 function)
- [x] `overview.py` — `overview` callback (1 function)

No intentional exceptions — every typer entry point now emits structured JSON errors under `-f json/agent` and a rich error message otherwise. AST-based audit in the session scratch can be re-run to catch future drift.

#### R.12 — Honor `--show-sql` in `context` — **done (2026-04-17)**

- [x] `core/context.py:_fetch_stats` now returns the primary stats SQL alongside the data (the DuckDB/Snowflake single-scan template or the SQLite profile template). `get_context` surfaces it in the return dict under `"sql"`.
- [x] `cli/context.py` calls `maybe_show_sql()` + `set_last_sql()` after the fetch — matches the pattern used by `profile`, `explain`, `assert`.
- [x] The SQL is also carried in the envelope's `data.sql` field (consistent with `pivot`), so agents can see what query backed the context without re-running with `--show-sql`.
- [x] Per-column frequency queries on the SQLite path are not surfaced — they're repetitive boilerplate; showing the profile scan is the useful signal. Documented in the `_fetch_stats` docstring.
- [x] 3 new tests: `--show-sql` emits on SQLite and DuckDB paths; envelope `data.sql` is present.

#### R.13 — Accelerate `qdo serve` deprecation — **done (2026-04-17, via full removal)**

Instead of the intermediate deprecation notice, collapsed Phase 6.2 + 6.3 into a single removal. No users yet — no migration cost.

- [x] Deleted `src/querido/web/` (FastAPI app, routes, static, templates), `src/querido/cli/serve.py`, `tests/test_web.py`, `tests/test_serve_cli.py` — 31 tests removed
- [x] Unwired the `serve` entry from `cli/main.py`'s lazy loader
- [x] Stripped the `Phase B (qdo serve)` comments from `output/html.py`
- [x] `pyproject.toml`: dropped the `[web]` optional extra; removed `fastapi`, `uvicorn`, `python-multipart` from `[all]` and from `[dependency-groups.dev]`; dropped `httpx` (was only for FastAPI `TestClient`)
- [x] `README.md`: removed install hint + "Interactive — TUI and web UI" shell (kept the TUI section)
- [x] `ARCHITECTURE.md`: removed the `web/` project-structure block, the `test_web.py` and `test_serve_cli.py` entries, the web-UI paragraph in §Output, and the `fastapi` / `uvicorn` rows from the dependency table
- [x] `AGENTS.md`: removed the "serve — local web UI" section
- [x] Jinja is kept (`report_html.py` still uses it for single-file HTML reports)
- [x] 869 passing, 24 skipped — down from 900 by exactly the 31 deleted tests

### Workflow subsystem polish

#### R.14 — Document format-flag auto-injection — **done (2026-04-17)**

Expanded the "Captures and format flags" section in `integrations/skills/WORKFLOW_AUTHORING.md` with a 4-row truth table covering the capture × explicit-flag matrix:

- **No capture, no flag** → inherits the outer format
- **No capture, flag set** → hoisted to root, respected
- **Capture, no flag** → auto-injects `-f json`
- **Capture, flag set (any value)** → hoisted as-is; **non-JSON value fails the capture at runtime** with the existing helpful error (`capture requires JSON output but parse failed`)

Also documented that flag position inside `run` doesn't matter (runner normalizes `-f X`, `--format X`, `--format=X`) and added a non-capture example showing `-f markdown` is legitimate when no capture follows.

#### R.15 — Tighten or document `expr.py` comparison semantics — **done (2026-04-17)**

- [x] `_apply_compare` now wraps ordering ops (`<`, `<=`, `>`, `>=`) in a try/except that re-raises `TypeError` as `ExpressionError` with the repr + type of both operands and a null-check hint: `cannot compare None (NoneType) > 0 (int) — null or mismatched types. Guard with an equality check first, e.g. \`${ref} != null and ${ref} > 0\`.`
- [x] `==` and `!=` untouched — they're already null-safe and that's the whole point of the guard idiom
- [x] **Latent bug fix**: `_eval_node` for `ast.BoolOp` was evaluating all children eagerly before applying truthiness. That defeated short-circuit — `${x} != null and ${x} > 0` would raise the ordering `TypeError` even when the left side decided the result. Rewrote to walk children one-at-a-time so the idiom actually short-circuits
- [x] Added `null` and `none` as YAML-style aliases for `None` in `_BOOL_NAMES` — `${x} == null` now works (previously only `${x} == None` did)
- [x] Documented in `WORKFLOW_AUTHORING.md` under "Conditional steps with `when:`" → new "Null-safe comparisons" subsection covering: the null-guard idiom, which literal spellings resolve to null, the no-coercion constraint, and the new error message shape
- [x] 6 new tests in `tests/test_workflow_runner.py` — null raises ExpressionError, message names both operands, type mismatch caught, equality still null-safe, null-guard short-circuits, all three null-literal spellings work

#### R.16 — Tighten `WRITE_WITHOUT_ALLOW` — **done (2026-04-17)**

Replaced the whole-line regex with statement-start detection scoped to the `--sql` value.

- [x] `_is_write_query` now: (a) only inspects `qdo query` invocations, (b) extracts the `--sql`/`-s` value (handles `--sql VAL` and `--sql=VAL`), (c) splits on `;` to get statements, (d) strips line comments (`-- ...`) and block comments (`/* ... */`), (e) checks whether the first word of each statement is in `_DESTRUCTIVE_FIRST_KEYWORDS`. Other tokens (connection names, table names, column names) are never examined.
- [x] `--file` / `-F` and stdin (neither flag present) can't be inspected at lint time — both conservatively trigger `WRITE_WITHOUT_ALLOW`. Authors either set `allow_write: true` or switch to inline `--sql`.
- [x] Documented in `WORKFLOW_AUTHORING.md` → "Destructive writes" section — added a "How the lint decides" subsection with the three common false-positive shapes that now pass, and a "Conservative fallback" note for file/stdin.
- [x] 8 new tests: column-name, connection-name, string-literal false-positives now pass; multi-statement destructive still flagged; leading comments + whitespace don't hide the keyword; `--file` and stdin conservative flag; `--sql=VAL` form parses.

#### R.17 — Log resolved step argv in workflow runner output — **done (2026-04-17)**

The runner already stored the fully-interpolated command in `StepRecord.run` — the only gap was that `cli/workflow.py`'s envelope stripped it out before emitting. One-line fix + test.

- [x] `cli/workflow.py` now includes `"run": s.run` on each `data.steps[]` entry in the `workflow run` envelope. Value is the shell-quoted, interpolated argv (same string the runner logs on `--verbose` and that the session's step-subprocess ends up recording).
- [x] Step-failure envelope already carried this via `step_cmd` — no change needed there.
- [x] Session logs already record the resolved argv (the `qdo` subprocesses run under `QDO_SESSION` and log themselves) — no change needed there either.
- [x] 2 new tests: resolved `run` appears with `${...}` interpolated + the connection path substituted; skipped steps still have the `run` key (empty string — contract-stable shape).

#### R.18 — Document lint error-code stability — **dropped (2026-04-17)**

No external consumers today — a written stability promise with nobody to enforce it against is marketing, not engineering. Tests already pin the codes by name (rename one → tests fail). Revisit if/when a real downstream tool starts acting on lint codes programmatically, or we plan a code rename worth signalling.

#### R.19 — Consolidate near-duplicate example workflows — **done (2026-04-17)**

Reworked `table-handoff.yaml` to teach a distinct pattern (conditional composition) rather than merging.

- [x] `table-handoff.yaml`: now gates `profile` on `${schema.data.row_count} != null and > 0` (the R.15 null-safe idiom) and gates `quality` on `${stats.data} != null` (chain-skip). Dropped the unused `sample_values` input (the prior comment said "passed through… in future" — aspirational, never wired). Comment header reframed to "conditional composition" teaching pattern.
- [x] `table-summary.yaml` left alone — still the canonical unconditional three-scan example. The contrast between the two is now load-bearing (one runs all three scans, the other gates them).
- [x] **Latent runner bug fixed**: a `when:` that referenced a skipped step's capture was raising `UnresolvedReference` → aborting the workflow. Reworked `run_workflow`'s when-eval to catch `UnresolvedReference` specifically and treat it as a skip (mirrors the `outputs` lenience policy). `ExpressionError` still aborts.
- [x] `integrations/skills/WORKFLOW_EXAMPLES.md` → rewrote the `table-handoff` entry to advertise the new pattern (null-safe `when:`, gated expensive step, chain-skip, graceful-null outputs).
- [x] 1 new test: `test_run_workflow_chain_skip_via_when_referencing_skipped_capture` asserts chain-skip works. Smoke-test on an empty table shows `schema` ran, `stats` skipped, `callouts` chain-skipped, outputs for skipped steps are `null`.

#### R.20 — Validate `from-session` drafts against target schema — **done (2026-04-17)**

Extended the existing `qdo workflow lint` with optional schema-aware checks rather than adding a new `validate` subcommand — keeps the surface area small and the workflow (`lint → run`) unchanged.

- [x] `core/workflow/lint.py:lint()` now accepts `valid_columns: set[str] | None`. When set, scans every step's `run` tokens for `-C` / `--columns` / `--columns=VAL` values, comma-splits, and case-insensitively checks each name against the set. Unknown names emit `UNKNOWN_COLUMN`. Values containing `${...}` are skipped (unresolvable at lint time). `--column-set` is not inspected (its value names a saved set, not columns).
- [x] `cli/workflow.py` lint gained `--connection`/`-c` + `--table`/`-t` + `--db-type` flags. Both connection and table must be set together or neither — single-flag usage raises `BadParameter`. When set, the CLI connects, fetches columns, and threads into `lint(valid_columns=...)`.
- [x] Documented in `WORKFLOW_AUTHORING.md` — new step 3 in "How to author efficiently" ("Schema-aware lint for from-session drafts") explains the flags, the from-session motivation, and the two known limitations (SQL inside `--sql` not parsed; check assumes one target table).
- [x] `UNKNOWN_COLUMN` added to the lint error catalog.
- [x] 9 new tests: no schema check without `valid_columns`; unknown columns flagged; known columns accepted; case-insensitive match (DuckDB vs Snowflake); `${ref}` values skipped; CSV lists handled; `--columns=VAL` form; CLI rejects single-flag usage; end-to-end CLI test using the sqlite fixture.
- [x] Smoke test: lint on an untouched draft → OK; same lint with `--connection --table` pointing at a table missing the referenced column → `UNKNOWN_COLUMN` at `/steps/0/run`.

### Traditional code quality

#### R.21 — Delete or wire up dead `null_count` templates — **done (2026-04-18, deleted)**

- [x] Confirmed no `render_template("null_count", ...)` callers exist and no dynamic path construction lands on `null_count`. Every caller that needs null counts gets them from a broader multi-column scan: `profile` (per-column columns in one select), `dist` (CTE), `context` (single-scan stats), `values` (window aggregate on grouped results), `quality` (inline aggregate build).
- [x] Deleted `src/querido/sql/templates/null_count/{common,duckdb,snowflake}.sql` and the empty `null_count/` directory.
- [x] Updated `ARCHITECTURE.md` project-structure block to drop the `null_count/` subsection.
- [x] No tests touched the template path (grep clean); `ruff format`, `ruff check`, `ty check`, `pytest` all green.

#### R.22 — Narrow broad `except Exception:` handlers — **done (2026-04-18)**

Narrowed 6 handlers to specific exception types; kept 5 broad with inline comments explaining the intentional fallback. All 11 sites listed in the original audit addressed:

- [x] Narrowed: `cli/report.py` + `cli/_errors.py` Click-context defensive reads → `(AttributeError, LookupError)`; `cli/overview.py` Click `list_commands` → `(AttributeError, TypeError)`; `config.py` atomic-write rollback → `OSError`; `core/metadata.py:_read_yaml` → `(OSError, yaml.YAMLError)`.
- [x] Kept broad with one-line rationale comment: `cli/overview.py:_print_json` introspection fallback (Typer/Click internals can fail in many ways), `core/catalog.py` bulk + per-table row-count fallbacks, `core/bundle.py:_fingerprint_for_table` + diff target-DB probe (driver errors vary by connector — R.23 will normalize through `ConnectorError`), `connectors/factory.py` parquet registration (close-and-reraise, untouched propagation).
- [x] Out-of-scope sites intentionally left for R.23 / R.11's friendly_errors decorator / TUI error display (`cli/_errors.py:74`, `cli/_pipeline.py:{79,121,128,153}`, `cli/config.py:237`, `tui/*`, `cache.py`, `core/context.py`, `core/workflow/loader.py`). These either already classify exceptions via `_classify_error`, surface them via the TUI, or intentionally swallow in best-effort background work.
- [x] `ruff format`/`ruff check`/`ty check`/`pytest` all green; 894 passing, 24 skipped — no behavioral change.

#### R.23 — Use connector error hierarchy consistently

- [ ] `connectors/base.py:42-63` defines `ConnectorError`, `TableNotFoundError`, `ColumnNotFoundError` — most code paths raise `ValueError` or bare `Exception`
- [ ] Route all connector-origin errors through the hierarchy; retire the fragile string-match classifier in `cli/_errors.py:200-224`

**Effort:** half day.

#### R.24 — Validate table names in `sample_source`

- [ ] `connectors/sqlite.py:101-121`, `connectors/duckdb.py:160-169` build SQL via f-string and trust callers
- [ ] Call `validate_table_name(table)` internally so integrations/tests can't bypass CLI validation

**Effort:** 30 min.

#### R.25 — Narrow `Any` in `arrow_util` and `bundle`

- [ ] `connectors/arrow_util.py:35` — `data: Any` → `PyArrowTable | list[dict]`
- [ ] `core/bundle.py` provenance helpers — introduce a TypedDict for provenance dicts
- [ ] Not blocking (ty passes); improves IDE autocomplete and reviewability

**Effort:** 1 hour.

#### R.26 — Document connector cache-key strategies

- [ ] `connectors/duckdb.py:70` lowercases; `connectors/snowflake.py:234` fully-qualifies uppercase
- [ ] Add a one-line docstring on each connector class explaining the convention

**Effort:** 15 min.

---

**Triage summary (post-2026-04-17 session).** R.1–R.20 all done or intentionally dropped (R.3, R.18). R.13 + Phase 6.2/6.3 collapsed into full `qdo serve` removal. Only R.21–R.26 remain — classic maintenance, none blocking. Test count grew from 842 (post test-cleanup baseline) to 894 as R.2, R.5, R.6, R.7, R.8, R.10, R.11, R.12, R.14, R.15, R.16, R.17, R.19, R.20 added named-invariant contract tests; R.13's removal subtracted 31 web/serve tests that no longer apply.

---

## Test-suite cleanup (2026-04-17) — done

Full arc (T.1–T.11) landed 2026-04-17. **Baseline: 871 passing, 19.65s. Final: 842 passing, 12.48s.** Net −29 deletions plus +11 new contract tests (T.3 envelope, T.5 readback) — about 40 tests' worth of redundancy/framework-noise removed while coverage of named invariants expanded.

### Where the rubric lives

**`AGENTS.md` → "Writing tests"** is the reviewer-facing test-philosophy rubric (seven rules: name the failure mode, test behavior not framework, exit code is not an assertion, parametrize over copy-paste, scenario coverage ≠ redundancy, integration for invariants / unit for pure logic, don't string-match error prose). Enforce on every new test.

### Extensible contract tests to build on

Two parametrized contract tests were introduced during the cleanup; extending either is a one-line addition in its `_*_CASES` list:

- **`_ENVELOPE_CASES`** in `tests/test_next_steps.py` — asserts 11 scanning commands emit the uniform `{command, data, next_steps, meta}` envelope. Extending it is the R.2 handshake: wire each bypass command through `emit_envelope()`, add a row, done.
- **`_READBACK_CASES`** in `tests/test_readback_loop.py` — asserts every `--connection`-accepting scan surfaces stored metadata on the next call. Template for future metadata-driven invariants.

A third (`test_validation_error_contract` in `tests/test_errors.py`, parametrized across 6 commands) centralizes the prose-matching error tests that will be rewritable against structured output once R.22/R.23 ship.

### Don't touch — already good

Files the cleanup explicitly spared; resist future pressure to shrink them:

- **`tests/test_toon.py`** (118 tests) — parametrized over vendored TOON spec-conformance fixtures. Model spec-implementation suite.
- **Per-rule scenario tests in `tests/test_next_steps.py`** — e.g., three `for_inspect_*` tests each exercise a distinct branch (populated / empty / no-comment), not the same assertion three times.
- **Dialect-specific `sql` tests where outputs genuinely diverge** — DDL types (TEXT vs VARCHAR), UDF syntax (Python `create_function` vs SQL `CREATE FUNCTION`). Keep both dialects.
- **`tests/test_readback_loop.py`** — 7 tests on the R.1 compounding-loop invariant.

### Lessons that apply to future audits

1. **Scenario coverage ≠ redundancy.** The initial audit over-estimated waste (~145 pitched deletions, ~40 delivered). Three tests per lint rule / per classifier rule / per error-path branch are each doing real work. Parametrize only when assertions are genuinely symmetric, not just when tests look similar.
2. **Spec-conformance suites are honest.** A file with 118 tests may be one `@pytest.mark.parametrize` over 118 fixture entries — appropriate for the shape.
3. **The real wins weren't deletions.** T.1 (shared tutorial-DB fixture, −7s wall time), T.3 (envelope contract: 3→11 commands covered), and T.5 (readback contract: extensible) moved the needle more than any individual trim.
4. **Brittle-prose tests often reflect product gaps, not test failures.** Validation errors in qdo go through `typer.BadParameter` and bypass the structured envelope; that's why `test_errors.py` tests had to prose-match. Fix the product (R.22 / R.23), not just the tests.

### Open items this cleanup deferred

- `tests/test_web.py` (29 tests) — tied to R.13; those tests vanish when `qdo serve` is removed.
- Structured-envelope rewrites of `test_validation_error_contract` / `test_missing_connection_file_contract` — one-file change after R.22/R.23 ship.

---

## Phase 6 — Session reports and cleanup (~1 week)

### 6.1 — `qdo report session` HTML

- [ ] Session-as-narrative: each step = card with title, one-line context, collapsed command (`<details>`), rendered output
- [ ] Optional per-step `--note` captured during the session renders as commentary
- [ ] Same single-file, offline, print-friendly constraints as Phase 2.2

**Acceptance:** run a 5-step session, export to HTML, email to someone without qdo installed, they can read it in a browser offline.

**Effort:** 2 days.

### 6.2 + 6.3 — Deprecate + remove `qdo serve` — **done (2026-04-17, collapsed into one step via R.13)**

The deprecation step was skipped (no users yet); the removal landed directly. See R.13 above for the full checklist. `tests/test_web.py` tie-in mentioned in the 2026-04-17 test-cleanup lessons section is now resolved — that file is gone.

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
