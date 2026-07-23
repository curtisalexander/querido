# Plan

Current commitments for qdo. This file answers only two questions: **what is
true now?** and **what should happen next?** Completed execution history lives
in [the archived plan](./docs/archive/PLAN-2026-07-13.md); uncommitted ideas and
rejected directions live in [IDEAS.md](./IDEAS.md).

## Status — 2026-07-23

- **Release state:** `0.2.0` is prepared but not published to PyPI. The PyPI
  JSON endpoint returns 404, and [RELEASING.md](./RELEASING.md) records the
  one-time trusted-publisher setup as incomplete.
- **Supported core:** `catalog`, `context`, `metadata`, `query`, `assert`,
  `quality`, `report`, and `bundle`.
- **Experimental:** workflows remain available but do not yet have a stable
  schema or recovery contract.
- **Verification baseline:** the last recorded full local gate was green, and
  Codex matrix coverage was **45/45 (100%)** across `gpt-5.4-mini`, `gpt-5.4`,
  and `gpt-5.6-sol` on 2026-07-23 after targeted retries completed five
  initially unresolved combinations. CI is authoritative; do not infer current
  green status without rerunning checks.

## Do next

### Release gate — maintainer-owned

- [ ] Use qdo on a real project for at least one week. Record bugs, friction,
  and desires separately; fix release-blocking correctness issues before
  adding surface area.
- [ ] Complete the one-time PyPI trusted-publisher and GitHub environment setup
  in [RELEASING.md](./RELEASING.md).
- [ ] Run the full CI-equivalent gate and build/install the wheel in a clean
  environment.
- [ ] Tag and publish `0.2.0`, then run the documented clean-room verification
  against the live PyPI package.

### Evidence for the product claim

- [ ] Build the hallucination benchmark described below. Do not make a
  comparative “qdo beats notes” claim until the benchmark supports it.

## Hallucination benchmark

**Question:** does a coding agent using warm qdo metadata hallucinate fewer
identifiers and invalid filter values, answer more questions correctly, and
recover more cheaply than the same agent using a bare database CLI or
self-written instruction notes?

### Minimum design

1. Generate a database with deterministic traps: coded enums, lookalike date
   columns, plausible-but-absent identifiers, misleading join cardinality, and
   one wide table.
2. Write 15–25 natural-language tasks with exact answers.
3. Compare four arms: bare database CLI, prior-session prose notes, qdo cold,
   and qdo with metadata populated by a prior exploration.
4. Deterministically grade invalid identifiers, invalid enum literals, final
   answers, attempts to recovery, and token usage.
5. Publish methodology and negative results. If prose notes perform as well as
   qdo metadata, treat that as a product gap rather than hiding the result.

The existing `scripts/eval_skill_files_claude.py` and
`scripts/eval_skill_files_codex.py` provide provider-specific subprocess and
evaluation plumbing over the same task catalog. Extend them only after dogfood
confirms that this remains the right evidence to collect.

## After release

No feature is committed beyond the benchmark. Candidates stay in
[IDEAS.md](./IDEAS.md) until dogfood creates concrete pull. The leading
questions are schema change over time, Snowflake result reuse, and whether a
small MCP wrapper is needed for clients without shell access. Apply the filter
in [DIFFERENTIATION.md](./DIFFERENTIATION.md#filter-for-future-changes) before
promoting any of them.

## Durable engineering references

- The contributor rules and test rubric are in [AGENTS.md](./AGENTS.md).
- Extend `_ENVELOPE_CASES` in `tests/test_next_steps.py` for a new scanning
  command.
- Extend `_READBACK_CASES` in `tests/test_readback_loop.py` when a scan begins
  reading stored metadata.
- Preserve dialect-specific tests where generated SQL genuinely differs.
- Re-run either supported agent eval after changing command surface or installed
  agent instructions; use Claude for the historical multi-model baseline or
  `eval_skill_files_codex.py --models all` for the strict subscription-backed
  Codex 45/45 gate.
