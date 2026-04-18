---
name: qdo-workflow-examples
description: Annotated reference workflows bundled with qdo. Load this when you need a concrete example of the patterns documented in WORKFLOW_AUTHORING.md — each entry here pairs a task shape with a working YAML.
---

# Bundled qdo workflow examples

These workflows ship with qdo and are discoverable via `qdo workflow list` / `qdo workflow spec --examples`. They are intentionally small (<50 lines each) and each teaches a distinct pattern. Use them as starting points when authoring your own.

Every workflow carries inline `# why:` comments explaining *why* each step is shaped the way it is — those comments are aimed at you (the agent authoring the next workflow).

## table-summary

**Shape:** linear composition.
**Inputs:** `connection`, `table`.
**Pattern:** three scans — `inspect` (schema), `profile --quick` (stats), `quality` (callouts). The minimum viable "know this table" workflow.
**Use when:** you're handed a table and need the standard exploration triad in one call.

```bash
qdo workflow run table-summary connection=mydb table=orders
```

## schema-compare

**Shape:** conditional follow-up (`when:`).
**Inputs:** `connection`, `left`, `right`.
**Pattern:** `diff` the schemas; *only if* they differ, run `joins` to discover candidate keys. Demonstrates:
- `when:` evaluating boolean combinators over captured output (`${diff.data.changed} or ${diff.data.added} or ${diff.data.removed}`).
- Lenient outputs — when the `joins` step is skipped, `${joins.data.candidates}` resolves to `null` instead of aborting.

**Use when:** comparing two versions of the same table across environments, or exploring a newly added table against a reference one.

```bash
qdo workflow run schema-compare connection=mydb left=orders right=orders_staging
```

## migration-safety

**Shape:** gather + assert. Ends in `qdo assert` calls that exit non-zero on invariant violation — CI-friendly.
**Inputs:** `connection`, `before`, `after`, optional `max_row_delta_pct` (default `1.0`).
**Pattern:** capture row counts for both tables, diff the schemas, then assert (a) row-count drift is within the threshold and (b) no new nulls were introduced on columns that still exist after the migration. Demonstrates:
- Using `qdo assert --expect-lte` as the final gate on a workflow.
- Chain-skip via `when:` when a prior step (here, schema diff) would make a downstream assertion meaningless.
- Parameterizing a tolerance via the `inputs` block so the same workflow handles strict and loose migrations.

**Use when:** promoting a table from staging to prod, running a schema refactor, or anywhere a migration should be gated on not losing or duplicating rows.

```bash
qdo workflow run migration-safety connection=mydb before=orders_v1 after=orders_v2
qdo workflow run migration-safety connection=mydb before=orders_v1 after=orders_v2 max_row_delta_pct=0.1
```

## column-deep-dive

**Shape:** single-column focus.
**Inputs:** `connection`, `table`, `column`, optional `top_n`.
**Pattern:** inspect the table, list distinct `values` for the column, show `dist` (which auto-detects numeric vs categorical — no `when:` type check needed).
**Teaches:** a one-input focus alongside connection+table; relying on a primitive's auto-dispatch instead of conditional logic.

**Use when:** you want to understand a single column's shape in depth — good prep before writing a WHERE clause, building a filter, or using the column as a grouping key.

```bash
qdo workflow run column-deep-dive connection=mydb table=customers column=country
```

## wide-table-triage

**Shape:** same-primitive-twice composition.
**Inputs:** `connection`, `table`.
**Pattern:** two `profile` steps with different flags — first `--quick` (fast row/null counts for every column), then `--classify` (categorizes columns as numeric / categorical / temporal / high-cardinality / identifier).
**Teaches:** step ids must be unique even when the subcommand repeats; using `--classify` to drive a follow-up decision about which subset to profile in full.

**Use when:** a table has 50+ columns and you need to triage before investing time in a full profile. Follow-up: persist a `column-set` with `qdo config column-set save` so subsequent runs target only the interesting columns.

```bash
qdo workflow run wide-table-triage connection=mydb table=events
```

## table-handoff

**Shape:** conditional composition with row-count-gated follow-up steps.
**Inputs:** `connection`, `table`.
**Pattern:** `inspect` runs unconditionally (cheap probe). `profile --quick` runs only when the table has rows (`${schema.data.row_count} != null and ${schema.data.row_count} > 0`). `quality` runs only when profile wasn't skipped (`${stats.data} != null`). Outputs degrade to `null` for skipped steps so the handoff document still lands on an empty table — it just honestly says "no rows yet".
**Teaches:** null-safe `when:` comparisons (the `!= null and` guard idiom); gating an expensive step on a cheap probe's result; outputs that resolve gracefully when their source step skipped.

**Use when:** you want a summary that doesn't waste cycles on empty tables or fail noisily on views whose row-count the connector can't cheaply determine. Contrast with `table-summary`, which runs all three scans unconditionally.

```bash
qdo workflow run table-handoff connection=mydb table=orders
```

## feature-target-exploration

**Shape:** data-science starter — work-in-progress scaffold.
**Inputs:** `connection`, `table`, `target`.
**Pattern:** the first pass for a fresh modeling dataset — schema, full profile, quality flags, target distribution. Uses only existing primitives today.
**Teaches:** authoring a workflow against an incomplete toolbox — the YAML contains `# gap:` comments pointing at primitives that don't exist yet (outlier detection, correlation matrices, target-aware feature ranking, group stats with multiple aggregates). See `IDEAS.md` ("Data-science primitives") for the feasibility discussion.

**Use when:** you've been handed a table with a target column and you want the first-pass univariate view before deciding whether to add the missing primitives locally or move to a notebook.

```bash
qdo workflow run feature-target-exploration connection=mydb table=customer_churn target=churned
```

# Browsing from the command line

```bash
qdo workflow list                       # all bundled + user + project workflows
qdo workflow show <name>                # print a specific workflow's YAML
qdo workflow spec --examples            # concatenated YAML of all bundled examples
```

When you generate your own workflow with `qdo workflow from-session`, the resulting draft will already include per-step captures and parameterized connection/table inputs — use these examples as reference when tightening the draft.
