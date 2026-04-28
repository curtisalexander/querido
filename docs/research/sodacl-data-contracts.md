# SodaCL → Soda 4.0 Data Contracts: research notes for qdo

**Date:** 2026-04-28
**Branch:** `claude/research-sodacl-contracts-G3TVD`
**Status:** Reference + mini-plan. Not active work — captured for future consideration.

---

## Why this file exists

Soda Core 4.0 (released 2026-01-28) made a clean break from SodaCL — its
"checks language" of ad-hoc per-table assertions — and replaced it with a
single Data Contract per dataset. Because qdo's metadata YAML is structurally
close to a Soda contract already, the pivot is worth reading carefully: what
changed, what they wrote about *why* it changed, and which pieces qdo can
borrow without breaking its own invariants (no LLM-in-the-loop, files as
primitives, pay-for-what-you-use, etc.).

---

## What Soda 4.0 actually shipped

- **A new top-level concept: the contract.** One YAML per dataset. Pinned to
  a fully-qualified name (`postgres_ds/db/schema/customers`), signed by an
  `owner`, declares column types + per-column checks + dataset-level checks.
- **Breaking change.** `soda-core-{datasource}` package names changed; v3
  pinned to `~=3.5.0`; v3 docs moved to a separate branch. Conversion tool
  shipped to migrate v3 SodaCL checks → v4 contracts. Customer engineers
  outreach for paying customers.
- **First-class typed checks**, not just SQL: `missing`, `invalid` (with
  `invalid_format` regex / `invalid_values`), `duplicate`, `schema` (with
  `allow_extra_columns`, `allow_other_column_order`), `row_count`,
  `group_by`, `reconciliation`, freshness.
- **Variables and plugins.** Contract YAML can reference variables; plugin
  system extends check types.
- **CLI flow:** `soda data-source create → soda data-source test → soda
  contract verify -ds ds.yml -c contract.yml`. Designed for CI/Airflow/
  Dagster/Prefect. Custom keys ignored by the verifier (extensible).
- **Contract Copilot (LLM, paid tier).** Auto-generates a starter contract
  from an existing dataset; plain-English refinement; co-author UI for
  business SMEs alongside engineers writing as code.

### Sample contract (v4)

```yaml
dataset: postgres_ds/db/schema/customers
owner: [email protected]
columns:
  - name: id
    data_type: VARCHAR
    checks:
      - missing:
      - duplicate:
  - name: email
    data_type: VARCHAR
    checks:
      - missing:
      - invalid:
          invalid_format:
            regex: ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$
checks:
  - schema:
      allow_extra_columns: false
      allow_other_column_order: false
  - row_count:
  - reconciliation:
  - group_by:
```

---

## The philosophy (Tom Baeyens, Soda CTO)

Useful turns of phrase to notice — they motivate the shape of the product:

- **"Every dataset that is a handover deserves a contract."** Not every
  table — only the ones that cross a team boundary. This is a sharper rule
  than "document everything."
- **"A data contract is nothing more than an API specification."** Tables-as-
  APIs, producers-as-service-owners, consumers-as-clients. Same rigor as
  microservices.
- **"Move from a reactive approach to a proactive agreement between
  producers and consumers."** Checks are reactive (something broke, write an
  assertion). Contracts are proactive (you publish what you guarantee, then
  enforce it).
- The contract is **the API for data**: producers communicate guarantees;
  consumers can find out what data exists and how to use it without
  re-discovering it.

---

## Side-by-side: Soda 4.0 vs qdo today

| Concept                       | Soda 4.0                                                   | qdo today                                                                                |
|-------------------------------|------------------------------------------------------------|------------------------------------------------------------------------------------------|
| Per-dataset YAML, signed      | `dataset:` + `owner:` + columns                            | `.qdo/metadata/<conn>/<table>.yaml` with `data_owner`                                    |
| Column type + description     | `data_type`, custom fields                                 | `type`, `description`, `pii`                                                              |
| Allowed values                | `invalid: invalid_values: [...]`                           | `valid_values: [...]`                                                                     |
| Null/missing thresholds       | `missing:` (numeric / percent)                             | hard-coded classifier in `quality` (warn > 20 %, fail > 90 %)                            |
| Schema enforcement            | `schema: allow_extra_columns / allow_other_column_order`   | `diff` exists; no metadata-driven enforcement                                             |
| Row-count check               | `row_count:` with thresholds                               | `assert --sql ... --expect 0` (ad-hoc only)                                              |
| Group-by / reconciliation     | first-class checks                                         | `assert` ad-hoc only                                                                      |
| One-command verify            | `soda contract verify`                                     | spread across `quality`, `assert`, `diff`                                                 |
| Starter generation            | Contract Copilot (LLM)                                     | `metadata suggest` (deterministic — by design)                                            |
| Migration / breaking change   | conversion tool + version pin + CE outreach                | not yet exercised                                                                         |
| Producer / consumer split     | engineers as code, SMEs in UI                              | implicit (human + agent)                                                                  |

The structural overlap is striking. qdo's metadata YAML is already ~70 % of
a Soda contract. The gap is mostly framing, plus a few missing dataset-level
check types and a single capstone verify command.

---

## Recommendations (carried forward from the conversation)

### 1. Borrow the framing — keep the substrate
"Contract" carries weight that "metadata" doesn't: agreement, obligation,
handover. qdo's `bundle export` is *literally* a contract handover artifact;
the docs call it a "knowledge bundle." Renaming/reframing in
README.md, DIFFERENTIATION.md, SKILL.md, and the tutorial would tighten
the story for both humans and agents — "contract" implies a verb (verify);
"metadata" only implies a noun (read).

### 2. Adopt the "handover" filter
Soda's smartest non-technical idea: only the datasets that cross team
boundaries deserve a contract. qdo could surface this in `metadata list`
(prompt the user to mark `handover: true` or rank by inferred consumer
count from `joins`/lineage), then prioritise completeness scoring on those
tables. Avoids the metadata-sprawl failure mode.

### 3. Add typed dataset-level checks declaratively
qdo's `assert` is SodaCL — ad-hoc SQL invariants — and stays useful. The
metadata file should additionally be able to **declare** common invariants
without SQL, mirroring Soda's typed checks:

```yaml
table: orders
checks:
  row_count: { min: 1000 }
  schema: { allow_extra_columns: false }
  freshness: { column: order_date, max_age: 1d }
columns:
  - name: status
    valid_values: [pending, shipped, delivered, cancelled]
    null_pct: { max: 1.0 }
```

A new `qdo verify -c mydb -t orders` runs every declared check in one
pass and exits non-zero on failure (CI-friendly). This is the highest-
leverage move: it turns the metadata file from a passive document into an
executable contract — the same direction Soda took, but stays
deterministic and file-local.

### 4. Migration discipline up front
Soda's release demonstrated something qdo will need eventually: a clean
breaking-change playbook (conversion tool + version pin + clearly
separated docs branch). qdo's metadata file should have a
`qdo_metadata_version: 1` field at the top **before** there are users with
stored files in production, so future migrations are mechanical.
The example file at `docs/examples/metadata/test/orders.yaml` doesn't
have one yet.

### 5. Producer / consumer split, in agent terms
Soda's "engineers write contracts as code, SMEs edit in UI" maps to qdo's
dual audience: humans at the keyboard and coding agents writing SQL. Lean
into the split explicitly in SKILL.md:

- **Producer** (the agent or analyst exploring): uses `context`, `values`,
  `metadata suggest` to author / refine.
- **Consumer** (the agent answering a downstream question): reads
  `metadata show` and `context` to know what they can rely on without
  re-investigating.

The consumer's speed-up is the producer's earlier work — that's the
compounding loop, made legible.

### 6. What to *not* copy
DIFFERENTIATION.md already rules these out, and Soda 4.0's choices are
good evidence why qdo should hold the line:

- **Soda Cloud / Agent / hosted UI** — violates "files as primitives." Soda
  is now a platform; that's the trade qdo declined.
- **Contract Copilot's LLM scaffolding** — violates "no LLM-in-the-loop."
  qdo's `metadata suggest` is the deterministic equivalent and stays the
  right call. Story: *"Soda needs an LLM in the box because they generate
  from natural language; qdo doesn't, because the agent already in the loop
  with you does that, and qdo just makes the rules durable."*
- **Plugin marketplace, extensible check engine** — violates the
  surface-area filter.

### 7. Communication patterns worth stealing
- **"X deserves Y" template.** *Every dataset that is a handover deserves
  a contract.* → *Every table you'll come back to deserves a metadata
  file.*
- **Single-line product positioning.** Soda: *Data Contracts engine for
  the modern data stack.* qdo: *Persistent-memory layer for data
  exploration.* Soda's is more verb-y (engine, action). Consider:
  *"qdo accumulates what your team learns about data, so the next
  investigation starts ahead."*
- **Name the failure they save you from.** Soda calls out "scattered
  checks and ad-hoc rules." qdo could name "re-discovering the same
  column twice" or "agents that hallucinate enums."
- **One named workflow, not five commands.** Soda's docs walk users
  through `create → test → verify` as a single arc. qdo has the arc
  (discover → understand → capture → answer → hand off) but five+
  commands; promoting a single `qdo verify` capstone tightens the
  success path.

---

## Mini-plan: how to act on this later

Not active work. Designed so future-me (or an agent) can pick this up
cold and start making progress in small, independently-shippable
slices. Ordered by leverage / cost.

### Phase A — framing only (low risk, no code)
**Goal:** test the "contract" framing on real readers without changing
behaviour.

- [ ] **A1.** Add a paragraph to `DIFFERENTIATION.md` introducing the
  word *contract* alongside *metadata*. Keep "metadata" as the file
  name but explain what role the file plays: "a starter contract — what
  the producer guarantees and the consumer can rely on."
- [ ] **A2.** Add a sentence to README.md "Quick Start" section calling
  the metadata file a "table contract" once, with a link out to the
  DIFFERENTIATION discussion.
- [ ] **A3.** Add to `integrations/skills/SKILL.md`: explicit
  producer / consumer roles, with one example for each.
- [ ] **A4.** Pick a tagline candidate and run it through `eval_skill_files_claude.py`
  to make sure rephrasing doesn't drop the 45/45 score.

**Acceptance:** docs read coherently with the new vocabulary; no code
or test changes; eval still 45/45.

### Phase B — mechanical migration insurance (small code)
**Goal:** make future format changes cheap.

- [ ] **B1.** Add `qdo_metadata_version: 1` to the metadata writer
  (`src/querido/core/metadata_write.py`). All new files include it.
- [ ] **B2.** Loader (`src/querido/core/metadata.py`) reads the field
  and, when absent, treats it as version 1 (no break for existing
  files).
- [ ] **B3.** Update `docs/examples/metadata/test/orders.yaml` to
  include the field.
- [ ] **B4.** Update tests to assert the field is round-tripped.

**Acceptance:** no behaviour change; field present on every newly-
written file; no test regressions.

### Phase C — the verify capstone (the big one)
**Goal:** turn the metadata file into an executable contract.
Deliverable is a single `qdo verify` command that runs every declared
check on the table and exits non-zero on failure.

- [ ] **C1.** Extend the metadata schema with declarative checks:
  - dataset-level: `row_count: { min, max }`, `schema:
    { allow_extra_columns, allow_other_column_order }`,
    `freshness: { column, max_age }`.
  - column-level: `null_pct: { max }`, `unique: true`, optional
    `valid_values` (already supported as a list, just plumb it
    through verify).
- [ ] **C2.** Add `src/querido/core/verify.py` that loads the metadata,
  walks the declared checks, executes each (re-using `quality`,
  `assert_check`, and existing connectors), and emits a structured
  result via the envelope — `{command: "verify", data:
  {checks: [...]}, next_steps, meta}`.
- [ ] **C3.** Add `src/querido/cli/verify.py` exposing
  `qdo verify -c <conn> -t <table>` with `-f json/toon`. Exit code:
  0 on all-pass, 2 on any fail, 1 on infrastructure error.
- [ ] **C4.** Update `tests/test_next_steps.py::_ENVELOPE_CASES` to
  include the new command.
- [ ] **C5.** Add a `qdo verify` lesson to `qdo tutorial agent` and
  the `qdo agent install skill` docs — this is the new capstone of
  the compounding loop.
- [ ] **C6.** Add to README.md "Quick Start" as the canonical CI
  invocation: `qdo verify -c my-db -t orders`.

**Acceptance:** verify runs every declared check in one pass; exits
non-zero on failure; eval still 45/45 (likely 45/45 with one task
shifted from `assert` to `verify`).

### Phase D — the handover filter (small UX, big positioning)
**Goal:** push users toward the high-leverage tables, not all tables.

- [ ] **D1.** Add an optional `handover: true` (and optional
  `consumers: ["team-x", "team-y"]`) field at the top of metadata
  YAML.
- [ ] **D2.** `qdo metadata list` gains a `--handover-only` flag and
  weights completeness scoring toward those tables when rendering the
  default summary.
- [ ] **D3.** Add a one-paragraph section to README ("Which tables
  deserve a metadata file?") quoting Baeyens' rule.

**Acceptance:** flag works; sort order changes; new docs section
reviewed.

### Phase E — typed checks beyond v1 (future, opt-in)
**Goal:** catch up to Soda's `group_by` and `reconciliation` checks
where they're useful for qdo's audience. Defer until verify lands and
real users hit the gap.

- [ ] **E1.** `group_by` check: declared aggregation that must satisfy
  a SQL expression (e.g. `sum(amount) > 0` per region).
- [ ] **E2.** `reconciliation` check: row-by-row comparison vs another
  table or saved query (could reuse `qdo diff`).
- [ ] **E3.** `regex` invalid-format check on string columns (Soda's
  most-asked-for column check).

**Acceptance:** new check types documented + tested; opt-in via
metadata file; no impact on existing files.

---

## Additional suggestions surfaced while writing this up

- **Cheatsheet/poster.** `docs/qdo-cheatsheet.html` already exists.
  When the verify capstone lands, the cheatsheet should grow a
  "writing your first contract" lane that mirrors Soda's
  `create → test → verify` arc.
- **Eval coverage.** Add at least one task to the self-hosting eval
  that exercises `qdo verify` end-to-end. The eval is qdo's
  regression detector for SKILL changes; if framing changes ship
  before eval coverage exists, regressions there will be invisible.
- **Naming the file.** Today the file is `metadata/<table>.yaml`.
  Keep the path — renaming to `contracts/` would be a breaking
  change with no benefit. The framing change is in the docs, not the
  filesystem layout. Reserve a future migration only if real users
  ask.
- **Don't promise a Cortex-style preview for verify.** Soda's
  Contract Copilot crosses a line qdo has chosen not to. If the
  community asks for "auto-write me a verify spec," the answer is
  *use the agent already in your loop with `metadata suggest` +
  hand-edits*, not *we'll add an LLM*.
- **Watch what Soda walks back.** Breaking changes at v4 are real;
  if Soda adds a v3-compat shim or finds the contract surface too
  rigid, that's data qdo should fold into Phase B/C decisions.
- **Cross-link IDEAS.md.** When this work moves from "research" to
  "considered," add a one-line entry pointing here from
  `IDEAS.md` so the trail is discoverable from the canonical
  brainstorm doc.

---

## Sources

- [Introducing Soda 4.0 (announcement)](https://soda.io/blog/introducing-soda-4.0)
- [Soda Core on GitHub — README and v4 positioning](https://github.com/sodadata/soda-core)
- [Soda Releases OSS Data Contract Engine](https://soda.io/blog/soda-releases-oss-data-contract-engine)
- [Contract Language reference (v4)](https://docs.soda.io/soda-v4/reference/contract-language-reference)
- [Soda Core release notes (v4)](https://docs.soda.io/soda-v4/release-notes/soda-core-release-notes)
- [Tom Baeyens — Introducing Soda Data Contracts](https://medium.com/@tombaeyens/introducing-soda-data-contracts-ac752f38d406)
- [Tom Baeyens — Data contracts as the API for data](https://medium.com/@tombaeyens/data-contracts-as-the-api-for-data-6f2859da10c2)
- [Data Contract Examples: 4 Templates](https://soda.io/blog/data-contracts-examples)
- [Soda v3 docs — Set up data contracts (historical reference)](https://docs.soda.io/data-contracts)
