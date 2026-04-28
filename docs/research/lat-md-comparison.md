# lat.md ↔ qdo: research notes and mini-plan

> **Status:** research / parking lot. Not committed work. Captured on 2026-04-28
> while exploring whether qdo should evolve from "a pile of tools" toward an
> explicit "knowledge graph for your data."
>
> **Audience:** future-me and any contributor thinking about the shape of qdo's
> next chapter. Read DIFFERENTIATION.md first; this doc builds on top of it.

---

## Why this doc exists

qdo started as a set of CLI tools. The vision is bigger: a **persistent
knowledge graph of a user's data**, populated by qdo commands, queryable by the
user *and* their coding agent, and shareable with teammates. lat.md
([https://www.lat.md/](https://www.lat.md/)) is the same product shape applied
to *code* — so it's the closest analog to study before reshaping qdo.

This file captures (a) what lat.md is, (b) where qdo and lat.md align and
diverge, and (c) a ranked, actionable plan for incorporating the highest-value
ideas.

---

## What lat.md is, in one paragraph

**Pitch:** *"A knowledge graph for your codebase, written in markdown."*

A `lat.md/` directory at the repo root holds interlinked markdown files. Three
link types tie everything together:

- `[[file#Section]]` — sections cite each other
- `[[src/auth.ts#validateToken]]` — docs cite code symbols
- `// @lat: [[section-id]]` — code cites docs (backlink in source)

A small CLI (`lat init`, `check`, `locate`, `section`, `refs`, `search`,
`expand`, `mcp`) lets agents navigate the graph instead of grepping. `lat
check` validates referential consistency (drift detection). `lat search` is
semantic via embeddings. `lat mcp` exposes the graph over MCP. Test specs
marked `require-code-mention: true` must be referenced from test code, or `lat
check` flags them.

### Sources

- [lat.md homepage](https://www.lat.md/)
- [lat.md GitHub repo](https://github.com/1st1/lat.md)
- [lat.md README](https://github.com/1st1/lat.md/blob/main/README.md)
- [Hacker News discussion](https://news.ycombinator.com/item?id=47561496)
- [ASCII News writeup](https://ascii.co.uk/news/article/news-20260330-fe1df78f/latmd-knowledge-graph-system-for-ai-assisted-codebases)
- Adjacent: [GitLab Knowledge Graph](https://docs.gitlab.com/user/project/repository/knowledge_graph/),
  [FalkorDB CodeGraph](https://www.falkordb.com/blog/code-graph/),
  [Cognee repo-to-graph](https://www.cognee.ai/blog/deep-dives/repo-to-knowledge-graph),
  [Knowledge Graph for Repo-Level Code Gen (arXiv)](https://arxiv.org/html/2505.14394v1)

---

## The parallel

lat.md and qdo are *the same product shape applied to different substrates*:

|                    | lat.md                                  | qdo                                                   |
| ------------------ | --------------------------------------- | ----------------------------------------------------- |
| Substrate          | code                                    | data                                                  |
| Asset              | knowledge graph in `lat.md/`            | metadata in `.qdo/metadata/`                          |
| Primitives         | markdown + wiki-links                   | YAML + envelope                                       |
| Loop               | doc ↔ code via backlinks                | values → metadata → context → quality                 |
| Philosophy         | deterministic; agent brings the brain   | identical (DIFFERENTIATION.md §2)                     |
| Agent surface      | MCP server + `lat expand`               | SKILL.md + JSON envelope                              |
| Sharing            | commit `lat.md/` with the repo          | `qdo bundle export`                                   |
| Drift detection    | `lat check`                             | partial: `qdo quality` / `assert` / `diff`            |

The deepest principles already match. What lat.md does that qdo doesn't yet:

1. Makes the graph **visible** (root-level directory, links between files,
   one-shot drift check).
2. Frames the product around the **noun** ("knowledge graph") not the verb
   ("exploration").
3. Gives agents **graph-aware operations** (refs, expand, mcp) so they don't
   reconstruct the graph from per-table calls.
4. Positions docs as the **primary** review artifact; code review is secondary.

---

## Recommendations (ranked, with rationale)

### Tier 1 — biggest leverage

1. **Cross-table link syntax in metadata YAML.** Per-table metadata is a list of
   nodes; the graph emerges from edges. Add link syntax:

   ```yaml
   # qdo/metadata/mydb/orders.yaml
   columns:
     customer_id:
       references: [[customers.id]]    # join edge
     status:
       glossary: [[glossary#fulfillment-status]]
       valid_values: [pending, shipped, delivered, cancelled]
       require_assertion: true          # mirrors lat's require-code-mention
   ```

   Unlocks `qdo refs --column customer_id` and the `qdo check` work below.

2. **`qdo check` umbrella command (drift detection).** You already have
   `quality`, `assert`, `diff`. lat.md's framing is *one verb*: "is the graph
   still consistent with reality?" Wrap them as `qdo check` and have
   SKILL.md prescribe agents call it before finishing work:
   - declared schema vs actual schema
   - declared `valid_values` vs observed values
   - declared `references` resolve to real tables/columns
   - declared PK/uniqueness still holds
   - assertions covering `require_assertion: true` columns still pass

3. **Promote `.qdo/` to a visible `qdo/` directory.** A dotdir signals "tool
   config, gitignore me." If metadata is the asset, the asset shouldn't be
   hidden. Recommend committing `qdo/metadata/` next to dbt/SQL projects the
   way teams commit `lat.md/`. Big philosophical signal with very small code
   change.

### Tier 2 — high value, more work

4. **`qdo mcp` server.** Today agents shell out for `qdo context -f json` per
   call. An MCP server lets editors/agents query metadata as first-class
   context. lat.md ships this; for qdo it's even more valuable because metadata
   gets queried far more often than written.

5. **`qdo expand` for prompts.** Mirrors `lat expand`:
   `qdo expand "investigate {{table:orders}} {{column:orders.status}}"` injects
   metadata + context inline before the agent sees the prompt. Removes a class
   of "agent forgot to call context first" failures.

6. **A graph view, not just per-table reports.** `qdo report graph` — HTML/SVG:
   tables as nodes, joins as edges, metadata coverage as fill, PII as colored
   badges. Plus a text version: `qdo metadata coverage` ("orders: 90%,
   customers: 30%, transactions: 0%") so the user knows what to document next.

### Tier 3 — smaller, still worth it

7. **Glossary as a first-class node type.** Business terms (Customer, Order,
   Subscription) cut across tables. Add `qdo/glossary/` as a sibling to
   `qdo/metadata/`; columns link to terms via `glossary: [[customer]]`.

8. **Bidirectional link maintenance.** Every `references: [[customers.id]]`
   should be reciprocal — `customers.id` should know it's referenced by
   `orders.customer_id`. Auto-maintain on `qdo metadata refresh`.

9. **`qdo bundle diff` for PR review.** lat.md positions doc review as
   primary. For qdo: in a PR, surface "the orders.status enum changed from 4
   values to 5" *before* reviewers look at the SQL. Cheap to compute, big UX
   payoff.

10. **`qdo bootstrap` end-to-end first-run.** Today the first 60 seconds is
    "install + read tutorial." Make it "produce a populated graph": one command
    runs catalog → init metadata for top-N tables → suggest values → write the
    agent skill. lat.md's `lat init` is the shape; we go further because we
    can populate from the data itself.

### Tier 4 — communication / framing

11. **Lead with the noun, not the verb.** Try a one-liner closer to:
    > qdo is a knowledge graph for your data, written in plain files. Catalog,
    > profile, and query it — agents and teammates pick up where you left off.

    Today's "agent-first data exploration CLI" is accurate but emphasizes the
    verb the user thinks they're buying, not the noun they actually get value
    from.

12. **Tighten the README.** lat.md README is short and graph-shaped: pitch →
    example file → link semantics → commands. Ours is 566 lines mixing pitch
    with sampling internals, Snowflake auth, and dependency policy. Split:
    - `README.md`: pitch + a screenshot of a metadata file linking to others +
      6 commands
    - `docs/installation.md`, `docs/sampling.md`, `docs/connections.md`: ops
      detail

13. **Lead with the artifact, not the workflow.** Show a populated
    `qdo/metadata/orders.yaml` with `references:` and `glossary:` links
    *before* showing any commands. lat.md does this; readers see the linked
    markdown sample before they see `lat init`.

### What NOT to copy

- **Embeddings/semantic search inside qdo.** lat.md needs it because code
  symbol names are noisy; data has clean column names + types. The "no LLM
  in the loop" invariant is right. Expand `qdo metadata search` cross-table
  rather than going semantic.
- **The `// @lat:` backlink in source.** Data isn't code; the closest analog
  is SQL `COMMENT ON COLUMN`, and most warehouses already do that. Don't
  invent a parallel system.

---

## Additional ideas worth parking

These didn't fit cleanly into the tiered list but came up while writing it.

- **Knowledge density as a metric.** Surface `coverage_pct` in the envelope on
  `qdo catalog` so even a no-op call nudges the user toward the next best
  table to document.
- **Versioning the graph over time.** Log "graph health" — what % of metadata
  files passed last `qdo check`, when each table's metadata was last verified.
  Makes drift visible historically, not just at HEAD.
- **`qdo lineage` as a graph-shaped command.** `qdo snowflake lineage` exists
  per-object; a cross-table lineage view (built from declared `references:`
  plus warehouse metadata where available) would slot into the graph view in
  Tier 2 #6.
- **Self-hosting eval should measure graph use.** The eval already grades
  agents on tasks. Add a paired condition: same task, with vs. without a
  populated metadata directory. If the populated case doesn't beat the empty
  case by a wide margin, the compounding loop isn't earning its keep yet.
- **Markdown alongside YAML?** lat.md's choice of markdown matters because
  humans skim it naturally. YAML is great for agents but worse for browsing.
  Consider rendering each metadata YAML to a sibling `.md` (or HTML) on
  `qdo metadata refresh` so the graph is browseable in any IDE.
- **A "graph linter" beyond `qdo check`.** Style-level warnings: orphan
  columns (no description, no glossary link), unreferenced glossary terms,
  tables with metadata older than N days. Cheap, runs in CI, prevents rot.
- **An explicit `qdo/CHANGELOG.md` for the metadata directory.** Helps
  reviewers and future-self understand *why* a `valid_values` set changed,
  not just *that* it changed.

---

## Mini-plan: how to start (when we pick this up)

**Goal:** validate the "qdo as knowledge graph" reframing with the smallest
end-to-end slice that exercises every layer.

### Phase 0 — decide

- [ ] Re-read this doc and DIFFERENTIATION.md side by side. Confirm the
  reframing is the right next chapter (vs. another sharpening pass on the
  current surface).
- [ ] Decide on the directory rename: `.qdo/` → `qdo/`. This is a one-way
  door — choose now, document the migration before any code lands.
- [ ] Pick the canonical link syntax: `[[table.column]]` vs.
  `[[mydb/orders#status]]` vs. JSON pointer style. Whatever ships first will
  be hard to change.

### Phase 1 — foundation (Tier 1, ~1 week of focused work)

- [ ] Add `references:` and `glossary:` fields to the metadata schema.
  Backwards-compatible: old files without them still load.
- [ ] Implement `qdo check` as an umbrella over existing `quality` / `assert`
  / `diff`, plus new validators for `references` resolution and
  `valid_values` coverage.
- [ ] Add a `require_assertion: true` flag and have `qdo check` flag any
  column with the flag that lacks a recorded assertion.
- [ ] Update SKILL.md so the canonical agent loop ends with `qdo check`.

### Phase 2 — agent surface (Tier 2 #4–5)

- [ ] Spike `qdo mcp`: minimal MCP server exposing `context`, `metadata
  show`, `refs`, and `check`. Don't go broad — go deep on the four most-used
  reads.
- [ ] `qdo expand` with a small template syntax (`{{table:X}}`,
  `{{column:X.Y}}`, `{{glossary:term}}`). Reuses metadata reads under the
  hood.

### Phase 3 — visibility (Tier 2 #6 + Tier 3 #10)

- [ ] `qdo metadata coverage` text view. Lands first because it's free —
  pure read over existing files.
- [ ] `qdo report graph` HTML/SVG view. Reuses the per-table report renderer
  for node detail panes.
- [ ] `qdo bootstrap` end-to-end first-run command.

### Phase 4 — polish & framing (Tier 4)

- [ ] Rewrite README around the noun. Lead with a populated metadata file.
- [ ] Split ops detail (installation, sampling, connections) into `docs/`.
- [ ] Update DIFFERENTIATION.md to call the graph reframing out as a ranked
  differentiator (it's already implied; make it explicit).

### Out of scope for the first pass

- Embeddings / semantic search (violates the invariant).
- Source-code backlink syntax (wrong substrate).
- Markdown rendering of YAML (Tier 3 idea, defer).
- Versioning the graph over time (defer until coverage is real).

---

## Open questions

- **Where does dbt/sqlmesh fit?** Many teams already maintain a parallel
  semantic layer. Does qdo's graph compete with their model YAML, or import
  from it? Importing is probably the right move — *meet teams where they are*.
- **Single-user vs team?** lat.md is a per-repo artifact, so team semantics
  are inherited from git. qdo's `bundle export` is a different model. Should
  the canonical mode be "git-tracked `qdo/` directory" with bundles as a
  fallback for teams without shared repos?
- **Glossary scope.** Per-connection? Per-database? Global to the user? Each
  has tradeoffs; lat.md ducks this because code lives in one repo.
- **MCP vs CLI as the primary agent surface.** If MCP becomes primary, does
  the JSON envelope still earn its weight, or do we keep both as
  belt-and-suspenders?

---

## Snapshot

This file is a snapshot, not a roadmap. Before acting on it:

1. Reread DIFFERENTIATION.md and confirm none of these recommendations have
   been rejected since this was written.
2. Cross-reference IDEAS.md — some of this may already be there in different
   words.
3. If the reframing lands, port the agreed items into PLAN.md and delete
   them from this file so there's one source of truth.
