# Contributor guide for qdo

This file helps people (and coding agents) contributing to qdo get up to speed quickly. It is deliberately short — for the end-user story and command surface, read elsewhere.

## Where to look first

- **Product story** — [DIFFERENTIATION.md](./DIFFERENTIATION.md) (5 min). Read this **before touching code**. It's the orientation doc on what qdo is for, what it deliberately isn't, and the invariants that keep it that way. Prevents whole classes of well-intentioned-but-off-target changes.
- **What's built, what's next** — [PLAN.md](./PLAN.md) is the committed todo list. Pick up any unchecked item; don't invent new ones without a matching entry.
- **What's been considered and rejected** — [IDEAS.md](./IDEAS.md). Before proposing a new feature, check here — the filter in DIFFERENTIATION.md plus the rejected list catch most drift.
- **Code layout** — [ARCHITECTURE.md](./ARCHITECTURE.md). File-tree listing + key design principles; kept in sync with the code.
- **End-user surface** — [README.md](./README.md) and [docs/cli-reference.md](./docs/cli-reference.md). Don't duplicate that content here.
- **Agent integration** — [integrations/skills/SKILL.md](./integrations/skills/SKILL.md) (Claude Code) and [integrations/continue/qdo.md](./integrations/continue/qdo.md) (Continue.dev). If you're using qdo *from* an agent, read SKILL.md; if you're changing the agent-facing envelope, update both.

## Quick start

```bash
# Install dependencies (dev group includes duckdb for tests)
uv sync

# Run the CLI
uv run qdo --help

# Before every commit: format, lint, type, test — CI runs the same four
uv run ruff format src/ tests/
uv run ruff check src/ tests/
uv run ty check
uv run pytest
```

Line length is 99 (`[tool.ruff]` in `pyproject.toml`). There are no pre-commit hooks — run the checks manually.

## Critical invariants

These are the rules a contributor must know. Breaking any of them will fail review.

### 1. Pay for what you use

SQLite is the only always-available backend. DuckDB, Snowflake, and the TUI are opt-in extras:

```bash
uv pip install querido               # SQLite only
uv pip install 'querido[duckdb]'     # + DuckDB + Parquet
uv pip install 'querido[snowflake]'  # + Snowflake
uv pip install 'querido[tui]'        # + textual for qdo explore
```

**All heavy imports must happen inside functions, not at module level.** Only `typer`, stdlib, and `TYPE_CHECKING`-only imports are allowed at the top of a module. This keeps `qdo --help` fast regardless of what's installed.

```python
# CORRECT — imported only when this command runs
def my_command():
    from rich.table import Table
    ...

# WRONG — slows down every invocation, even --help
from rich.table import Table
```

Enforce on every PR. `config add`/`clone` also probe backend importability at config-write time and warn with the exact `uv pip install 'querido[<extra>]'` command — match that pattern if you add a new backend.

### 2. Envelope contract

Every scanning command emits `{command, data, next_steps, meta}` via `output/envelope.py::emit_envelope` under `-f json` / `-f agent`. Tests in `tests/test_next_steps.py::_ENVELOPE_CASES` enforce this — adding a new scanning command means adding it to that list.

### 3. Files as primitives

Sessions write JSONL. Metadata writes YAML. Bundles are zips. Workflows are YAML. If a feature wants a daemon, socket, or hosted surface, it's the wrong feature — see the rejected directions in IDEAS.md.

### 4. Deterministic tools — no LLM calls inside qdo

The agent brings the brain; qdo brings the memory and the map. `next_steps`, metadata writes, quality checks, and auto-fills are all rule-based. No LLM calls inside qdo itself, no "clever" inference that adds randomness.

### 5. Input validation at the boundary

Table and column names are validated at the CLI boundary via `validate_table_name()` / `validate_column_name()` in `connectors/base.py`. They're interpolated into SQL templates (Jinja2) and sampling subqueries (f-strings), so they must be safe identifiers. Always validate before passing into a template.

### 6. Connector protocol

Every backend implements the `Connector` protocol in `connectors/base.py` and supports context-manager usage. Always use `with create_connector(config) as conn:` in CLI commands. When adding a new backend: implement the full protocol including `__enter__` / `__exit__`, pick a case normalization strategy (lowercase for SQLite/DuckDB, uppercase for Snowflake) and document it in the connector's class docstring so the in-process `_columns_cache` keys stay deterministic.

### 7. SQL templates, not string literals

All database queries live in `.sql` files under `src/querido/sql/templates/` and are rendered with Jinja2. Exception: connector `get_columns()` methods, which use backend-specific mechanisms (`PRAGMA`, `information_schema`, `duckdb_columns()`). See ARCHITECTURE.md for the renderer's dialect-fallback rules.

### 8. Preserve CLI surface

Renames and removals preserve the public invocation names. Deprecation precedes removal. `qdo workflow run <name>` is the canonical workflow invocation — there is no `qdo <workflow-name>` sugar alias (that was considered and rejected; see IDEAS.md).

## Writing tests

Every test is a lifelong maintenance obligation. A tight, fast suite beats a big one. Before adding a test, read these rules:

1. **Name the failure mode.** Write the one-sentence regression this test prevents. If you can't name it, don't write the test. "Coverage" is not a failure mode.
2. **Test behavior, not framework.** We don't own Typer's `--help` rendering, Jinja's escaping, YAML's round-trip, or DuckDB's query engine. A test whose assertions are really about a dependency's contract belongs upstream.
3. **Exit code alone is not an assertion.** `assert result.exit_code == 0` proves the command parsed, nothing more. Pair every exit-code check with an assertion on the output payload, a file written to disk, or an observable side effect. Same for `!= 0` — assert on the structured error code, not just failure.
4. **Prefer parameterization to copy-paste.** Two tests that differ only in fixture path should be one `@pytest.mark.parametrize` unless the assertions genuinely diverge (e.g., DDL types, UDF syntax). When they do diverge, keep both — that's real dialect coverage.
5. **Scenario coverage is not redundancy.** Three tests per rule that each exercise a distinct branch (populated / empty / no-metadata) are each doing work. Don't cut them in the name of "deduplication."
6. **Integration beats unit for helpers used in one place.** One round-trip test through a CLI command beats an isolated unit test of a helper called only from that command. Reserve unit tests for pure logic.
7. **Don't string-match error prose.** Wording drifts; brittle substring matches churn on every refactor and silently pass when error handling degrades. Assert on error codes, exit statuses, or structured `try_next` / envelope fields — not human-readable messages.

PLAN.md has a "Durable references" section with extensible contract tests (`_ENVELOPE_CASES`, `_READBACK_CASES`) and a "Don't touch — already good" list; check both before pruning.

## Self-hosting evaluations

Three optional eval scripts under `scripts/`. All are opt-in — run them locally after docs or command-surface changes; failures that cluster in a category point at specific docs to tighten.

- **`eval_skill_files_claude.py`** — feeds SKILL.md + AGENTS.md + WORKFLOW_EXAMPLES.md to `claude -p` and asks it to answer 15 realistic data-exploration tasks across Haiku / Sonnet / Opus. Per-model pass gates (70 / 85 / 95 %). Current baseline: **45/45 (100%)** — zero failures across all three models. Safeguards: per-task timeout (`--task-timeout-sec`), overall wall-clock cap (`--max-wall-clock-minutes`, default 20). Results land in `scripts/eval_results/` (gitignored).
- **`eval_skill_files_codex.py`** — same task catalog against Codex via `codex exec`, for agent-cross-check.
- **`eval_workflow_authoring.py`** — feeds `WORKFLOW_AUTHORING.md` + `qdo workflow spec` + bundled examples to `claude -p` and asks for three novel workflows, then lint + runs them. Signals whether the authoring doc is pedagogically complete.

All three refuse to run with `ANTHROPIC_API_KEY` set (they're meant to go through Claude's CLI auth) and enforce a budget guardrail.

## Test data

```bash
uv run python scripts/init_test_data.py   # creates data/test.db and data/test.duckdb
```

| Database | Tables | Rows |
|----------|--------|------|
| test.db (SQLite) | customers, products, orders, datatypes | 1000 / 1000 / 5000 / 100 |
| test.duckdb | customers, products, orders, datatypes | 1000 / 1000 / 5000 / 100 |

`orders` intentionally contains data-quality outliers (~0.8% malformed status, ~2.5% null amounts, ~1.5% negative amounts) so `qdo quality` and `qdo values --write-metadata` demos have something real to flag. `datatypes` covers edge-case types (blobs, JSON, nulls, negatives, large ints).

## Dependency management

- **uv** for packaging. Everything in `pyproject.toml`; no `requirements.txt`.
- **ruff** for lint + format. **ty** for type check. **pytest** for tests.
- DuckDB is in the `[dependency-groups] dev` group so tests always run.

```bash
uv run python scripts/check_deps.py              # report outdated + quarantine status
uv run python scripts/check_deps.py --update     # update packages past quarantine
uv run python scripts/check_deps.py --audit      # include uv audit for known CVEs
```

`check_deps.py` queries PyPI release dates and skips packages inside a 7-day quarantine (supply-chain guard). Always run tests after updating.

## Releasing

```bash
./scripts/retag.sh v0.1.0          # retag HEAD
./scripts/retag.sh v0.1.0 abc1234  # retag a specific commit
```

Deletes the remote tag + GitHub release, then recreates the tag at the target commit and pushes. Always commit + push the release content first, then retag. When the user says "retag", run this script — don't use raw `git tag` commands.

## Style

- Keep functions focused. Avoid premature abstraction.
- Tests prove things work; they don't chase coverage.
- Type hints on public function signatures.
- Default to no comments. Write one only when the *why* is non-obvious.
- Connectors are context managers — use `with`, not `try/finally`.
- Lowercase SQL keywords in templates and examples.
