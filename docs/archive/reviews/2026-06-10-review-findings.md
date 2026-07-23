# Archived review findings — 2026-06-10

> **Historical record.** All code findings shipped. L35 remains as the
> post-publication clean-room check in [the active plan](../../../PLAN.md).
> The distribution decisions below were later superseded by the 0.2.0 PyPI
> release plan.

Full findings from the 2026-06-10 multi-agent review (core, connectors/SQL security, CLI layer, workflow engine + agent docs, docs-vs-code accuracy).

Decisions already made (2026-06-10):
- **H5 (skill install path):** keep `skills/querido` as the generic default — qdo's skill install is agent-agnostic, not Claude Code-specific. Fix is an output note telling the user to copy/symlink the files into wherever their agent reads skills (e.g. `.claude/skills/` for Claude Code).
- **Install story:** wheels from GitHub Releases are the canonical install path everywhere. No PyPI assumptions in docs. PyPI release is a deferred PLAN.md item.

---

## High — fix before dogfooding

- [x] **H1. DuckDB mixed-case table names break catalog lookups end-to-end.** `src/querido/connectors/duckdb.py:101-126` (also `get_table_comment`:128, `get_view_definition`:140, `get_row_count`:151). Docstring claims DuckDB folds unquoted identifiers to lowercase — false; DuckDB preserves case and resolves case-insensitively. Verified: `get_columns('MyTable')` → `[]`, `get_row_count('MyTable')` → 0. Since `resolve_table` returns the canonical catalog name, profile/context/template silently fail on any table with an uppercase letter. Fix: match case-insensitively in SQL (`lower(table_name) = lower($table_name)`) in all four catalog queries; keep the lowercase cache key; fix the docstring.
- [x] **H2. `--allow-write` guard bypassed by CTE-prefixed writes.** `src/querido/core/sql_safety.py:26-34`. `any_statement_is_destructive` checks only the first keyword per statement; `with x as (select 1) delete from t` executes without `--allow-write` (verified live). Fix: when a statement starts with `with`, scan past the CTE list to the first top-level DML keyword.
- [x] **H3. `-f jsonl` is a hallucinated format flag in shipped agent docs.** `integrations/skills/SKILL.md:344`, `integrations/continue/qdo.md:276`. Verified: fails with `BadParameter` (valid set: rich, markdown, json, csv, html, yaml, agent). Ships verbatim into every `qdo agent install`. Fix: replace with `qdo export -e jsonl` or `-f json`. Re-run the eval after.
- [x] **H4. Workflow step `id` is never bound into the runtime context, but spec/lint/docs all say it is.** `src/querido/core/workflow/runner.py:390-398` only binds `capture:`; `spec.py:128-131` and `WORKFLOW_AUTHORING.md:73-74` claim id works; `lint.py:305-306` adds bare ids to `defined` so `${some_id.x}` lints clean. Silent failure mode: unresolved refs in `when:` mean "skip". Fix (smaller change): stop adding capture-less ids to `defined` in lint, fix spec.py + WORKFLOW_AUTHORING.md wording.
- [x] **H5. `qdo agent install skill` gives no guidance on where the skill must live.** `src/querido/cli/agent.py:32`. Default stays `skills/querido` (generic, agent-agnostic — decided). Fix: after install, print a note that the user must copy/symlink the directory into their agent's skill discovery path (e.g. `.claude/skills/querido` for Claude Code), or pass `--path` directly.
- [x] **H6. `get_sample_values` crashes instead of falling back (SQLite `template --format yaml`).** `src/querido/core/semantic.py:65-73, 84-93`. Batched query puts `limit` on each branch of a `union all` — invalid SQLite (verified). The fallback `except (ValueError, LookupError, OSError, RuntimeError)` catches neither `ConnectorError` nor raw driver errors, so the per-column fallback is dead code. Fix: wrap each branch in parens (`select * from (select ... limit n)`) and add `ConnectorError` to the except tuple (also at `_fetch_per_column`, line 123).
- [x] **H7. Global `-f` argv hoist collides with `qdo agent install --force/-f`.** `src/querido/cli/agent.py:151` + `src/querido/cli/argv_hoist.py:52`. `qdo agent install -f skill` becomes `--format skill` → error; `-f` before another flag consumes it as the format value. Fix: drop the `-f` short alias on `--force` (other commands deliberately use `-F`).

## Medium

- [x] **M1. `values` reports wrong `total_rows` / wrong stats for all-NULL columns.** `src/querido/core/values.py:68-93`. Window fns evaluate after `where value is not null`, so `sum(count) over()` counts non-null rows only (verified: 3-row table w/ one NULL → `total_rows: 2`). All-NULL column hits the empty-rows fallback which reports `null_count: 0` — backwards. Fix: compute total via `null_count + sum(count) over()` or scalar subquery; empty fallback derives `null_count = total_rows`.
- [x] **M2. `profile` overwrites true `row_count` with sample size when sampling.** `src/querido/core/profile.py:114-117` (similar at `context.py:219`). Verified: `sample=2` on 3-row table → `row_count: 2, sampled: true`, contradicting the sampling note. Fix: only adopt `stats[0]["total_rows"]` when `not sampled`.
- [x] **M3. `qdo assert` exit-code contract broken.** `src/querido/cli/assert_cmd.py:40` promises 0=pass, 1=fail, 2=SQL error, but `friendly_errors` (`_errors.py:113`) always exits 1. CI can't distinguish assertion-fail from broken query. Fix: catch DB errors in assert_cmd and `raise typer.Exit(2)`.
- [x] **M4. `pivot` rewrites `count(*)` to `count(<first group col>)`.** `src/querido/cli/pivot.py:131-137`. `count(col)` excludes NULLs → wrong counts when group column has NULLs. Fix: pass `*` through to `build_pivot_query`.
- [x] **M5. SQLite connector silently mutates the user's database.** `src/querido/connectors/sqlite.py:20-33`. `pragma journal_mode = WAL` is a persistent file change + sidecar files; default `sqlite3.connect` creates an empty DB for missing paths (named connections bypass the exists-check). Fix: open read-only via URI (`file:...?mode=ro`); drop the journal_mode pragma. Pair with write-mode handling for `query --allow-write`.
- [x] **M6. `-f agent` crashes on non-string dict keys where `-f json` succeeds.** `src/querido/output/envelope.py:159-171` + `toon.py:236-239`. `_normalize_for_structured` doesn't normalize keys; `_encode_key` raises `TypeError` on int keys; YAML fallback only catches `ToonUnsupportedShape`. Fix: coerce keys with `str(k)` during normalization.
- [x] **M7. Column-set keys break for dotted table names.** `src/querido/config.py:78-79, 122-126` (+ `bundle.py:263-267`). `_set_key` joins with `.` but table names may contain dots; `key.split(".", 2)` misparses, silently dropping/misattributing sets. Fix: store structured TOML fields (`connection`/`table`/`set`) instead of a dot-joined key.
- [x] **M8. `metadata init`/`refresh` emit nothing on stdout under `-f json`; bypass shared pipeline.** `src/querido/cli/metadata.py:41-65, 196-222` (same json-silence for `snowflake semantic -o`, `snowflake.py:63-70`). No `resolve_table`, no suggestions, success printed to stderr only. Fix: use `table_command`, emit a small envelope (`path`, `created`).
- [x] **M9. `config test` / `column-set show` / `column-set delete` break the structured-error contract.** `src/querido/cli/config.py:332-334, 431, 457`. Catch `Exception`, print Rich text, exit 1 — no parseable payload under `QDO_FORMAT=json`. Fix: route through `friendly_errors` / `emit_envelope`.
- [x] **M10. Mistyped connection name → `FILE_NOT_FOUND` instead of `CONNECTION_NOT_FOUND`; hint suggests invalid command.** `src/querido/config.py:174-180`, `_errors.py:342`. Hint says `qdo config add <name> --type <type> --path <path>` but `add` takes `--name`. Fix: raise a connection-specific error mapped to `CONNECTION_NOT_FOUND`; correct the hint.
- [x] **M11. Report HTML counts `<description>` placeholders as documented.** `src/querido/output/report_html.py:96-115`. Inflates "N/N columns documented"; can render literal placeholders. Fix: reuse the `startswith("<")` filter (`metadata._unwrap_field`) like `catalog.py:164` / `console.py:458`.
- [x] **M12. No `expanduser()` on sqlite/duckdb/parquet paths.** `src/querido/connectors/sqlite.py:22`, `duckdb.py:28,40`, `config.py:resolve_connection`. `path = "~/data.db"` in connections.toml fails opaquely (Snowflake `private_key_path` does get expanded). Fix: expand once in `resolve_connection`/`factory` for `path` and `parquet_path`.
- [x] **M13. Snowflake `get_table_row_counts` missing empty-context guard.** `src/querido/connectors/snowflake.py:333-347`. Empty `_database` builds `from .information_schema.tables` → confusing driver error. Fix: same `ValueError` guard as `get_tables` (snowflake.py:242-252).
- [x] **M14. Workflow recursion unguarded.** `src/querido/core/workflow/runner.py`. `run: qdo workflow run <itself>` lints clean and recurses unboundedly with `step_timeout: 0`. Fix: `QDO_WORKFLOW_DEPTH` env in `_session_env`, refuse past a small limit.
- [x] **M15. `qdo_min_version` documented as enforced but never checked at run time.** `WORKFLOW_AUTHORING.md:39` vs `runner.py` (lint only validates format). Fix: enforce in `run_workflow`, or soften the doc.
- [x] **M16. WORKFLOW_AUTHORING.md claims `-f` on `workflow run` propagates via env — false.** `WORKFLOW_AUTHORING.md:89` vs `runner.py:179-186` (`_session_env` sets only `QDO_SESSION`). Fix: export `QDO_FORMAT` from the resolved format, or fix the doc.
- [x] **M17. `diff --target` skips case-insensitive table resolution.** `src/querido/cli/diff.py:704-719` calls `get_columns` raw while the `--since` path uses `resolve_table` (diff.py:687). Fix: `resolve_table` both sides in all branches.
- [x] **M18. `session note` rewrites the append-only log non-atomically.** `src/querido/cli/session.py:153-156`. Opens `steps.jsonl` with `"w"`; interrupt mid-write corrupts the session. Fix: temp file + `os.replace`.
- [x] **M19. Install docs inconsistent: cli-reference implies PyPI.** `docs/cli-reference.md:12-17` says `uv pip install querido`; README says GitHub Releases wheels. Decision: GitHub wheels everywhere. Fix cli-reference (and any other PyPI-shaped instructions). PyPI itself → deferred PLAN.md item.

## Low

### Core / output

- [x] **L1. `QDO_SESSION=..` escapes the sessions dir.** `src/querido/core/session.py:172`. Rejects `/\:` but not `..`. Fix: restrict to `[A-Za-z0-9._-]+` minus dot-only names.
- [x] **L2. `run_query` executes destructive SQL even when `allow_write=False`.** `src/querido/core/query.py:36-41`. CLI gates upstream, but the core function is an unguarded footgun. Fix: raise inside `run_query` when `is_write and not allow_write`.
- [x] **L3. Quoting whole table name breaks schema-qualified names.** `src/querido/core/values.py:69-72`, `semantic.py:86-88`. `from "{table}"` turns `schema.table` into one identifier. Fix: quote per-segment via a shared qualifier helper.
- [x] **L4. `written_at` tie-break compares session names against ISO timestamps lexicographically.** `src/querido/core/bundle.py:164-170, 687-690`, `metadata_write.py:84-89`. Fix: always store the ISO timestamp; session name separately.
- [x] **L5. Uppercase SQL stragglers (house style is lowercase).** `src/querido/cache.py:182` (`WHERE`), `core/next_steps.py:1012-1014` (`SELECT/FROM/WHERE/LIMIT` in agent-facing suggestions), `core/pivot.py:63` (`AS`). Fix: lowercase them.
- [x] **L6. `metadata refresh` comment says placeholders are updated; code only fills missing keys.** `src/querido/core/metadata.py:723-726`. Fix code or comment.
- [x] **L7. `estimate` complexity scoring misses CTE-heavy SQL.** `src/querido/core/estimate.py:149-158`. `" with "` padded-substring match never fires for queries starting with `with` or using newlines/parens. Fix: tokenize.
- [x] **L8. `bundle import` reports `applied: true` when every action was a skip.** `src/querido/core/bundle.py:487-498`. Fix: gate on at least one `"write"` action.
- [x] **L9. Direct `d["key"]` indexing pervasive (house style is `.get()`).** `src/querido/cache.py`, `core/dist.py:65-66`, `output/formats.py`, etc. Fix: consistency pass.
- [x] **L10. Dead `qdo search` output code remains.** `src/querido/output/console.py::print_search`, `output/formats.py::format_search`, dispatch-table entries. Fix: delete.

### Connectors

- [x] **L11. Snowflake `_active_cursor` race under concurrency.** `src/querido/connectors/snowflake.py:132-150, 370-377`. Single shared slot; with parallel queries `cancel()` hits at most one arbitrary cursor. Fix: lock-guarded set of active cursors; cancel iterates.
- [x] **L12. `wrap_driver_error` misclassifies by substring.** `src/querido/connectors/base.py:96-107`. `"does not exist"` → `TableNotFoundError` with the whole message as `.table`; any message containing `"password"` → `AuthenticationError`. Fix: anchor per-dialect patterns; pass known table name from call site.
- [x] **L13. Snowflake `sample_source` bypasses `_resolve_table`; `sample system` invalid on views.** `src/querido/connectors/snowflake.py:356-368`. Fix: route through `_resolve_table`; fall back to `sample row` or document the view limitation.
- [x] **L14. Identifier allowlist rejects legitimate quoted names (spaces, hyphens, `$`).** `src/querido/connectors/base.py:4`. One such column aborts the whole profile. Decide: keep validate-don't-escape (document), or skip invalid columns with a warning.
- [x] **L15. SQLite `pragma table_info({table})` vs quoted usage disagree on dotted names.** `src/querido/connectors/sqlite.py:62` vs `:98`. Fix: quote consistently or reject dots for SQLite.
- [x] **L16. DuckDB creates a new file when the named-connection path doesn't exist.** `src/querido/connectors/duckdb.py:24-25`. Fix: raise instead of creating.

### CLI

- [x] **L17. `dispatch_output` docstring claims import-time check; reality is runtime `KeyError` → `UNKNOWN_ERROR`.** `src/querido/cli/_pipeline.py:206-209`. Fix: catch `KeyError`, emit clear internal-error message.
- [x] **L18. Dead code: `get_debug()` has no callers.** `src/querido/cli/_context.py:26-28`. Fix: delete.
- [x] **L19. `--show-sql` can display SQL that differs from what runs.** `src/querido/cli/inspect.py:32-34`, `profile.py:111-113`. Fix: render from the actual executed SQL.
- [x] **L20. `qdo --show-sql` with no subcommand silently exits 0.** `src/querido/cli/main.py:307`. Fix: check `ctx.invoked_subcommand` in the callback.
- [x] **L21. `-t` means `--type` in `config add` and `--tables` in `bundle export`, `--table` elsewhere.** `config.py:35`, `bundle.py:42`. Fix: document as deliberate or harmonize.
- [x] **L22. `_bad_parameter_code` is an 80-line string-prefix matcher; rewording silently degrades codes.** `src/querido/cli/_errors.py:211-296`. Fix: `CodedBadParameter(typer.BadParameter)` carrying the code explicitly.
- [x] **L23. `workflow run` lint failure raises bare `RuntimeError` → `UNKNOWN_ERROR`.** `src/querido/cli/workflow.py:218-221`. Fix: structured `WORKFLOW_LINT_FAILED` code.
- [x] **L24. Duplication to factor.** `export.py:146-164` vs `207-225` and `query.py:111-124` vs `166-174` (run_cmd reconstruction); `query.py:75-90` / `export.py:104-119` (source_meta + cross-connection warning); the `--connection/--table/--db-type` option triple hand-copied in ~20 modules though `_options.py` defines shared ones (help-text drift already started). Fix: shared helpers; adopt `_options.py` everywhere.

### Workflow / agent docs

- [x] **L25. Quoted `${ref}` inside `when:` silently compares false.** `src/querido/core/workflow/expr.py:84-98`. `"${x}" == "active"` becomes a literal placeholder string. Fix: detect `"${` inside `when` and warn at lint; document "never quote refs in when:".
- [x] **L26. Omitted optional inputs interpolate as the string `"None"`.** `src/querido/core/workflow/runner.py:125`. Fix: raise a clear error when a resolved `run:` value is `None`.
- [x] **L27. `qdo agent install` writes files one at a time; mid-list conflict leaves a partial install.** `src/querido/cli/agent.py:164-172`. Fix: pre-check all destinations before writing any.
- [x] **L28. WORKFLOW_AUTHORING.md:225 claims schema validation that doesn't exist; `timeout: true` passes the `isinstance(int)` check.** Fix wording; exclude bools from the int check.

### Docs

- [x] **L29. README has no `qdo workflow` section; bundles under-documented.** Add an "Automate and share" section: `workflow run/spec/lint/from-session`, `bundle export/inspect/import/diff` (note import is dry-run by default).
- [x] **L30. Tutorial CLI help says "15 lessons"; tutorial has 10.** `src/querido/cli/tutorial.py:35-36,52` (`--lesson` max=15). Fix code.
- [x] **L31. `view-def -v VIEW` documented but doesn't exist.** `docs/cli-reference.md:92`. Fix: `--view`.
- [x] **L32. Undocumented commands/flags.** `qdo overview`, `catalog functions`, `workflow spec/show`, `session note`, `bundle import/inspect/diff` (cli-ref lists only export), `metadata edit` + `agent show` (missing from cli-ref tables), `sql insert`/`sql udf`, `catalog --live/--schema/--enrich`. Fix: add to README/cli-reference as appropriate.
- [x] **L33. ARCHITECTURE.md drift.** Duplicate "### 6" section numbering (lines 351/394); scripts/ listing omits `benchmark_agent_format.py`, `eval_skill_files_codex.py`, `generate_tui_screenshots.py`, `init-test-data.sh`; docs/ listing omits `examples/`, `_config.yml`, `_layouts/`, `research/`; §7 sessions prose omits `note`/`replay`; cli-reference labeled "auto-generated" but hand-drifted (regenerate from `qdo overview` or drop the label).
- [x] **L34. Sessions introduced via `QDO_SESSION` env var before sessions are explained.** README. Fix: one early sentence ("set `QDO_SESSION` or run `qdo session start` to record steps").
- [ ] **L35. Clean-room install verification.** Re-verify the install end-to-end from an empty environment — now against PyPI (`uv tool install querido`) after the v0.2.0 publish. Partially done: the v0.1.0 GitHub Release shipped with assets on 2026-04-28, release.yml smoke-tests the wheel on every tag, and the CHANGELOG fold/bump landed as 0.2.0 (2026-07-06). Remaining: one manual clean-room `uv tool install querido` + `qdo tutorial explore` pass once 0.2.0 is live on PyPI.
