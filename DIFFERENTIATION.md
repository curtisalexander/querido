# What sets qdo apart

Durable orientation for humans returning to the project and for coding agents starting
fresh. Point-in-time snapshot; last reviewed 2026-07-06.

> **Audience:** someone — you, a teammate, or an agent — who needs to understand
> what qdo is for and why it's shaped the way it is before touching code or docs.

---

## 30-second orientation

qdo doesn't try to be the tool that runs queries fastest, renders data prettiest, or
has the biggest plugin ecosystem. It tries to be the tool that **accumulates
understanding of your data** so every subsequent investigation — by you, a teammate,
or a coding agent — is faster and more correct than the last.

The product surface looks ordinary (`catalog`, `inspect`, `profile`, `query`). The
asset is the compounding loop those commands form: a `qdo values --write-metadata`
run today sharpens tomorrow's `qdo context`, which sharpens next week's `qdo quality`,
which a teammate can pull down as a `qdo bundle` and have the full picture without
re-doing the work.

**One-liner: qdo is the persistent-memory layer for data exploration, expressed as
plain files and deterministic CLI commands.**

qdo's home turf is **un-modeled data** — extracts, replicas, vendor drops, scratch
DuckDB/SQLite files, and the warehouse corners nobody has curated yet. Where a
governed, documented model already exists, use it; qdo is for the exploration that
happens before (or instead of) that curation.

### Stability boundary

The supported core is `catalog`, `context`, `metadata`, `query`, `assert`,
`quality`, `report`, and `bundle`. These commands define the public loop and
receive compatibility treatment from the first PyPI release.

Specialist exploration, generation, setup, and interactive commands remain
available but are secondary surface. They may evolve, always with deprecation
before a rename or removal. `workflow` is explicitly experimental until real
projects establish that its schema and recovery behavior deserve a stable
contract.

---

## The compounding knowledge loop (the moat)

qdo's differentiator is not any single command — it's the loop the commands form.

```
discover ─► understand ─► capture ─► answer ─► hand off
catalog     context       metadata    query     report / bundle
                          values        ▲
                            │           │
                            └── auto-merged into next context / quality ──┘
```

Concrete example:

1. `qdo values --write-metadata -c mydb -t orders -C status`
   writes `valid_values: [pending, shipped, delivered, cancelled]` to
   `.qdo/metadata/mydb/orders.yaml`.
2. The next `qdo context -c mydb -t orders` surfaces those valid values on the
   `status` column automatically.
3. The next `qdo quality -c mydb -t orders` flags every row whose status isn't
   one of the documented values.
4. The next `qdo bundle export -c mydb -t orders` captures all of that,
   connection-agnostic, for a teammate to import.

This loop is **deterministic**. No LLMs in the loop. No "hopefully the agent
remembers". The tool remembers.

---

## The failure mode qdo exists to prevent — and the real competitor

Hallucinated identifiers are the top documented failure mode for agents doing data
work, and the public evidence says *instructions alone don't fix it*. In
[anthropics/claude-code#53988](https://github.com/anthropics/claude-code/issues/53988)
— "Claude hallucinated identifiers: writes column/field/config names from memory
instead of reading source files" — explicit CLAUDE.md instructions demonstrably
failed to stop it. Tool-enforced verification is what works. That is qdo's thesis,
stated by the market.

It also names qdo's real competitor. Not another product — the null hypothesis:
**"the agent just writes what it learned into CLAUDE.md for free."** qdo's answer,
and the reason everything here says *deterministic*:

- **Notes are advisory; qdo is enforced.** An agent can (and, per the evidence above,
  does) ignore a note. It cannot ignore a tool error: qdo validates table and column
  names at the query boundary and fails with fuzzy did-you-mean suggestions.
- **Notes are prose; metadata is typed.** Free-form notes can't be machine-checked.
  `valid_values` in YAML is mechanically enforced by `quality`, merged into `context`,
  and exported by `snowflake semantic` — one captured fact, three deterministic
  consumers.
- **Notes go stale silently; metadata has provenance.** Every qdo write is
  provenance-tracked and reversible (`metadata undo`); `metadata refresh` re-profiles
  while preserving human-authored fields. Nothing curates a CLAUDE.md.
- **Notes load whole; metadata loads per table.** CLAUDE.md rides along in every
  session in full. qdo metadata surfaces only for the table being investigated.
- **Notes are stuck in one repo; bundles and plain YAML travel.**

This argument must eventually be *demonstrated*, not asserted — see "Hallucination
benchmark" in [PLAN.md](./PLAN.md) for the eval that tests qdo against exactly this
null hypothesis.

---

## Ranked differentiators (hardest to copy first)

1. **Metadata-as-persistent-memory, with envelope + next_steps.** No other tool in
   this space treats exploration output as an asset that compounds over time.
   `src/querido/output/envelope.py` defines the agent contract: every scanning
   command returns `{command, data, next_steps, meta}`.
   `src/querido/core/next_steps/` is the deterministic suggestion graph that
   keeps agents moving in the right direction.

2. **Deterministic tools, not LLM-in-the-loop.** `values --write-metadata` writes
   a rule. `quality` checks the rule. The agent brings the brain; qdo brings the
   memory and the map. A philosophical boundary competitors have to *choose* to
   cross.

3. **Snowflake depth.** `qdo snowflake semantic` emits `create semantic view`
   DDL from stored metadata. `qdo snowflake lineage` surfaces upstream /
   downstream objects via `GET_LINEAGE`. `sql task` and `sql procedure`
   templates are dialect-aware. No other tool in the space goes this deep into
   Snowflake specifically.
   **Note (2026-07-06):** the command originally emitted stage-based Cortex
   Analyst YAML; it was converted to semantic-view DDL when Snowflake started
   calling the YAML path the "legacy stage API" and recommending native
   semantic views for all new implementations. Treat this as an on-ramp to
   Snowflake's native semantics, not a moat.

4. **Self-hosting eval at 45/45 (100%).** `scripts/eval_skill_files_claude.py`
   runs `claude -p` against the SKILL file and grades results across haiku,
   sonnet, and opus on 15 tasks. Both a credibility artifact and a regression
   detector — any SKILL change that drops the score is signal. The pre-beta
   audit caught the detector doing its job: a hallucinated flag introduced
   during a doc rewrite became a measurable 36/45 regression, progressively
   smaller fixes plus a grading-primitive relaxation (`required_any_of`
   accepts any of the legitimate paths an SKILL promotes) restored the score
   and took it to 45/45: haiku 15/15, sonnet 15/15, opus 15/15. Zero
   failures across all three models, zero `qdo-bug`.

5. **Files as primitives.** Sessions are JSONL + stdout. Metadata is YAML.
   Bundles are zip archives. Workflows are YAML. All portable, diffable,
   reviewable, and forkable without a running service.

6. **Pay for what you use — enforced, not aspirational.** Install extras opt you
   in to DuckDB, Snowflake, or the TUI. Every heavy dependency imports inside
   functions, not at module top. A command you don't invoke costs you nothing
   at startup.

---

## What qdo deliberately isn't (and why)

Knowing what *not* to become is half the product strategy.

| Competitor   | What it's good at                         | Why qdo doesn't chase it                     |
|--------------|-------------------------------------------|----------------------------------------------|
| qsv          | Row-stream CSV/Parquet transformation     | Different problem (wrangling, not knowing)   |
| datasette    | Hosted plugin-rich SQLite explorer        | qdo is files + CLI, not a platform           |
| visidata     | Interactive terminal spreadsheet          | qdo is agent-first; TUI is a supplement      |
| harlequin    | Terminal SQL IDE                          | qdo is for knowing data, not authoring SQL   |
| duckdb CLI   | Database shell with zero opinion          | qdo's value is the opinionated workflow     |

qdo also rejects, by design:

- **An in-product NL-to-SQL assistant.** The agent is the brain; qdo is the
  deterministic tool layer.
- **A plugin marketplace or hosted surface.** Files, not services.
- **A Rust rewrite for speed.** The hot path lives in DuckDB / SQLite /
  Snowflake engines; rewriting qdo itself would be low-ROI.
- **A second workflow invocation pattern.** `qdo workflow run <name>` is
  canonical; there is no `qdo <workflow-name>` sugar alias.

---

## Code-level invariants that preserve the product shape

These are the guardrails that keep qdo from drifting into something above.

1. **Pay for what you use.** Optional dependencies are not imported during core
   CLI startup. Optional-only packages such as `querido.tui` may import their
   own dependencies at module level because the package itself is reached
   lazily; elsewhere, heavy imports belong inside the function that uses them.
   Enforce on every PR.

2. **Envelope contract.** Every scanning command emits
   `{command, data, next_steps, meta}` via `output/envelope.py::emit_envelope`.
   Tests in `tests/test_next_steps.py::_ENVELOPE_CASES` enforce the contract.

3. **Files as primitives.** Sessions write JSONL. Metadata writes YAML. Bundles
   are zips. If a feature wants a daemon, it's the wrong feature.

4. **Deterministic tools.** No LLM calls inside qdo itself. Suggestions
   (`next_steps`), metadata fills (`metadata_write`), and quality checks are all
   rule-based.

5. **Preserve CLI surface.** Conversions and removals preserve invocation names;
   deprecation precedes removal.

---

## Filter for future changes

When evaluating any proposed feature, in order:

1. Does this make the compounding loop tighter, cheaper, or more correct?
   If no — defer.
2. Does this cost anything at startup or install for users who don't use it?
   If yes — make it opt-in.
3. Does this require a running service? If yes — rethink until it doesn't.
4. Does this put an LLM call inside qdo? If yes — push it to the agent.
5. Does this fragment the CLI surface? One workflow invocation pattern, not two.

---

## Current state (snapshot, 2026-07-23)

- **Verification:** the last recorded full local gate and 45/45 agent eval were
  green. CI is authoritative; see [PLAN.md](./PLAN.md) for the active release
  gate rather than treating a dated snapshot as current evidence.
- **Shipped phases:** 1–4, 6, 7. Phase 5 dropped by design. R-series complete.
  Sharpening Waves 1–4 complete. Pre-release polish pass (items 0–6) landed
  2026-04-22. Pre-beta audit pass (26 items across 5 tiers) landed 2026-04-23.
- **Eval:** 45/45 (100%) across haiku, sonnet, and opus on 15 tasks.
  Haiku 15/15, sonnet 15/15, opus 15/15. Zero failures.
- **Surface:** 32 top-level commands across 10 categories. The structured
  envelope is emitted by all data-emitting scans — `sql` and `snowflake`
  gained envelope coverage in the pre-release polish pass. Commands that
  correctly don't emit: `explore` (TUI), `report` (HTML artifact), `tutorial`
  (interactive), `completion` (install artifact).
- **Active work:** dogfood, release verification, and the hallucination
  benchmark in [PLAN.md](./PLAN.md). Completed phase and audit history is in
  [`docs/archive/`](./docs/archive/).

---

## Where to look when you're lost

- **Product story:** this file + [README.md](./README.md) "Start with one table".
- **How to be helpful as a coding agent:** [AGENTS.md](./AGENTS.md) and
  [integrations/skills/SKILL.md](./integrations/skills/SKILL.md).
- **What's built, what's next:** [PLAN.md](./PLAN.md).
- **What was considered and rejected:** [IDEAS.md](./IDEAS.md).
- **Code structure:** [ARCHITECTURE.md](./ARCHITECTURE.md).
