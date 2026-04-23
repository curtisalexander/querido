# What sets qdo apart

Durable orientation for humans returning to the project and for coding agents starting
fresh. Point-in-time snapshot; last reviewed 2026-04-23.

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

## Ranked differentiators (hardest to copy first)

1. **Metadata-as-persistent-memory, with envelope + next_steps.** No other tool in
   this space treats exploration output as an asset that compounds over time.
   `src/querido/output/envelope.py` defines the agent contract: every scanning
   command returns `{command, data, next_steps, meta}`.
   `src/querido/core/next_steps.py` (~1300 lines) is the deterministic suggestion
   graph that keeps agents moving in the right direction.

2. **Deterministic tools, not LLM-in-the-loop.** `values --write-metadata` writes
   a rule. `quality` checks the rule. The agent brings the brain; qdo brings the
   memory and the map. A philosophical boundary competitors have to *choose* to
   cross.

3. **Snowflake depth.** `qdo snowflake semantic` emits a Cortex Analyst YAML from
   stored metadata. `qdo snowflake lineage` surfaces upstream / downstream
   objects via `GET_LINEAGE`. `sql task` and `sql procedure` templates are
   dialect-aware. No other tool in the space goes this deep into Snowflake
   specifically.

4. **Self-hosting eval at 44/45 (97.8%).** `scripts/eval_skill_files_claude.py`
   runs `claude -p` against the SKILL file and grades results across haiku,
   sonnet, and opus on 15 tasks. Both a credibility artifact and a regression
   detector — any SKILL change that drops the score is signal. The pre-beta
   audit caught the detector doing its job: a hallucinated flag introduced
   during a doc rewrite became a measurable 36/45 regression, two small fixes
   restored the baseline and added +2 on top (haiku 15/15, sonnet 15/15,
   opus 14/15). The one remaining failure is `model-mistake`, zero `qdo-bug`.

5. **Files as primitives.** Sessions are JSONL + stdout. Metadata is YAML.
   Bundles are zip archives. Workflows are YAML. All portable, diffable,
   reviewable, and forkable without a running service.

6. **Agent output format (TOON + YAML via the envelope).** TOON for tabular,
   YAML for nested — ~30–70% fewer tokens than JSON for LLM consumption. In-tree
   encoder (`src/querido/output/toon.py`) with vendored spec-conformance
   fixtures.

7. **Pay for what you use — enforced, not aspirational.** Install extras opt you
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

1. **Pay for what you use.** Only `typer`, stdlib, and `TYPE_CHECKING` imports at
   module top. Rich, Jinja2, duckdb, snowflake-connector, pyarrow, textual all
   import lazily inside functions. Enforce on every PR.

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

## Current state (snapshot, 2026-04-23)

- **Tests:** 1184 passing / 25 skipped. `ruff check`, `ruff format`, `ty check`
  all green. Zero `TODO` / `FIXME` markers anywhere in src or tests.
- **Shipped phases:** 1–4, 6, 7. Phase 5 dropped by design. R-series complete.
  Sharpening Waves 1–4 complete. Pre-release polish pass (items 0–6) landed
  2026-04-22. Pre-beta audit pass (26 items across 5 tiers) landed 2026-04-23.
- **Eval:** 44/45 (97.8%) across haiku, sonnet, and opus on 15 tasks. Haiku
  15/15, sonnet 15/15, opus 14/15. The one failure is `model-mistake`,
  not `qdo-bug`.
- **Surface:** 38 top-level commands across 10 categories. The structured
  envelope is emitted by all data-emitting scans — `sql` and `snowflake`
  gained envelope coverage in the pre-release polish pass. Commands that
  correctly don't emit: `explore` (TUI), `report` (HTML artifact), `tutorial`
  (interactive), `completion` (install artifact).
- **Active polish pass:** see [PLAN.md](./PLAN.md) → "Pre-beta audit pass — active".

---

## Where to look when you're lost

- **Product story:** this file + [README.md](./README.md) "Quick Start".
- **How to be helpful as a coding agent:** [AGENTS.md](./AGENTS.md) and
  [integrations/skills/SKILL.md](./integrations/skills/SKILL.md).
- **What's built, what's next:** [PLAN.md](./PLAN.md).
- **What was considered and rejected:** [IDEAS.md](./IDEAS.md).
- **Code structure:** [ARCHITECTURE.md](./ARCHITECTURE.md).
