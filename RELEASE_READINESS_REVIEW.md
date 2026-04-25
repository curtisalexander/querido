# Release readiness review — qdo

Date: 2026-04-25

This review is a release-readiness pass over the repository from the perspective of a first user, a coding agent, and a future maintainer. It uses `ARCHITECTURE.md`, `PLAN.md`, `README.md`, `IDEAS.md`, and `DIFFERENTIATION.md` as background, then checks the current working tree, docs, package build, CLI behavior, and test suite.

## Verdict

**qdo is close to releasable, but I would not announce it to users until the release-artifact story is fixed.** The codebase is functionally strong: the full suite passes, lint/type checks are green, the wheel builds, a minimal install can run SQLite-only commands, optional DuckDB failure is structured and actionable, and the product story is genuinely differentiated.

The main release blocker is not core functionality; it is distribution credibility. The README's recommended install path points at a GitHub Release URL that currently does not expose a wheel to installers, and `gh release view v0.1.0` reports no release. A new user following the README cannot install the tool as documented.

Once the release artifacts and a few documentation consistency issues are fixed, I would be comfortable with a beta-style release.

## Evidence from this pass

Commands run during review:

```bash
uv run ruff check src/ tests/
uv run ty check
uv run pytest
uv build --wheel --sdist --out-dir /tmp/qdo-dist-check
uv run qdo --help
uv run qdo overview > /tmp/qdo-overview.md
uv run qdo catalog -c data/test.db -f json
uv run qdo context -c data/test.db -t orders -f json
uv run qdo quality -c data/test.db -t orders -f json
```

Results:

- `ruff check`: pass
- `ty check`: pass
- `pytest`: **1193 passed, 25 skipped** in ~15s
- Wheel + sdist build: pass
- `docs/cli-reference.md` matches `qdo overview` except for one trailing blank line
- Built wheel contains packaged agent docs:
  - `querido/agent_docs/skills/SKILL.md`
  - `querido/agent_docs/skills/WORKFLOW_AUTHORING.md`
  - `querido/agent_docs/skills/WORKFLOW_EXAMPLES.md`
  - `querido/agent_docs/continue/qdo.md`
- Minimal wheel install can run SQLite:
  - `qdo preview -c data/test.db -t orders -r 1 -f json` succeeds
- Minimal wheel install without DuckDB fails usefully on DuckDB:
  - structured `MISSING_DEPENDENCY` error with install hints
- `qdo --help` startup through `uv run` is fast (~70ms on this machine)

Caveat: the working tree already had a local modification in `scripts/retag.sh` before this document was written. I did not modify it.

## Release blockers

### 1. README install instructions currently fail

`README.md` says pre-built wheels are available from GitHub Releases and recommends:

```bash
uv tool install querido \
  --find-links https://github.com/curtisalexander/querido/releases/expanded_assets/v0.1.0
```

But a dry-run installer check could not find `querido` at that URL:

```bash
pip install --dry-run --find-links \
  https://github.com/curtisalexander/querido/releases/expanded_assets/v0.1.0 \
  querido
# ERROR: No matching distribution found for querido
```

Additional checks:

- The expanded-assets page is HTML and did not contain `.whl` links during this review.
- `gh release view v0.1.0 --repo curtisalexander/querido` reported `release not found`.
- A local `dist/querido-0.1.0-py3-none-any.whl` exists, but `dist/` is ignored and not a user-facing distribution channel.

**Fix before release:** create the GitHub Release, upload the wheel and sdist, then verify the README command in a clean environment. If GitHub's `expanded_assets` page is not a reliable `--find-links` target, switch the README to a direct wheel URL, a proper simple index, or PyPI/TestPyPI.

### 2. Changelog release boundary is inconsistent with the tag

`CHANGELOG.md` has substantial current functionality under `[Unreleased]`, including `qdo agent list/show/install`, but the local tag state reports `v0.1.0-dirty` and `git log v0.1.0..HEAD` shows no commits after the tag. That means the tag appears to include the changes that the changelog calls unreleased.

This creates confusion for users and maintainers:

- Is `qdo agent install` part of v0.1.0 or post-v0.1.0?
- Should the published v0.1.0 wheel include the packaged agent docs?
- Should the v0.1.0 changelog include the pre-beta audit and 45/45 eval result?

**Fix before release:** decide whether current `HEAD` is v0.1.0. If yes, fold the `[Unreleased]` content into the `0.1.0` section and retag/release. If no, bump to `0.1.1` or `0.2.0` and update README install URLs accordingly.

### 3. Do one real clean-room install before announcing

A local wheel install worked when dependencies were fetched normally, but the documented GitHub Release path did not. Before announcement, run the exact user journey from an empty temp directory and clean venv/tool environment:

```bash
uv tool install querido --find-links <final release URL>
qdo --version
qdo --help
qdo agent list
qdo preview -c ./some.db -t some_table -r 5 -f json
qdo agent install skill --path /tmp/qdo-skill-smoke
```

Also test optional extras:

```bash
uv tool install 'querido[duckdb]' --find-links <final release URL>
uv tool install 'querido[tui]' --find-links <final release URL>
```

## High-priority non-blockers

### 1. Snapshot numbers are already drifting

Docs say:

- `PLAN.md`: 1192 passing / 25 skipped
- `DIFFERENTIATION.md`: 1192 passing / 25 skipped

Current local suite reports **1193 passing / 25 skipped**.

This is minor, but the project leans heavily on test/eval numbers as credibility artifacts, so stale numbers are noticeable. Either update them immediately before release or phrase them as approximate / last-audited numbers to reduce churn.

### 2. `DIFFERENTIATION.md` says 38 top-level commands; current root help exposes 32

Current root command list contains 32 top-level commands:

`agent`, `assert`, `bundle`, `cache`, `catalog`, `completion`, `config`, `context`, `diff`, `dist`, `explain`, `explore`, `export`, `freshness`, `inspect`, `joins`, `metadata`, `overview`, `pivot`, `preview`, `profile`, `quality`, `query`, `report`, `session`, `snowflake`, `sql`, `template`, `tutorial`, `values`, `view-def`, `workflow`.

`DIFFERENTIATION.md` says 38. Update or remove the count; the exact number is not strategic.

### 3. `ARCHITECTURE.md` is missing recently added `agent_docs` / `cli/agent.py`

The architecture tree does not list:

- `src/querido/agent_docs/`
- `src/querido/cli/agent.py`

Since `qdo agent install` is now central to the no-clone agent onboarding story, this should be in the architecture doc before release.

### 4. Some dead output code from removed `qdo search` remains

`qdo search` was intentionally cut, but these still exist:

- `src/querido/output/console.py::print_search`
- `src/querido/output/formats.py::format_search`
- dispatch-table entries for `