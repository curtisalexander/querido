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

**All review items R.1–R.26 are done or dropped.** Also done via R.13: Phase 6.2 + 6.3 (`qdo serve` fully removed — `src/querido/web/`, `cli/serve.py`, `tests/test_web.py`, `tests/test_serve_cli.py`, `[web]` extra all gone).

Next planned work: **Phase 6.1** (`qdo report session` HTML).

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

#### R.23 — Use connector error hierarchy consistently — **done (2026-04-18)**

- [x] Extended `connectors/base.py` with `DatabaseLockedError`, `DatabaseOpenError`, `AuthenticationError`, and `DatabaseError` (generic wrapper), plus `wrap_driver_error(exc)` helper that centralizes the dialect-agnostic message-pattern classifier in the connector layer.
- [x] Each connector's `execute()` + `__init__` / `execute_arrow()` catches its native driver error (`sqlite3.Error`, `duckdb.Error`, `snowflake.connector.Error`), runs `wrap_driver_error()`, and re-raises as the typed `ConnectorError` subclass (preserving the original as `__cause__`). Unclassified driver errors pass through untouched so tracebacks stay intact.
- [x] `cli/_errors.py` `_format_db_error` / `_error_code` / `_recovery_hint` rewritten to switch on `isinstance` against the hierarchy; the old 3-way string-match in `_error_code` + `_recovery_hint` is gone. `_is_db_error` kept as a fallback for raw driver errors that escape the connector wrap.
- [x] `cli/_pipeline.py:_maybe_reraise_as_table_not_found` dropped its string-match fallback — now a single `isinstance(exc, TableNotFoundError)` guard. The inner `except Exception` narrowed to `except ConnectorError`.
- [x] R.22 rationale comments retired: `core/catalog.py` bulk + per-table row-count fallbacks → `except ConnectorError`; `core/bundle.py:_fingerprint_for_table` → `except ConnectorError`; bundle diff target-DB probe → `except (ConnectorError, FileNotFoundError, ImportError, ValueError)`.
- [x] New tests (16): 5 connector-level (`test_sqlite_missing_table_raises_table_not_found`, `test_duckdb_missing_table_raises_table_not_found`, `test_sqlite_missing_column_raises_column_not_found`, `test_wrap_driver_error_unclassified_returns_none`, `test_wrap_driver_error_preserves_original_as_cause`) + 11-row parametrized `test_error_code_from_typed_exception` pinning the isinstance-based classifier for every code (`TABLE_NOT_FOUND`, `COLUMN_NOT_FOUND`, `DATABASE_LOCKED`, `DATABASE_OPEN_FAILED`, `AUTH_FAILED`, `DATABASE_ERROR`, `FILE_NOT_FOUND`, `VALIDATION_ERROR`, `MISSING_DEPENDENCY`, `PERMISSION_DENIED`, `UNKNOWN_ERROR`).
- [x] `ruff format`/`ruff check`/`ty check`/`pytest` all green; 910 passing (+16), 24 skipped.

#### R.24 — Validate table names in `sample_source` — **done (2026-04-18)**

- [x] `connectors/sqlite.py` + `connectors/duckdb.py` `sample_source` now call `validate_table_name(table)` before f-stringing; `connectors/snowflake.py` calls `validate_object_name(table)` (dotted names allowed).
- [x] Snowflake was missing from the original audit but had the same issue — three-connector fix instead of two.
- [x] 7 new parametrized tests asserting `ValueError` on four attack shapes (semicolon injection, SQL comment trailer, parens, leading digit) for SQLite + three shapes for DuckDB. Snowflake test coverage flows through its existing `_resolve_table` validation; no new fixture needed.
- [x] `ruff format`/`ruff check`/`ty check`/`pytest` all green; 917 passing (+7), 24 skipped.

#### R.25 — Narrow `Any` in `arrow_util` and `bundle` — **done (2026-04-18)**

- [x] `connectors/arrow_util.py` — introduced `ArrowOrDicts = pa.Table | list[dict]` alias under `TYPE_CHECKING`; `execute_arrow_or_dicts` return and `arrow_to_dicts` arg now use it instead of `Any`.
- [x] `core/bundle.py` — added `Provenance` TypedDict (`value: Any, source: str, confidence: float, written_at: str, author: str`) and changed `_is_provenance` return type to `TypeGuard[Provenance]` so `_confidence_of` / `_written_at_of` branches narrow correctly.
- [x] `ruff format`/`ruff check`/`ty check`/`pytest` all green; 917 passing, 24 skipped — pure annotation change, no behavioral diff.

#### R.26 — Document connector cache-key strategies — **done (2026-04-18)**

- [x] Added a class docstring to each connector explaining the `_columns_cache` key convention and why: `SQLiteConnector` → `table.lower()` (SQLite is case-insensitive for unquoted identifiers), `DuckDBConnector` → `table.lower()` (DuckDB folds to lowercase), `SnowflakeConnector` → fully-qualified `f"{DATABASE}.{SCHEMA}.{TABLE}"` uppercase (Snowflake uppercases + must disambiguate across schemas).
- [x] `ruff format`/`ruff check`/`ty check`/`pytest` all green; 917 passing, 24 skipped — docstring-only change.

---

**Triage summary (post-2026-04-18 session).** R.1–R.26 all done or intentionally dropped (R.3, R.18). R.13 + Phase 6.2/6.3 collapsed into full `qdo serve` removal. Test count grew from 842 (post test-cleanup baseline) to 917 as R.2, R.5, R.6, R.7, R.8, R.10, R.11, R.12, R.14, R.15, R.16, R.17, R.19, R.20, R.23, R.24 added named-invariant contract tests; R.13's removal subtracted 31 web/serve tests that no longer apply. R.21 (dead null_count templates) + R.22 (narrow `except Exception`) + R.23 (connector error hierarchy) + R.24 (sample_source validation) + R.25 (narrow `Any`) + R.26 (cache-key docstrings) landed 2026-04-18.

---

## Sharpening pass (2026-04-18)

Goal: verify the repo is delivering what we set out to build — a tool a new user + coding agent can sit down with and immediately use to explore data — and sharpen any edge where it isn't yet true. Scope is everything: direction, differentiation, onboarding, consistency, code quality, docs, eval design, cleanup candidates.

Broken into five tracks, three waves. Each track produces a bucketed findings list (prefix in parens). Findings land in this file as they arrive, organized by bucket. Obvious cleanups land inline between waves; judgment calls (drop/rename commands, large refactors) are escalated to the user.

### Tracks

1. **Cold-start simulation (CS.x)** — an agent reading only skill files + README + AGENTS.md (no code, no ARCHITECTURE.md) attempts four realistic tasks against the fixture DB. Logs friction points, skill-file claims that don't match reality, commands unreachable from docs.
2. **Command-surface audit (CA.x)** — per-command scorecard over all ~30 CLI commands: purpose, flag consistency, overlap, tutorial / example / test coverage. Verdicts: keep / merge / drop / rename.
3. **Docs & tutorial consistency (DC.x)** — walks AGENTS.md, README, SKILL.md, ARCHITECTURE.md, both tutorial runners, WORKFLOW_AUTHORING / EXAMPLES. Finds overlap, stale claims, contradictions with the current CLI.
4. **Code consistency sweep (CC.x)** — reads representative CLI + core + output + connector modules. Flags dead code, inconsistent patterns, unclear abstractions, security smells beyond what R-series caught.
5. **Eval-design proposal (EV.x)** — codifies the cold-start sim into a repeatable harness. Task taxonomy, pass criteria, billing guardrails. Design now, run later.

### Wave ordering

- **Wave 1** (foundations): CS + CA in parallel. These set the frame everything else is evaluated against.
- **Wave 2** (coverage): DC + CC in parallel. Informed by Wave 1 findings.
- **Wave 3** (forward-looking): EV alone. Informed by Waves 1–2.

Each wave: run agents → synthesize findings under their bucket heading → land obvious fixes inline → escalate judgment calls → proceed.

### Working assumptions (user-confirmed 2026-04-18)

- **Persona**: data engineer / analyst with SQL fluency pairing with Claude Code or Cursor. Not a beginner; not a non-technical stakeholder.
- **Backwards compat is not sacred** — no external users yet. Drop/rename commands freely.
- **Expanded eval is design-now, run-later** — spec the harness + task list this round; running it is follow-up.

### Resume point

Wave 1 landed 2026-04-18. CS and CA findings below. Wave 2 (DC + CC) blocked on user triage of the judgment calls flagged under each finding's **Verdict** line.

### Cold-start simulation findings (CS.x)

Agent was given skill files + README + AGENTS.md and four tasks against `data/test.duckdb`. Each finding below was spot-verified after the agent returned.

#### CS.1 — `qdo context` crashes on date/datetime columns — **BLOCKER**

- **Where:** `src/querido/core/context.py` (already in Deferred / future phases as "Bug: `qdo context` on date/datetime columns")
- **Repro:** `uv run qdo -f json context -c data/test.duckdb -t customers` → `TypeError: 'datetime.date' object is not subscriptable` surfaced as `UNKNOWN_ERROR` in the envelope
- **Why it matters:** `context` is the documented "start here" in SKILL.md. On any real DB with a date column (which is most of them), the first command in the recommended workflow crashes. This makes qdo feel broken on contact.
- **Verdict:** **Fix inline before Wave 2.** This is the single highest-leverage issue Wave 1 found — every other onboarding polish is downstream of "does the first command work." Not a judgment call.

#### CS.2 — Fixture mismatch: docs use `orders`, fixture has `customers/products/datatypes` — **BLOCKER**

- **Where:** `SKILL.md:105,108,145,292-297` and `AGENTS.md:193-256,269-303,361-364` all reference `-t orders` in examples; `data/test.duckdb` (generated by `scripts/init_test_data.py`) has only `customers, datatypes, products`
- **Why it matters:** Any new user following *any* example in SKILL.md or AGENTS.md hits "Table 'orders' not found" immediately. The docs promise one shape; the fixture delivers another.
- **Verdict:** **Judgment call.** Two options:
  - **(A) Add `orders` + `order_items` to the fixture** — matches doc examples, gives a richer test DB for tutorials, requires updating `init_test_data.py`.
  - **(B) Rewrite every skill/AGENTS example to use `customers` or `products`** — smaller diff but loses the narrative of "orders" (which is the canonical "transactions with status enum + dates" example).
  - I recommend **(A)** — the examples are carefully crafted and the fixture should serve them. Asking for your call.

#### CS.3 — `metadata show -f json` bypasses the envelope — **CONSISTENCY GAP**

- **Where:** `src/querido/cli/metadata.py` — `metadata show` emits a flat `{table, connection, row_count, table_description, columns, …}` dict; every other command emits `{command, data, next_steps, meta}`
- **Repro:** `uv run qdo -f json metadata show -c data/test.duckdb -t customers` (after `metadata init`)
- **Why it matters:** Agents parsing `-f json` output have learned the envelope shape from every other command; `metadata show` silently breaks the contract. R.2 closed the envelope gaps for 5 commands; `metadata show` was explicitly noted as still-bypassing.
- **Verdict:** **Fix inline before Wave 2.** Wire through `emit_envelope()` with a `for_metadata_show` rule. Small change, completes R.2's intent.

#### CS.4 — Agent claim withdrawn (profile --quick column names)

- Sim reported `profile --quick -f json` had null column names. Verification (`uv run qdo -f json profile -c data/test.duckdb -t customers --quick`) shows column names are present as `column_name`. Agent misread — probably confused `columns[].column_name` with a field called `name`. **Not a real finding.** Kept here so it's not re-discovered later.

#### CS.5 — Connection-to-metadata-dirname mapping is non-obvious — **POLISH**

- **Where:** `SKILL.md:26`, `AGENTS.md:296` say metadata lives at `.qdo/metadata/<connection>/` but when `--connection` is a file path, the dir becomes the file *stem* (`data/test.duckdb` → `.qdo/metadata/test/`). Not documented anywhere.
- **Why it matters:** An agent that wrote metadata via `-c data/test.duckdb` will, on a later command, look under `.qdo/metadata/data_test_duckdb/` or similar and miss it. Silent confusion.
- **Verdict:** **Doc fix** — add a sentence to SKILL.md and AGENTS.md explaining the mapping. **Land inline.** A product fix (normalize to a deterministic sanitized path) is a larger design call — defer.

#### CS.6/CS.9 — `values` isn't in SKILL.md's "Quick exploration workflow" — **DISCOVERABILITY**

- **Where:** `SKILL.md` Quick exploration section stops at `catalog → context → profile → inspect`; `values` appears at line 72 in a later section ("Enumerate distinct values in a column") but not in the main workflow example.
- **Why it matters:** Task 3 ("enumerate status distinct values") is the canonical use case. The natural traversal from SKILL.md's main flow doesn't surface `values`. Agents end up writing a custom `qdo query --sql "select distinct status, count(*) from …"` instead of using the built-in that also writes metadata.
- **Verdict:** **Land inline** — add `qdo values -C <col>` into SKILL.md's quick workflow as the "enumerate enum values" step.

#### CS.7 — `joins` isn't in SKILL.md's "Quick exploration workflow" — **DISCOVERABILITY**

- **Where:** Same as CS.6; `joins` is in AGENTS.md step 10 but not in SKILL.md's main flow
- **Why it matters:** Task 2 ("find likely join keys") has a bespoke command that isn't reached by skill-file traversal
- **Verdict:** **Land inline** — promote `qdo joins` into the SKILL.md quick workflow alongside `inspect` / `context`.

#### CS.8 — Metadata YAML stores raw `connection:` value, not a portable alias — **PORTABILITY**

- **Where:** `AGENTS.md:296` promises "files live at `.qdo/metadata/<connection>/`" but the YAML's own `connection:` field stores whatever string was passed to `-c` — which may be an absolute path
- **Why it matters:** A bundle exported from machine A with `connection: /Users/alice/data.duckdb` imports onto machine B where that path is invalid. Bundles should be connection-agnostic (which is the R.3.1 design goal) but the raw path leaks into metadata.
- **Verdict:** **Judgment call.** Options: (1) strip to the file stem; (2) normalize to a canonical name at write time; (3) leave as-is and document that bundles strip `connection` on export. Probably (3) — the bundle path already handles the portability story, and the local YAML can keep a human-useful reminder of where the data is. Asking for your call.

#### CS.10 — `quality` vs `profile` roles are not clearly differentiated — **POLISH**

- **Where:** SKILL.md and AGENTS.md list both in the workflow but don't say when each earns its keep
- **Why it matters:** Minor. Agents may run both redundantly or skip one unnecessarily. `quality` fills a real niche (null-rate thresholds, enum violations via stored `valid_values`, status elevation) that `profile` doesn't.
- **Verdict:** **Land inline** — add a one-line "when to reach for each" in SKILL.md next to the workflow.

### Command-surface audit findings (CA.x)

Agent produced a scorecard over all 33 top-level commands + 11 nested subcommands (44 total endpoints). All commands have `@friendly_errors` (R.11) and SQL injection surfaces go through `validate_table_name` / `validate_column_name` / `validate_object_name` (R.24). Global `-f`/`-c`/`--show-sql`/`--debug` are correctly distributed. Test coverage is good.

The interesting findings — judgment calls in bold:

#### CA.1 — `qdo sql` and `qdo snowflake` group parents don't surface `-c` — **DX FRICTION**

- **Where:** `uv run qdo sql --help` / `uv run qdo snowflake --help` — no `--connection` on the parent
- **Why it matters:** Every leaf (`sql select`, `sql insert`, `snowflake semantic`, `snowflake lineage`, …) takes `-c`. Having to specify it per-leaf is fine but an agent reading the group help gets no hint that `-c` is needed. Other groups (`bundle`, `workflow`, `config`, `metadata`, `session`) don't take `-c` at the group either, so this is consistent — just terse.
- **Verdict:** **Not a fix.** Typer's group model doesn't naturally forward `-c` to every leaf. Could add it in the group's help epilog ("Every subcommand takes `-c` — see leaf help"). **Judgment call** whether worth the doc update. I lean *no* (low signal, easy to discover once a leaf is run).

#### CA.2 — `assert`-as-group misread — finding withdrawn

- Audit agent flagged `assert` as a "misleading group." Verified: `uv run qdo assert --help` shows `Usage: qdo assert [OPTIONS] COMMAND [ARGS]...` but this is Typer's boilerplate header for ALL commands, not a signal of grouping. `assert` is a leaf with 11 real options. **Not a real finding.**

#### CA.3 — 5 commands invisible to SKILL.md / skills docs — **DISCOVERABILITY**

High-value commands that aren't mentioned in `integrations/skills/SKILL.md` or the agent tutorial narration:
- **`assert`** — CI-friendly value assertion; agents should know about this for validation workflows
- **`diff`** — schema comparison; the only command specifically for "what changed"
- **`explain`** — query-plan introspection; common SQL skill
- **`snowflake semantic`** — Cortex Analyst YAML generator; high-value Snowflake-only feature
- **`snowflake lineage`** — upstream/downstream trace; high-value Snowflake-only feature

Niche commands whose invisibility is probably fine: `view-def`, `completion` (shell-utility), `tutorial` (invoked manually).

- **Verdict:** **Land inline** — add an "Advanced / specialized" short section to SKILL.md listing these five with one-line descriptors. Not every command needs to be in the main workflow, but agents should be able to discover them from skill-file context alone. This is a 20-line addition.

#### CA.4 — `-f json` support missing on `diff` and `joins` — **CONSISTENCY**

- **Where:** `diff` and `joins` emit rich-only output; no structured envelope for agents
- **Why it matters:** Both are "agents want structured output" commands. Diff results are table lists; joins are candidate-key lists — both naturally tabular.
- **Verdict:** **Land inline** as two small wires through `emit_envelope()` — same pattern as R.2. Good test: add them to `_ENVELOPE_CASES` in `tests/test_next_steps.py`.

#### CA.5 — No command merges recommended — **CONFIRMED GOOD**

- `quality` + `profile --classify`, `values` + `dist` (categorical), `inspect` + `catalog --pattern` — each pair has distinct user flows. Keep as-is.

#### CA.10 — Bundled workflows don't reference `assert` / `explain` — **EXAMPLE GAP**

- **Where:** 6 bundled workflows under `src/querido/core/workflow/examples/` use profile/quality/context/dist/values/diff/template/query/pivot. None use `assert` or `explain`.
- **Why it matters:** `assert` is exactly what you want at the end of a workflow (validate invariants before publishing). `explain` can guide which columns to profile first on a wide table.
- **Verdict:** **Judgment call.** Option: add one small example workflow that ends in `assert` (e.g., `migration-safety.yaml` — compare row counts, assert `abs(diff) < threshold`). Asking whether to schedule.

### Judgment calls Wave 1 surfaced (need your ruling)

1. **CS.2** — Fixture direction: (A) add `orders` table, (B) rewrite examples. Recommending (A).
2. **CS.8** — Metadata `connection:` field portability: (1) strip, (2) normalize, (3) leave + bundle strips on export. Recommending (3).
3. **CA.10** — Add an `assert`-terminated bundled workflow? (Small, worthwhile.)

### Wave 1 cleanups to land inline (no approval needed)

- **CS.1** — Fix `qdo context` datetime.date crash (blocker; tracked in deferred section; promoting to now)
- **CS.3** — Wire `metadata show` through `emit_envelope()` with a `for_metadata_show` rule
- **CS.5** — Document connection-to-dirname mapping in SKILL.md + AGENTS.md
- **CS.6/CS.7** — Add `values` + `joins` to SKILL.md quick workflow
- **CS.10** — Add `quality` vs `profile` one-liner to SKILL.md
- **CA.3** — Add "Advanced / specialized" section to SKILL.md covering `assert`, `diff`, `explain`, `snowflake semantic`, `snowflake lineage`
- **CA.4** — Wire `diff` and `joins` through `emit_envelope()`; extend `_ENVELOPE_CASES`

After these land, Wave 2 (docs & tutorial consistency + code consistency sweep) runs.

### Docs & tutorial consistency findings (DC.x)

Agent walked README, AGENTS.md, SKILL.md, WORKFLOW_AUTHORING/EXAMPLES, `integrations/continue/qdo.md`, `docs/cli-reference.md`, and both tutorial runners. Verified claims against the actual CLI.

#### DC.1 — `docs/cli-reference.md` references removed `qdo serve` and `[web]` extra — **STALE** — **landed inline**

- **Where:** `docs/cli-reference.md:17` (`'querido[web]'`), `:106` (`qdo serve -c CONN` row), `:242-243` (example). R.13 (2026-04-17) removed the entire `qdo serve` command; the doc wasn't regenerated.
- **Fix landed:** stripped all three references; replaced the example with `qdo report table` (the intended replacement per Phase 2.2).

#### DC.2 — `integrations/continue/qdo.md` workflow block drifted from SKILL.md — **STALE** — **landed inline**

- **Where:** `integrations/continue/qdo.md:43-86` (old quick-workflow) vs. `SKILL.md:43-85` (authoritative). Missing `joins` step, duplicate step-8 numbering (two different commands both labeled `# 8`), old `values` framing without `--write-metadata`, no `profile vs quality` note.
- **Fix landed:** synced the workflow block to match SKILL.md verbatim (including steps 2 (joins) and 8 (`values --write-metadata`), renumbered through step 12, and copied the `profile vs quality` + `values --write-metadata` explanatory paragraphs).

#### DC.3 — "six bundled examples" prose was stale — **STALE** — **landed inline**

- **Where:** `integrations/continue/qdo.md:318` (old) — hardcoded "six bundled examples" after Call-3 added `migration-safety.yaml` (bringing the count to seven).
- **Fix landed:** replaced the literal count with `(qdo workflow list shows the current set)`. Avoids future drift — the count is now discoverable rather than hardcoded.

#### DC.4 — continue/qdo.md metadata-location docs lacked the path-vs-name nuance — **LANDED INLINE**

- **Where:** `integrations/continue/qdo.md:284` — said "files go to `.qdo/metadata/<connection>/<table>.yaml`" without explaining the connection-dir derivation (named → name, file → stem).
- **Fix landed:** copied the full explanation from SKILL.md, plus the bundle-portability note from CS.8.

#### DC.5 — SKILL.md never mentioned `qdo tutorial` — **LANDED INLINE**

- **Where:** `integrations/skills/SKILL.md` had zero mentions of the tutorial before this sweep. README + AGENTS surface it prominently, but SKILL.md (the Claude Code embedded rule) skipped it. New users reading SKILL.md alone couldn't discover the 15-lesson hands-on onboarding.
- **Fix landed:** added a "First time?" sub-block to "Quick Setup" pointing at `qdo tutorial explore` and `qdo tutorial agent` with one-liners on what each covers.

#### DC overall impression

Doc surface is **mostly coherent but had one broken cycle** — `integrations/continue/qdo.md` was a stale copy-paste derivative of SKILL.md, and `docs/cli-reference.md` was a hand-written file that wasn't touched when `qdo serve` was removed. Both are now fixed.

**Source-of-truth verdict:** SKILL.md is the authoritative agent-facing doc; AGENTS.md is complementary (output shapes, error codes); README.md is human-first; `continue/qdo.md` is a derivative (now synced); `docs/cli-reference.md` is a human-readable reference that must be hand-updated on each CLI surface change. No changes to that policy — just keep it honest.

### Code consistency findings (CC.x)

Agent read ~10 representative modules: `cli/_pipeline.py`, `cli/_errors.py`, `cli/workflow.py`, `core/profile.py`, `core/quality.py`, `core/workflow/runner.py`, `connectors/factory.py`, `connectors/snowflake.py`, `connectors/base.py`, `output/envelope.py`, `core/metadata.py`. Ran `grep` for `TODO|FIXME|XXX|HACK` — **zero hits**, code is clean of debt markers.

#### CC.1 — Bare `except Exception` in background work paths — **PARTIAL FROM R.22**

- **Where:** `cli/_pipeline.py:121,128` (cache warm), `core/context.py:302,312` (metadata load), `connectors/factory.py:37` (parquet register), `cli/config.py:237` (connection test). All intentional fallbacks; some already had rationale comments from R.22, others didn't.
- **Why it matters:** The pattern is correct (best-effort degradation with logged debug info) but future maintainers should know *why* the bare catch is safe rather than treating it as a bug to narrow.
- **Verdict:** **Partial-fix landed inline.** Added a doc block to `_maybe_warm_cache` explaining the daemon-thread design + cache-close invariant (CC.3 concern folded in). Remaining sites already have R.22 rationale comments; CC.8 improves `core/context.py`'s docstring.

#### CC.2 — `dispatch_output` uses `**kwargs: Any` — **TYPE-CHECK HOLE** — **JUDGMENT CALL**

- **Where:** `cli/_pipeline.py:200-248` — `dispatch_output(command_name, /, *args: Any, **kwargs: Any)` deliberately erases the per-command shape. Commands cast the result to `Any` at the call site.
- **Why it matters:** Runtime `KeyError` would catch a missing registry mapping, but a typo in a kwarg name for a specific command isn't caught statically. R.25-style `TypedDict` payloads or `@overload` declarations would tighten this.
- **Verdict:** **Judgment call.** The current pattern is safe in practice (integration tests exercise every command), and retrofitting overloads would be ~30 lines of protocol per command. I'd **defer** until we see an actual bug. Asking for your call.

#### CC.3 — Cache-warm daemon thread had no documented shutdown semantics — **LANDED INLINE**

- **Where:** `cli/_pipeline.py:126-127` spawns a daemon thread without documenting what happens at exit.
- **Fix landed:** added docstring block to `_maybe_warm_cache` explaining the daemon-only strategy, the `finally: cache.close()` invariant, and the `atexit` upgrade path for if the cache ever becomes persistent state.

#### CC.4 — `core/quality.py` metadata merge is silent — **REAL, SMALL**

- **Where:** `core/quality.py:83` calls `load_column_metadata(connection, table)` without a try/except. That function itself degrades silently via `show_metadata` → `_read_yaml` (which catches `(OSError, yaml.YAMLError)` per R.22). No wrapping needed at the call site.
- **Verdict:** **No fix needed** — the degradation path is already wrapped at the right layer (R.22). Agent misread the lack of try/except at the call site. **Finding withdrawn.**

#### CC.5 — Scan-command return types are plain `dict[str, Any]` — **LEVERAGE** — **JUDGMENT CALL**

- **Where:** `core/profile.py`, `core/quality.py`, `core/context.py`, `core/values.py` all return plain `dict`. Downstream callers (`cli/*.py`, tests, `core/next_steps.py`'s `for_*` rules) rely on specific keys by string lookup.
- **Why it matters:** An unannounced key rename in `profile.py` would break callers silently. A `TypedDict` per result (`ProfileResult`, `QualityResult`, `ContextResult`, `ValuesResult`) would make the contract enforceable at type-check time and document the shape in one place.
- **Verdict:** **Judgment call — high leverage.** This is a 4–6 TypedDicts, ~50 lines each once you count the optional-field markup. It enables static detection of shape drift and gives IDE autocompletion on scan results. Recommending we do it as a small post-Sharpening phase. Asking for your call.

#### CC.6 — Envelope emit error-escalation is implicit — **PARTIAL RISK**

- **Where:** All envelope-emitting commands go through `output/envelope.py:emit_envelope()`, which does the TOON-then-YAML fallback (per R.4). The non-envelope `render_agent()` path in `cli/_errors.py` is used only for structured errors and carries flat payloads that don't need fallback. Every leaf command is decorated with `@friendly_errors` (R.11).
- **Verdict:** **Already guarded.** The "TOON fallback" is inside `emit_envelope`, not per-caller, so every envelope emission gets it. Agent's concern was valid pre-R.4, not now. **Finding withdrawn** except for one follow-up: add a contract test that asserts every envelope-emitting command can survive a TOON-incompatible shape by falling back to YAML. Small, non-blocking.

#### CC.7 — Agent claim withdrawn (query.py module-level `import sys`)

- Agent claimed `cli/query.py` had a module-level `import sys` violating the "pay for what you use" principle. Verification (`head -10 src/querido/cli/query.py`): only `typer` and `friendly_errors` are imported at module level. `sys` is imported lazily inside the function. **Not a real finding.**

#### CC.8 — `core/context.py` docstring didn't document the metadata best-effort semantics — **LANDED INLINE**

- **Where:** `core/context.py:23-43` docstring promised "stored metadata is loaded from disk concurrently" but didn't warn that unreadable YAML or permission errors silently degrade to `metadata=None`.
- **Fix landed:** extended the docstring with a "Stored metadata is read best-effort…" paragraph so callers know to tolerate its absence.

#### CC.9 — `quality.py` has hand-escaped SQL with inline literals — **JUDGMENT CALL**

- **Where:** `core/quality.py:287-292` builds the stored-`valid_values` enum-violation probe via f-string with hand-escaped identifiers and literal values. `validate_column_name` runs first so the identifier is safe; literals are hand-escaped via `_sql_literal`.
- **Why it matters:** The code today is safe. But there's no compile-time check that a future query won't bypass the escaping step. A `SafeSQL` wrapper or strict preference for parameterized literals would remove the manual burden.
- **Verdict:** **Judgment call — probably overkill now.** Current surface is small enough that code review catches it. Revisit if the f-string SQL pattern spreads to more modules. **Defer** unless you want to make it a Phase.

#### CC.10 — Workflow runner stderr truncation isn't surfaced in the envelope — **SMALL PROTOCOL GAP**

- **Where:** `cli/workflow.py` — the `_STDERR_TAIL_BYTES = 4096` cap (per R.7) strips to the last 4KB of stderr but doesn't stamp a `stderr_truncated: true` flag on the error envelope. An agent reading an envelope whose `stderr` field is exactly 4096 bytes doesn't know whether it's a precise value or a truncation.
- **Verdict:** **Small protocol change — inline.** Add a `stderr_truncated: bool` field to the workflow-step-failed envelope + one test assertion in `tests/test_workflow_runner.py`. Schedule.

#### CC.11 — Cache-key convention wasn't linked from ARCHITECTURE.md — **LANDED INLINE**

- **Where:** R.26 added per-connector class docstrings describing the `_columns_cache` key convention. ARCHITECTURE.md §5 (Identifier Case Normalization) didn't link to them, so a future contributor could write a connector that gets the cache wrong without ever reading the docstrings.
- **Fix landed:** extended ARCHITECTURE.md §5 with a paragraph summarizing the conventions and making it a rule for future connectors.

#### CC.12 — No `TODO` / `FIXME` / `XXX` / `HACK` tags — **GOOD**

- Grep clean. Treat this as an invariant going forward.

#### CC overall impression

**Code is sharp overall.** The R-series cleanup is holding up — lazy imports follow the "pay for what you use" principle everywhere that matters, error hierarchy is typed and used, resource lifecycles are managed via context managers, security-sensitive paths (SQL interpolation) all route through validators.

**Three systemic opportunities worth scheduling:**

1. **TypedDict for scan results (CC.5)** — highest leverage. Documents the contract and catches shape drift statically.
2. **Envelope contract test for TOON fallback (CC.6 follow-up)** — small, ensures the fallback is exercised on every envelope shape.
3. **`stderr_truncated` flag (CC.10)** — protocol polish for the workflow step-failure envelope.

**No security smells.** All subprocess calls use argv (no `shell=True`), all SQL interpolation is validator-gated, YAML loading is `safe_load`, secrets aren't logged.

### Judgment calls Wave 2 surfaced (need your ruling)

1. **CC.2** — Tighten `dispatch_output` types with `@overload`/`Protocol`? Defer recommended — no evidence of current bugs.
2. **CC.5** — Add `ProfileResult` / `QualityResult` / `ContextResult` / `ValuesResult` TypedDicts? Recommending we schedule as a small post-Sharpening phase.
3. **CC.6** — Add a "TOON fallback survives any envelope shape" contract test? Small, recommending we do it.
4. **CC.9** — Introduce a `SafeSQL` wrapper for hand-escaped SQL paths? Defer recommended.
5. **CC.10** — Add `stderr_truncated: bool` to the workflow-step-failure envelope? Recommending we do it.

### Wave 2 cleanups landed inline (no approval needed)

- **DC.1** — Stripped `qdo serve` / `[web]` references from `docs/cli-reference.md`
- **DC.2** — Synced `integrations/continue/qdo.md` workflow block to SKILL.md
- **DC.3** — Replaced "six bundled examples" with a discovery reference
- **DC.4** — Added metadata-dir nuance + bundle-portability note to continue/qdo.md
- **DC.5** — Added `qdo tutorial` mention to SKILL.md "Quick Setup"
- **CC.3** — Documented cache-warm daemon-thread semantics in `_maybe_warm_cache`
- **CC.8** — Extended `core/context.py` docstring with metadata best-effort warning
- **CC.11** — Linked cache-key conventions from ARCHITECTURE.md §5

### Resume point

Wave 2 findings + cleanups landed 2026-04-18. Judgment calls resolved:

- **CC.2 — deferred** (no action; current `dispatch_output` typing hasn't produced bugs)
- **CC.5 — scheduled as a post-Sharpening phase** (see "Scan-result TypedDicts" below)
- **CC.6 — landed inline** (new `test_envelope_agent_format_either_toon_or_yaml_fallback` parametrized over 15 commands + `test_envelope_agent_format_yaml_fallback_for_non_tabular_shape` unit)
- **CC.9 — deferred** (f-string SQL surface is small enough today; revisit if pattern spreads)
- **CC.10 — landed inline** (`stderr_truncated: true` added to workflow step-failure envelope, absent when stderr fits; two new tests in `tests/test_workflow_runner.py`)

Wave 3 (eval-design proposal) is next.

### Scheduled follow-up: Scan-result TypedDicts (from CC.5)

Add one TypedDict per scan result so the shape contract is enforced at type-check time rather than discovered through tests or runtime `KeyError`.

- [ ] `ProfileResult` in `core/profile.py`
- [ ] `QualityResult` in `core/quality.py`
- [ ] `ContextResult` in `core/context.py`
- [ ] `ValuesResult` in `core/values.py`
- [ ] Optionally: `ColumnEntry` TypedDict shared by profile / quality / context (the per-column payload they all emit)
- [ ] Update `core/next_steps.py` `for_*` rule signatures to consume the narrower type
- [ ] Update tests to use `.get()` with `TypedDict.get(...)` semantics where applicable

Schedule after Wave 3. Not blocking anything; high leverage when it lands (blocks a class of silent-key-rename bugs).

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
