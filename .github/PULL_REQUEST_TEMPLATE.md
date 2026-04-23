<!--
Thanks for contributing to qdo. A few quick pointers before you submit:

- Run `uv run ruff format`, `uv run ruff check`, `uv run ty check`, and `uv run pytest` locally.
- Keep commits focused; prefer new commits over --amend.
- For docs changes, check that file-tree listings in ARCHITECTURE.md still match reality.
-->

## Summary

<!-- What does this PR do? 1–3 sentences. Focus on the *why*. -->

## Changes

<!-- Bullet list of what shipped. Keep it factual. -->

-
-

## How to test

<!--
Concrete commands or steps a reviewer can run.
If the change is CLI-visible, include the invocation and the expected envelope shape or behavior.
-->

```bash
```

## Checklist

- [ ] `uv run pytest` passes locally (1183 currently passing, 25 skipped)
- [ ] `uv run ruff check src/ tests/` clean
- [ ] `uv run ruff format src/ tests/` clean
- [ ] `uv run ty check src/` clean
- [ ] If this touches user-facing behavior: README / docs / SKILL refreshed
- [ ] If this adds a new scanning command: wired through `emit_envelope` + added to `_ENVELOPE_CASES`
- [ ] If this changes the compounding loop or SKILL.md: re-ran the eval (`scripts/eval_skill_files_claude.py --models all`)

## Related

<!-- Issues, prior PRs, PLAN.md items, or DIFFERENTIATION.md sections this touches. -->
