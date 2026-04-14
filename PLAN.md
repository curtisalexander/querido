# Plan

Working todo list for making querido the agent-first data exploration CLI. Items are ordered by dependency; complete a phase before starting the next unless noted.

> **PLAN.md vs IDEAS.md.** This file is the committed, actionable todo list — items here have been scoped, sequenced, and are ready to work on. [IDEAS.md](IDEAS.md) is the speculative archive: research notes, competitive analysis, and features we haven't committed to yet. Promote ideas from IDEAS.md into PLAN.md when we decide to build them; don't duplicate between the two.

Each item: **what**, **why it matters**, **acceptance criteria**, **effort estimate**.

---

## Phase 1 — Agent-first foundations (~1 week)

The four items that together create the "tool gets better the more it's used" compounding loop. Do these first; everything else depends on them.

### 1.1 — `next_steps` field in every JSON output

- [ ] Add a `next_steps: [{cmd, why}]` field to the JSON output of every scanning command (`catalog`, `context`, `inspect`, `preview`, `profile`, `dist`, `values`, `quality`, `diff`, `joins`, `query`)
- [ ] Add `try_next: [{cmd, why}]` to structured error objects
- [ ] Rules are deterministic (no LLM), based on output shape: row counts, null rates, distinct counts, metadata presence

**Why:** every command becomes a node in a traversable graph. Biggest single UX lever for agent workflows.

**Acceptance:** running any listed command with `-f json` returns a non-empty `next_steps` array whose entries are valid qdo invocations. Unit tests cover the rule for each command.

**Effort:** 2–3 days.

### 1.2 — Session MVP

- [ ] `QDO_SESSION=<name>` env var — when set, every command appends a JSONL record to `.qdo/sessions/<name>/steps.jsonl` with: timestamp, cmd, args, duration, exit_code, row_count, stdout_path
- [ ] Each step's full stdout saved to `.qdo/sessions/<name>/step_<n>/stdout`
- [ ] `qdo session start <name>` / `qdo session list` / `qdo session show <name>`
- [ ] No daemon, no DB, no server. Append-only files

**Why:** substrate for reports, bundles, workflow authoring, audit trail, and the `--from` patterns later. Collapses the separate audit-log and sql-history ideas into one feature.

**Acceptance:** running 5 commands under `QDO_SESSION=test` produces 5 JSONL rows and 5 stdout files; `qdo session show test` prints a readable summary.

**Effort:** 1 day.

### 1.3 — `--write-metadata` on scanning commands

- [ ] Add `--write-metadata` flag to `profile`, `values`, `quality`
- [ ] Flag writes computed stats to the table's metadata YAML with provenance fields per value: `source: profile|values|quality|human`, `confidence: 0.0–1.0`, `written_at: <session_id|timestamp>`, `author: $QDO_AUTHOR|git user`
- [ ] Deterministic auto-fill rules: low-cardinality (<20) string → candidate `valid_values` (0.8); null_rate >95% → `likely_sparse: true`; column name matches `*_at/*_date` + timestamp type → `temporal: true`
- [ ] Never overwrite a field with `confidence: 1.0` (human-authored) without `--force`

**Why:** turns metadata into a byproduct of normal exploration. Starts the compounding loop.

**Acceptance:** `qdo profile -t orders --write-metadata` updates `.qdo/metadata/<conn>/orders.yaml` with provenance-tagged entries; re-running doesn't duplicate; `--force` is required to overwrite human fields.

**Effort:** 2–3 days.

### 1.4 — Metadata scoring and suggestions

- [ ] `qdo metadata score -c <conn>` — per-table completeness score (% of columns with description, % with valid_values where cardinality is low, freshness of profile stats)
- [ ] `qdo metadata suggest -c <conn> -t <table>` — proposes additions as a diff from recent profile/values/quality runs; `--apply` writes them
- [ ] Output includes a pointer in `next_steps` from commands that scan tables with low scores

**Why:** gives agents a measurable target and a non-preachy nudge toward improving metadata.

**Acceptance:** `qdo metadata score` produces a ranked report; `suggest --apply` writes provenance-tagged fields identical in shape to Phase 1.3's output.

**Effort:** 1 day.

---

## Phase 2 — Agent output + first shareable artifact (~1 week)

### 2.1 — `-f agent` output format

- [ ] New `AgentFormatter` alongside JSON/rich/csv formatters
- [ ] Tabular results → TOON (row-oriented, explicit row count, column header once)
- [ ] Nested results (`context`, `metadata show`) → YAML
- [ ] Scalar results → single-line `key=value key=value`
- [ ] Errors → single-line `ERR CODE key=value message="..."`
- [ ] `QDO_FORMAT=agent` environment variable sets default

**Why:** TOON wins ~40% tokens on tabular data with equal-or-better accuracy; YAML wins on nested. Matching format to shape is the actual accuracy driver.

**Acceptance:** benchmark 5 representative commands with tiktoken; `-f agent` is ≥40% fewer tokens than `-f json` on tabular outputs. All outputs round-trip through a documented parser.

**Effort:** 2–3 days.

### 2.2 — `qdo report table` HTML

- [ ] `qdo report table -c <conn> -t <table> -o <file.html>` — single self-contained HTML file
- [ ] Inline CSS, inline SVG, no CDN, no JS required
- [ ] Content: header (name, conn, row count, generated_at), metadata summary, schema table, quality callouts, related tables from `joins`, collapsed "Generated with qdo" footer with the exact command that produced it
- [ ] Dark mode via `prefers-color-scheme`; print-friendly CSS

**Why:** gives users a polished artifact to hand to a PM or exec without asking them to install qdo. Strictly better than `serve` for the "share with a non-user" use case.

**Acceptance:** running the command produces a single HTML file that renders correctly offline in a fresh browser profile. Snapshot test on fixture DB.

**Effort:** 2–3 days.

---

## Phase 3 — Team sharing (~1 week)

### 3.1 — Knowledge bundle export/import MVP

- [ ] `.qdobundle` format: directory or zip containing `manifest.yaml`, `metadata/*.yaml`, optionally `column-sets/*.yaml`
- [ ] `qdo bundle export -c <conn> -t <tables> -o <file>` — package metadata with `schema_fingerprint` per table (hash of columns+types)
- [ ] `qdo bundle import <file> --into <conn>` — preview diff by default, `--apply` writes; `--strategy keep-higher-confidence|theirs|mine|ask`
- [ ] `qdo bundle diff a.qdobundle b.qdobundle`
- [ ] `qdo bundle inspect <file>` — summary
- [ ] `--redact` drops fields from PII-flagged columns

**Why:** unlocks team-level compounding. One person's investigation makes the next person's agent smarter.

**Acceptance:** export from conn A, import into conn B with a different table name mapping, verify metadata appears on the matching table by schema fingerprint. Merge strategies behave per spec.

**Effort:** 3–4 days.

---

## Phase 4 — Workflows as extensibility (~2 weeks)

The biggest feature in the plan and the most prone to scope creep. Do Phase 1–3 first so the spec has real use cases to validate against.

### 4.1 — Workflow spec (JSON Schema)

- [ ] Draft spec for YAML workflow files: `name`, `description`, `version`, `inputs` (typed), `steps` (with `run`, `capture`, `when`, conditional), `outputs`
- [ ] `qdo workflow spec -f json` emits the JSON Schema
- [ ] `qdo workflow spec --examples` emits bundled example workflows
- [ ] Declarative only — no embedded code, no shell escape

**Acceptance:** spec is complete enough to express all conversions in Phase 5. Draft is reviewed before runner implementation begins.

**Effort:** 2 days for draft; revise as Phase 5 reveals gaps.

### 4.2 — Workflow runner and introspection

- [ ] `qdo workflow run <name> [inputs...]` — execute, capture outputs, bind `${captures}`
- [ ] `qdo workflow lint <file>` — structured errors with `{code, message, fix}` per issue
- [ ] `qdo workflow list` — bundled + user + project workflows
- [ ] `qdo workflow show <name>` — print the YAML
- [ ] Every run auto-creates a session (auto-created if none)
- [ ] Search paths: `./.qdo/workflows/` → `$XDG_CONFIG_HOME/qdo/workflows/` → bundled

**Acceptance:** `workflow run` executes a non-trivial example end-to-end; `lint` catches malformed YAML, unknown captures, and unsafe steps.

**Effort:** 3–4 days.

### 4.3 — `qdo workflow from-session`

- [ ] Generate a draft workflow YAML from the last N steps of a session, parameterizing obvious inputs (connection, table)
- [ ] Output passes `lint` on happy paths

**Why:** this is the agent-authoring bootstrap. Agents edit a draft instead of authoring from cold.

**Acceptance:** run a 5-step investigation, call `from-session`, resulting YAML lints clean and runs against the fixture DB.

**Effort:** 2 days.

### 4.4 — CLI sugar shim

- [ ] Typer dispatcher: if no Python handler is registered for `<cmd>`, fall back to `qdo workflow run <cmd>`
- [ ] `qdo <any-workflow-name> [args]` works identically to `qdo workflow run <any-workflow-name> [args]`
- [ ] `qdo --help` surfaces workflows alongside primitives

**Why:** enables Phase 5 conversions without removing user-visible commands.

**Acceptance:** bundled workflows are invokable as `qdo <name>` and as `qdo workflow run <name>` with identical behavior.

**Effort:** 1 day.

### 4.5 — Agent-authoring documentation

- [ ] `integrations/skills/WORKFLOW_AUTHORING.md` (new) — spec reference, worked examples, common patterns, anti-patterns, lint-error catalog
- [ ] `integrations/skills/SKILL.md` — add "Writing workflows" section linking to the above
- [ ] `integrations/continue/qdo.md` — mirror the additions for Continue
- [ ] `integrations/playbooks/agent-recipes.md` (new) — include "recipe: author a workflow from a recent investigation"
- [ ] `AGENTS.md` at repo root — document the agent-authoring loop, point at `WORKFLOW_AUTHORING.md`
- [ ] Bundled workflows get inline `# why:` comments aimed at agents

**Why:** without these, agents produce plausible-looking YAML that doesn't run. This is on the critical path, not after it.

**Acceptance:** see Phase 4.6's self-hosting eval.

**Effort:** 2–3 days, parallel to 4.1–4.4.

### 4.6 — Self-hosting eval (Option 1, `claude -p`)

- [ ] CI script that feeds `WORKFLOW_AUTHORING.md` + `qdo workflow spec -f json` + `qdo workflow spec --examples` + a task prompt to `claude -p --model claude-opus-4-6`
- [ ] Writes result to scratch, runs `qdo workflow lint` + `qdo workflow run` against fixture DB
- [ ] Pass = lint 0 + run 0 + output matches golden file or schema check
- [ ] 3 target tasks the model has not seen
- [ ] Billing note: uses Max subscription via `claude -p`; `unset ANTHROPIC_API_KEY` in CI to avoid silent API billing

**Why:** the only objective signal that our agent docs are sufficient.

**Acceptance:** ≥2 of 3 tasks pass on frontier model; any failure drives a docs revision, not a model change.

**Effort:** 1 day.

---

## Phase 5 — Subcommand conversions to workflows (~1 week)

Use the CLI sugar shim; aliases preserve every current command name. Snapshot-test output shape before/after each conversion.

- [ ] **5.1 Pilot: convert `template`** — end-to-end with snapshot tests. Validates spec + shim + eval path
- [ ] **5.2** Convert `sql scratch`
- [ ] **5.3** Convert `pivot`
- [ ] **5.4** Convert `joins`
- [ ] **5.5** Convert `sql task`, `sql procedure`
- [ ] **5.6** Convert `snowflake semantic`
- [ ] **5.7** Convert `view-def` (if it's a thin SQL-function wrapper)
- [ ] **5.8** Revisit: externalize `profile --classify` rules to a readable YAML (keep the scan primitive)

**Acceptance per conversion:** JSON output byte-identical to pre-conversion version (modulo `generated_at`-style fields). Perf regression ≤50ms on fixture tables.

**Stay as primitives** (do not convert): `catalog`, `inspect`, `preview`, `profile`, `context`, `quality`, `dist`, `values`, `query`, `explain`, `assert`, `export`, `config/cache/metadata *`, `explore`, `snowflake lineage`.

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
- Phase 4.5 (docs) in parallel with 4.1–4.4, not after
- Phase 5 after Phase 4 lands and is internally stable
- Phase 6.1 depends on 4.2 (sessions must exist); 6.2–6.3 independent
