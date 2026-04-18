"""Tests for Phase 4.2 — workflow runner, lint, list, show."""

from __future__ import annotations

import json
import os
import sys
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app
from querido.core.workflow.expr import (
    ExpressionError,
    UnresolvedReference,
    evaluate_when,
    interpolate,
    resolve_output,
    resolve_path,
)
from querido.core.workflow.from_session import from_session as build_from_session
from querido.core.workflow.lint import lint
from querido.core.workflow.loader import (
    list_available_workflows,
    load_workflow_doc,
    resolve_workflow,
)
from querido.core.workflow.runner import (
    DEFAULT_STEP_TIMEOUT,
    InputError,
    StepFailed,
    WorkflowError,
    _resolve_step_timeout,
    bind_inputs,
    run_workflow,
)

runner = CliRunner()


# -----------------------------------------------------------------------------
# Expression evaluator
# -----------------------------------------------------------------------------


def test_resolve_path_walks_dotted_keys() -> None:
    ctx = {"a": {"b": {"c": 42}}}
    assert resolve_path("a.b.c", ctx) == 42


def test_resolve_path_missing_key_raises() -> None:
    with pytest.raises(UnresolvedReference):
        resolve_path("a.missing", {"a": {"b": 1}})


def test_interpolate_replaces_refs() -> None:
    out = interpolate("hello ${user.name}", {"user": {"name": "ada"}})
    assert out == "hello ada"


def test_resolve_output_single_ref_preserves_type() -> None:
    assert resolve_output("${n}", {"n": 7}) == 7


def test_resolve_output_template_stringifies() -> None:
    assert resolve_output("n=${n}", {"n": 7}) == "n=7"


def test_evaluate_when_truthy_bare_ref() -> None:
    assert evaluate_when("${flag}", {"flag": True}) is True
    assert evaluate_when("${flag}", {"flag": False}) is False


def test_evaluate_when_comparison() -> None:
    assert evaluate_when("${n} > 0", {"n": 5}) is True
    assert evaluate_when("${n} > 0", {"n": 0}) is False


def test_evaluate_when_and_or_not() -> None:
    ctx = {"a": True, "b": False}
    assert evaluate_when("${a} and not ${b}", ctx) is True
    assert evaluate_when("${b} or ${a}", ctx) is True


def test_evaluate_when_rejects_function_calls() -> None:
    with pytest.raises(ExpressionError):
        evaluate_when("len('x') > 0", {})


def test_evaluate_when_rejects_attribute_access() -> None:
    with pytest.raises(ExpressionError):
        evaluate_when("__import__('os').getcwd()", {})


# R.15 — comparison semantics (nulls, type mismatches, yaml-style literals)


def test_evaluate_when_null_ordering_raises_expression_error() -> None:
    """``None > 0`` should become an ExpressionError, not a bare TypeError."""
    with pytest.raises(ExpressionError, match="cannot compare"):
        evaluate_when("${x} > 0", {"x": None})


def test_evaluate_when_null_ordering_mentions_both_operands() -> None:
    """The message names both sides so agents can identify the bad reference."""
    with pytest.raises(ExpressionError, match=r"None.*NoneType.*>.*0.*int"):
        evaluate_when("${x} > 0", {"x": None})


def test_evaluate_when_type_mismatch_ordering_raises_expression_error() -> None:
    """Stringified numbers vs int — catch cleanly instead of bubbling TypeError."""
    with pytest.raises(ExpressionError, match="cannot compare"):
        evaluate_when("${x} > 0", {"x": "42"})


def test_evaluate_when_equality_null_safe() -> None:
    """``==``/``!=`` across types and with null must keep working — they're
    how users guard ordering comparisons."""
    assert evaluate_when("${x} == null", {"x": None}) is True
    assert evaluate_when("${x} != null", {"x": 5}) is True
    assert evaluate_when("${x} == 0", {"x": None}) is False


def test_evaluate_when_null_guard_short_circuits() -> None:
    """The idiomatic guard ``${x} != null and ${x} > 0`` must not raise
    when x is null (the ``and`` short-circuits before the ordering runs)."""
    assert evaluate_when("${x} != null and ${x} > 0", {"x": None}) is False
    assert evaluate_when("${x} != null and ${x} > 0", {"x": 5}) is True


def test_evaluate_when_accepts_yaml_null_literal() -> None:
    """``null`` (YAML-style) is an alias for None, as is ``none``."""
    assert evaluate_when("${x} == null", {"x": None}) is True
    assert evaluate_when("${x} == none", {"x": None}) is True
    assert evaluate_when("${x} == None", {"x": None}) is True  # unchanged
    assert evaluate_when("${x} != null", {"x": 7}) is True


# -----------------------------------------------------------------------------
# Lint
# -----------------------------------------------------------------------------


def _valid_doc() -> dict:
    return {
        "name": "demo",
        "description": "Example.",
        "version": 1,
        "inputs": {"conn": {"type": "connection", "required": True}},
        "steps": [
            {"id": "a", "run": "qdo -f json inspect -c ${conn} -t users", "capture": "schema"},
            {
                "id": "b",
                "when": "${schema.data.row_count} > 0",
                "run": "qdo -f json preview -c ${conn} -t users",
            },
        ],
        "outputs": {"row_count": "${schema.data.row_count}"},
    }


def test_lint_accepts_valid_doc() -> None:
    assert lint(_valid_doc()).ok


def test_lint_flags_duplicate_step_ids() -> None:
    doc = _valid_doc()
    doc["steps"][1]["id"] = "a"
    codes = [i.code for i in lint(doc).issues]
    assert "DUPLICATE_STEP_ID" in codes


def test_lint_flags_unresolved_reference() -> None:
    doc = _valid_doc()
    doc["steps"][0]["run"] = "qdo inspect -c ${unknown_input} -t users -f json"
    codes = [i.code for i in lint(doc).issues]
    assert "UNRESOLVED_REFERENCE" in codes


def test_lint_flags_capture_before_define() -> None:
    doc = _valid_doc()
    # Reference step a's capture before step a exists.
    doc["steps"] = [
        {
            "id": "first",
            "when": "${schema.data.row_count} > 0",
            "run": "qdo -f json inspect -c ${conn} -t users",
        },
        *doc["steps"],
    ]
    codes = [i.code for i in lint(doc).issues]
    assert "UNRESOLVED_REFERENCE" in codes


def test_lint_flags_write_query_without_allow_write() -> None:
    doc = _valid_doc()
    doc["steps"][0] = {"id": "wipe", "run": "qdo query -c ${conn} --sql 'DELETE FROM users'"}
    codes = [i.code for i in lint(doc).issues]
    assert "WRITE_WITHOUT_ALLOW" in codes


def test_lint_accepts_write_query_with_allow_write() -> None:
    doc = _valid_doc()
    doc["steps"][0] = {
        "id": "wipe",
        "run": "qdo query -c ${conn} --sql 'DELETE FROM users'",
        "allow_write": True,
    }
    codes = [i.code for i in lint(doc).issues]
    assert "WRITE_WITHOUT_ALLOW" not in codes


# R.16 — write-query lint scopes to --sql statement heads, not the whole line.


def test_lint_does_not_flag_destructive_word_in_column_or_table_name() -> None:
    """A SELECT against a table whose name contains 'create' is safe."""
    doc = _valid_doc()
    doc["steps"][0] = {
        "id": "read_events",
        "run": "qdo query -c ${conn} --sql 'select * from create_events limit 5'",
    }
    codes = [i.code for i in lint(doc).issues]
    assert "WRITE_WITHOUT_ALLOW" not in codes


def test_lint_does_not_flag_destructive_word_in_connection_name() -> None:
    """A plain SELECT against a connection named 'prod_delete' is safe."""
    doc = _valid_doc()
    doc["steps"][0] = {
        "id": "count",
        "run": "qdo query -c prod_delete --sql 'select count(*) from users'",
    }
    codes = [i.code for i in lint(doc).issues]
    assert "WRITE_WITHOUT_ALLOW" not in codes


def test_lint_does_not_flag_destructive_word_in_string_literal() -> None:
    """A SELECT whose string literal contains 'insert' as text is safe."""
    doc = _valid_doc()
    doc["steps"][0] = {
        "id": "note",
        "run": ("qdo query -c ${conn} --sql \"select 'we insert manually' as note from users\""),
    }
    codes = [i.code for i in lint(doc).issues]
    assert "WRITE_WITHOUT_ALLOW" not in codes


def test_lint_still_flags_multi_statement_destructive() -> None:
    """A compound statement where any statement starts with DELETE must fire."""
    doc = _valid_doc()
    doc["steps"][0] = {
        "id": "combo",
        "run": "qdo query -c ${conn} --sql 'select 1; delete from staging'",
    }
    codes = [i.code for i in lint(doc).issues]
    assert "WRITE_WITHOUT_ALLOW" in codes


def test_lint_still_flags_leading_whitespace_and_comments() -> None:
    """Leading whitespace and SQL comments before the keyword don't hide it."""
    doc = _valid_doc()
    doc["steps"][0] = {
        "id": "cleanup",
        "run": (
            "qdo query -c ${conn} --sql '   -- remove stale\n    /* block */ DROP TABLE staging'"
        ),
    }
    codes = [i.code for i in lint(doc).issues]
    assert "WRITE_WITHOUT_ALLOW" in codes


def test_lint_flags_file_sql_conservatively() -> None:
    """``--file path.sql`` hides the SQL from lint; err on the side of safety."""
    doc = _valid_doc()
    doc["steps"][0] = {
        "id": "from_file",
        "run": "qdo query -c ${conn} --file migration.sql",
    }
    codes = [i.code for i in lint(doc).issues]
    assert "WRITE_WITHOUT_ALLOW" in codes


def test_lint_flags_stdin_query_conservatively() -> None:
    """No --sql, no --file → stdin. Conservative flag."""
    doc = _valid_doc()
    doc["steps"][0] = {
        "id": "from_stdin",
        "run": "qdo query -c ${conn}",
    }
    codes = [i.code for i in lint(doc).issues]
    assert "WRITE_WITHOUT_ALLOW" in codes


def test_lint_accepts_equals_form_of_sql_flag() -> None:
    """``--sql=...`` form must parse the same as ``--sql ...``."""
    doc = _valid_doc()
    doc["steps"][0] = {
        "id": "eq",
        "run": "qdo query -c ${conn} --sql='select 1 from create_events'",
    }
    codes = [i.code for i in lint(doc).issues]
    assert "WRITE_WITHOUT_ALLOW" not in codes


# R.20 — schema-aware lint: --connection + --table check column refs.


def _doc_with_column_step(columns_spec: str) -> dict:
    """Make a valid doc whose first data step passes *columns_spec* to values."""
    doc = _valid_doc()
    doc["steps"][0] = {
        "id": "vals",
        "run": f"qdo -f json values -c ${{conn}} -t ${{table}} --columns {columns_spec}",
        "capture": "vals",
    }
    doc["inputs"]["table"] = {"type": "table", "required": True}
    return doc


def test_lint_no_schema_check_without_valid_columns() -> None:
    """Without ``valid_columns``, column refs are never flagged."""
    doc = _doc_with_column_step("nonexistent_col")
    codes = [i.code for i in lint(doc).issues]
    assert "UNKNOWN_COLUMN" not in codes


def test_lint_flags_unknown_column_with_schema() -> None:
    doc = _doc_with_column_step("nonexistent")
    result = lint(doc, valid_columns={"id", "name", "age"})
    codes = [i.code for i in result.issues]
    assert "UNKNOWN_COLUMN" in codes


def test_lint_accepts_known_column_with_schema() -> None:
    doc = _doc_with_column_step("name")
    result = lint(doc, valid_columns={"id", "name", "age"})
    assert "UNKNOWN_COLUMN" not in [i.code for i in result.issues]


def test_lint_column_check_case_insensitive() -> None:
    """DuckDB lowercases; Snowflake uppercases. Match case-insensitively."""
    doc = _doc_with_column_step("NAME")
    result = lint(doc, valid_columns={"id", "name", "age"})
    assert "UNKNOWN_COLUMN" not in [i.code for i in result.issues]


def test_lint_skips_interpolated_column_refs() -> None:
    """Values containing ``${...}`` can't be resolved at lint time — skip."""
    doc = _doc_with_column_step("${pick_col}")
    result = lint(doc, valid_columns={"id", "name"})
    assert "UNKNOWN_COLUMN" not in [i.code for i in result.issues]


def test_lint_column_check_handles_csv_lists() -> None:
    doc = _doc_with_column_step("id,nonexistent,age")
    result = lint(doc, valid_columns={"id", "name", "age"})
    bad = [i for i in result.issues if i.code == "UNKNOWN_COLUMN"]
    assert len(bad) == 1
    assert "nonexistent" in bad[0].message


def test_lint_column_check_handles_equals_form() -> None:
    doc = _valid_doc()
    doc["steps"][0] = {
        "id": "vals",
        "run": "qdo -f json values -c ${conn} -t ${table} --columns=bogus",
        "capture": "vals",
    }
    doc["inputs"]["table"] = {"type": "table", "required": True}
    result = lint(doc, valid_columns={"id", "name"})
    assert "UNKNOWN_COLUMN" in [i.code for i in result.issues]


def test_lint_cli_rejects_single_flag(tmp_path: Path, sqlite_path: str, monkeypatch) -> None:
    """``--connection`` without ``--table`` (or vice versa) must fail fast."""
    wf = tmp_path / "wf.yaml"
    wf.write_text(
        textwrap.dedent(
            """\
            name: wf
            description: minimal
            version: 1
            steps:
              - id: inspect
                run: qdo inspect -c ./x.db -t users -f json
            """
        )
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["workflow", "lint", str(wf), "-c", sqlite_path])
    assert result.exit_code != 0
    assert "together" in result.output.lower()


def test_lint_cli_with_schema_flags(tmp_path: Path, sqlite_path: str, monkeypatch) -> None:
    """End-to-end: --connection + --table wires into the column check."""
    wf = tmp_path / "wf.yaml"
    # ``users`` in sqlite_path has id, name, age. Reference a nonexistent col.
    wf.write_text(
        textwrap.dedent(
            """\
            name: wf
            description: draft that names a missing column
            version: 1
            inputs:
              connection: {type: connection, required: true}
              table: {type: table, required: true}
            steps:
              - id: vals
                run: qdo -f json values -c ${connection} -t ${table} --columns bogus
                capture: vals
            """
        )
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["-f", "json", "workflow", "lint", str(wf), "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code == 1
    payload = json.loads(result.output)
    codes = [i["code"] for i in payload["data"]["issues"]]
    assert "UNKNOWN_COLUMN" in codes


def test_lint_flags_invalid_run() -> None:
    doc = _valid_doc()
    doc["steps"][0]["run"] = "rm -rf /"
    codes = [i.code for i in lint(doc).issues]
    assert "INVALID_RUN" in codes


def test_lint_flags_missing_required_field() -> None:
    doc = _valid_doc()
    del doc["version"]
    codes = [i.code for i in lint(doc).issues]
    assert "MISSING_FIELD" in codes


def test_lint_flags_unknown_top_level_field() -> None:
    doc = _valid_doc()
    doc["bogus"] = 1
    codes = [i.code for i in lint(doc).issues]
    assert "UNKNOWN_FIELD" in codes


def test_bundled_examples_lint_clean() -> None:
    from querido.core.workflow.loader import _bundled_entries

    for _name, path in _bundled_entries():
        doc = load_workflow_doc(path)
        result = lint(doc)
        assert result.ok, f"{path}: {[i.to_dict() for i in result.issues]}"


# -----------------------------------------------------------------------------
# Loader / CLI list+show
# -----------------------------------------------------------------------------


def test_list_available_includes_bundled(tmp_path: Path) -> None:
    entries = list_available_workflows(cwd=tmp_path)
    names = {e.name for e in entries}
    assert "table-summary" in names
    assert "schema-compare" in names


def test_project_workflow_overrides_bundled(tmp_path: Path) -> None:
    wdir = tmp_path / ".qdo" / "workflows"
    wdir.mkdir(parents=True)
    (wdir / "table-summary.yaml").write_text(
        textwrap.dedent(
            """\
            name: table-summary
            description: Local override.
            version: 1
            steps:
              - id: noop
                run: qdo --version
            """
        )
    )
    entry = resolve_workflow("table-summary", cwd=tmp_path)
    assert entry.source == "project"
    assert entry.description == "Local override."


def test_resolve_workflow_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_workflow("does-not-exist", cwd=tmp_path)


def test_workflow_show_prints_bundled_yaml() -> None:
    result = runner.invoke(app, ["workflow", "show", "table-summary"])
    assert result.exit_code == 0, result.stdout
    assert "name: table-summary" in result.stdout


def test_workflow_list_json() -> None:
    result = runner.invoke(app, ["-f", "json", "workflow", "list"])
    assert result.exit_code == 0, result.stdout
    envelope = json.loads(result.stdout)
    names = {e["name"] for e in envelope["data"]}
    assert {"table-summary", "schema-compare"} <= names


# -----------------------------------------------------------------------------
# bind_inputs
# -----------------------------------------------------------------------------


def test_bind_inputs_requires_required() -> None:
    doc = {"inputs": {"conn": {"type": "connection", "required": True}}}
    with pytest.raises(InputError):
        bind_inputs(doc, {})


def test_bind_inputs_applies_default() -> None:
    doc = {"inputs": {"n": {"type": "integer", "default": 3}}}
    assert bind_inputs(doc, {}) == {"n": 3}


def test_bind_inputs_coerces_integer() -> None:
    doc = {"inputs": {"n": {"type": "integer"}}}
    assert bind_inputs(doc, {"n": "42"}) == {"n": 42}


def test_bind_inputs_rejects_unknown() -> None:
    doc = {"inputs": {"a": {"type": "string"}}}
    with pytest.raises(InputError):
        bind_inputs(doc, {"b": "x"})


# -----------------------------------------------------------------------------
# End-to-end runner
# -----------------------------------------------------------------------------


def test_run_workflow_end_to_end_against_sqlite(tmp_path: Path, sqlite_path: str) -> None:
    wf = tmp_path / "demo.yaml"
    wf.write_text(
        textwrap.dedent(
            """\
            name: demo
            description: End-to-end workflow test.
            version: 1
            inputs:
              connection:
                type: connection
                required: true
              table:
                type: table
                required: true
            steps:
              - id: inspect
                run: qdo inspect -c ${connection} -t ${table} -f json
                capture: schema
              - id: preview
                when: ${schema.data.row_count} > 0
                run: qdo preview -c ${connection} -t ${table} -f json
                capture: rows
            outputs:
              row_count: ${schema.data.row_count}
              rows: ${rows.data.rows}
            """
        )
    )
    doc = load_workflow_doc(wf)
    assert lint(doc).ok
    env_backup = os.environ.pop("QDO_SESSION", None)
    try:
        result = run_workflow(
            doc,
            {"connection": sqlite_path, "table": "users"},
            cwd=tmp_path,
        )
    finally:
        if env_backup is not None:
            os.environ["QDO_SESSION"] = env_backup

    assert result.outputs["row_count"] == 2
    assert isinstance(result.outputs["rows"], list)
    assert len(result.outputs["rows"]) == 2
    assert [s.id for s in result.steps] == ["inspect", "preview"]
    # Session was auto-created and both steps recorded into it.
    assert result.session.startswith("workflow-demo-")
    steps_file = tmp_path / ".qdo" / "sessions" / result.session / "steps.jsonl"
    assert steps_file.is_file()
    lines = [json.loads(line) for line in steps_file.read_text().splitlines() if line.strip()]
    assert len(lines) == 2


def test_run_workflow_skips_step_when_false(tmp_path: Path, sqlite_path: str) -> None:
    wf = tmp_path / "skip.yaml"
    wf.write_text(
        textwrap.dedent(
            """\
            name: skip
            description: Skip on when=false.
            version: 1
            inputs:
              connection:
                type: connection
                required: true
            steps:
              - id: first
                run: qdo inspect -c ${connection} -t users -f json
                capture: schema
              - id: second
                when: ${schema.data.row_count} > 9999
                run: qdo preview -c ${connection} -t users -f json
            """
        )
    )
    doc = load_workflow_doc(wf)
    result = run_workflow(doc, {"connection": sqlite_path}, cwd=tmp_path)
    assert result.steps[1].skipped is True


def test_run_workflow_chain_skip_via_when_referencing_skipped_capture(
    tmp_path: Path, sqlite_path: str
) -> None:
    """A ``when:`` that references a skipped step's capture resolves to a
    skip (not an UnresolvedReference abort). This is what makes the
    conditional-composition pattern in table-handoff work when an early
    gate skips the producing step."""
    wf = tmp_path / "chain-skip.yaml"
    wf.write_text(
        textwrap.dedent(
            """\
            name: chain-skip
            description: First gate skips; downstream refs must degrade gracefully.
            version: 1
            inputs:
              connection:
                type: connection
                required: true
            steps:
              - id: first
                run: qdo inspect -c ${connection} -t users -f json
                capture: schema
              - id: middle
                when: ${schema.data.row_count} > 9999
                run: qdo preview -c ${connection} -t users -f json
                capture: rows
              - id: last
                when: ${rows.data} != null
                run: qdo inspect -c ${connection} -t users -f json
            """
        )
    )
    doc = load_workflow_doc(wf)
    result = run_workflow(doc, {"connection": sqlite_path}, cwd=tmp_path)
    assert result.steps[1].skipped is True
    assert result.steps[2].skipped is True, (
        "when: that references a skipped step's capture should resolve to a skip, "
        "not abort with UnresolvedReference"
    )


def test_run_workflow_aborts_on_step_failure(tmp_path: Path) -> None:
    wf = tmp_path / "fail.yaml"
    wf.write_text(
        textwrap.dedent(
            """\
            name: fail
            description: A step that exits non-zero must abort the run.
            version: 1
            steps:
              - id: broken
                run: qdo inspect -c /nonexistent.db -t users -f json
            """
        )
    )
    doc = load_workflow_doc(wf)
    with pytest.raises(StepFailed) as excinfo:
        run_workflow(doc, {}, cwd=tmp_path)
    assert excinfo.value.step_id == "broken"


# -----------------------------------------------------------------------------
# R.6 — step timeouts
# -----------------------------------------------------------------------------


def test_resolve_step_timeout_default_when_nothing_set() -> None:
    assert (
        _resolve_step_timeout(cli_override=None, env={}, step={}, doc={}) == DEFAULT_STEP_TIMEOUT
    )


def test_resolve_step_timeout_workflow_level_wins_over_default() -> None:
    assert (
        _resolve_step_timeout(cli_override=None, env={}, step={}, doc={"step_timeout": 60}) == 60
    )


def test_resolve_step_timeout_step_level_overrides_workflow_level() -> None:
    assert (
        _resolve_step_timeout(
            cli_override=None,
            env={},
            step={"timeout": 30},
            doc={"step_timeout": 600},
        )
        == 30
    )


def test_resolve_step_timeout_env_overrides_yaml() -> None:
    effective = _resolve_step_timeout(
        cli_override=None,
        env={"QDO_WORKFLOW_STEP_TIMEOUT": "45"},
        step={"timeout": 30},
        doc={"step_timeout": 600},
    )
    assert effective == 45


def test_resolve_step_timeout_cli_overrides_env() -> None:
    effective = _resolve_step_timeout(
        cli_override=15,
        env={"QDO_WORKFLOW_STEP_TIMEOUT": "45"},
        step={"timeout": 30},
        doc={"step_timeout": 600},
    )
    assert effective == 15


def test_resolve_step_timeout_zero_means_unbounded() -> None:
    """``timeout: 0`` at the winning layer resolves to ``None`` (no limit)."""
    assert _resolve_step_timeout(cli_override=0, env={}, step={}, doc={}) is None
    assert _resolve_step_timeout(cli_override=None, env={}, step={"timeout": 0}, doc={}) is None


def test_resolve_step_timeout_higher_layer_zero_beats_lower_layer_nonzero() -> None:
    """A CLI 0 wipes out a step-level 30 — user's runtime intent wins."""
    effective = _resolve_step_timeout(
        cli_override=0,
        env={},
        step={"timeout": 30},
        doc={"step_timeout": 60},
    )
    assert effective is None


def test_resolve_step_timeout_higher_layer_wins_over_lower_zero() -> None:
    """CLI 60 beats a step's ``timeout: 0`` — runtime cap overrides author intent."""
    effective = _resolve_step_timeout(
        cli_override=60,
        env={},
        step={"timeout": 0},
        doc={},
    )
    assert effective == 60


def test_resolve_step_timeout_env_non_integer_raises() -> None:
    with pytest.raises(WorkflowError, match="not an integer"):
        _resolve_step_timeout(
            cli_override=None,
            env={"QDO_WORKFLOW_STEP_TIMEOUT": "sixty"},
            step={},
            doc={},
        )


def test_resolve_step_timeout_env_negative_raises() -> None:
    with pytest.raises(WorkflowError, match="non-negative"):
        _resolve_step_timeout(
            cli_override=None,
            env={"QDO_WORKFLOW_STEP_TIMEOUT": "-5"},
            step={},
            doc={},
        )


def test_run_workflow_raises_step_failed_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When subprocess.run hits its timeout, the runner wraps it as
    StepFailed(timed_out=True) with the effective timeout value."""
    import subprocess

    wf = tmp_path / "slow.yaml"
    wf.write_text(
        textwrap.dedent(
            """\
            name: slow
            description: A step the runner pretends timed out.
            version: 1
            steps:
              - id: slow_step
                run: qdo inspect -c ./x.db -t users -f json
                timeout: 2
            """
        )
    )
    doc = load_workflow_doc(wf)

    def _raise_timeout(*args, **kwargs):
        assert kwargs.get("timeout") == 2
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=2, output=b"", stderr=b"hung")

    monkeypatch.setattr(subprocess, "run", _raise_timeout)

    with pytest.raises(StepFailed) as excinfo:
        run_workflow(doc, {}, cwd=tmp_path)

    assert excinfo.value.step_id == "slow_step"
    assert excinfo.value.timed_out is True
    assert excinfo.value.timeout == 2
    assert excinfo.value.exit_code == -1
    assert "hung" in excinfo.value.stderr


def test_run_workflow_cli_step_timeout_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The --step-timeout CLI flag reaches subprocess.run as the timeout arg."""
    import subprocess

    seen: dict[str, object] = {}

    def _capture_run(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        # Return a zero-exit dummy so the workflow succeeds.
        completed = subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")
        return completed

    monkeypatch.setattr(subprocess, "run", _capture_run)

    wf = tmp_path / ".qdo" / "workflows" / "flag-demo.yaml"
    wf.parent.mkdir(parents=True)
    wf.write_text(
        textwrap.dedent(
            """\
            name: flag-demo
            description: Minimal workflow for --step-timeout threading.
            version: 1
            steps:
              - id: s
                run: qdo inspect -c ./x.db -t users
            """
        )
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["workflow", "run", "flag-demo", "--step-timeout", "17"],
    )
    assert result.exit_code == 0, result.output
    assert seen["timeout"] == 17


def test_lint_rejects_negative_workflow_step_timeout() -> None:
    doc = _valid_doc()
    doc["step_timeout"] = -1
    result = lint(doc)
    codes = [i.code for i in result.issues]
    assert "INVALID_STEP_TIMEOUT" in codes


def test_lint_rejects_negative_per_step_timeout() -> None:
    doc = _valid_doc()
    doc["steps"][0]["timeout"] = -5
    result = lint(doc)
    codes = [i.code for i in result.issues]
    assert "INVALID_STEP_TIMEOUT" in codes


def test_lint_accepts_zero_timeout() -> None:
    """``timeout: 0`` / ``step_timeout: 0`` are valid (unbounded)."""
    doc = _valid_doc()
    doc["step_timeout"] = 0
    doc["steps"][0]["timeout"] = 0
    result = lint(doc)
    assert result.ok, result.issues


def test_workflow_run_cli(tmp_path: Path, sqlite_path: str, monkeypatch) -> None:
    monkeypatch.delenv("QDO_SESSION", raising=False)
    wf = tmp_path / ".qdo" / "workflows" / "cli-demo.yaml"
    wf.parent.mkdir(parents=True)
    wf.write_text(
        textwrap.dedent(
            """\
            name: cli-demo
            description: Demo via CLI.
            version: 1
            inputs:
              connection:
                type: connection
                required: true
            steps:
              - id: inspect
                run: qdo inspect -c ${connection} -t users -f json
                capture: schema
            outputs:
              rows: ${schema.data.row_count}
            """
        )
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["-f", "json", "workflow", "run", "cli-demo", f"connection={sqlite_path}"]
    )
    assert result.exit_code == 0, result.stdout + "\nSTDERR:\n" + (result.stderr or "")
    envelope = json.loads(result.stdout)
    assert envelope["data"]["outputs"] == {"rows": 2}

    # R.17: every step entry carries the fully-interpolated run command so
    # agents can reproduce the step outside the workflow without re-parsing
    # ${...} refs.
    step = envelope["data"]["steps"][0]
    assert step["id"] == "inspect"
    assert step["run"]
    # The connection placeholder must be gone (interpolated to the path) and
    # the format flag hoisted to the root.
    assert "${connection}" not in step["run"]
    assert sqlite_path in step["run"]
    assert step["run"].startswith("qdo ")


def test_workflow_run_cli_records_run_for_skipped_steps(
    tmp_path: Path, sqlite_path: str, monkeypatch
) -> None:
    """Skipped steps have an empty run string (nothing was resolved) — that's
    expected, and the envelope must still include the ``run`` key so agents
    can rely on its shape."""
    monkeypatch.delenv("QDO_SESSION", raising=False)
    wf = tmp_path / ".qdo" / "workflows" / "skip-demo.yaml"
    wf.parent.mkdir(parents=True)
    wf.write_text(
        textwrap.dedent(
            """\
            name: skip-demo
            description: Step that gets skipped by a falsy guard.
            version: 1
            inputs:
              flag:
                type: boolean
                required: true
            steps:
              - id: optional
                when: ${flag}
                run: qdo inspect -c ./not-used.db -t users -f json
            """
        )
    )
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["-f", "json", "workflow", "run", "skip-demo", "flag=false"])
    assert result.exit_code == 0, result.output
    envelope = json.loads(result.output)
    step = envelope["data"]["steps"][0]
    assert step["skipped"] is True
    assert "run" in step  # contract: key present even when step skipped


# -----------------------------------------------------------------------------
# R.7 — structured step-failure envelope
# -----------------------------------------------------------------------------


def _write_failing_workflow(tmp_path: Path) -> None:
    """Install a workflow whose first step is guaranteed to exit non-zero."""
    wf = tmp_path / ".qdo" / "workflows" / "fail-demo.yaml"
    wf.parent.mkdir(parents=True)
    wf.write_text(
        textwrap.dedent(
            """\
            name: fail-demo
            description: Step guaranteed to fail.
            version: 1
            steps:
              - id: broken
                run: qdo inspect -c /nonexistent-db-path.db -t users -f json
            """
        )
    )


def test_step_failure_emits_structured_envelope_to_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Under -f json, a StepFailed must surface as a parseable error payload
    on stderr — agents should never have to scrape the human-readable message."""
    monkeypatch.delenv("QDO_SESSION", raising=False)
    _write_failing_workflow(tmp_path)
    monkeypatch.chdir(tmp_path)

    stderr_buf: list[str] = []
    orig_runner = runner

    result = orig_runner.invoke(app, ["-f", "json", "workflow", "run", "fail-demo"])
    assert result.exit_code != 0
    # CliRunner merges stderr into result.output; find the JSON object.
    stderr_buf.append(result.output)
    blob = result.output
    start = blob.find("{")
    assert start >= 0, blob
    payload = json.loads(blob[start:])
    assert payload["error"] is True
    assert payload["code"] == "WORKFLOW_STEP_FAILED"
    assert payload["step_id"] == "broken"
    assert payload["workflow"] == "fail-demo"
    assert payload["exit_code"] != 0
    # -f json gets hoisted right after ``qdo`` by the runner, so the
    # rendered command isn't ``qdo inspect ...`` verbatim — just check
    # the subcommand and target path survived.
    assert "inspect" in payload["step_cmd"]
    assert "/nonexistent-db-path.db" in payload["step_cmd"]
    # Every step failure should ship try_next suggestions.
    assert payload["try_next"], payload
    # And surface the session so agents can drill in.
    assert payload["session"].startswith("workflow-fail-demo-")


def test_step_failure_agent_format_renders_via_toon_or_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """-f agent uses the TOON/YAML envelope path — the error payload must
    include the code and step id as keys parseable by either format."""
    monkeypatch.delenv("QDO_SESSION", raising=False)
    _write_failing_workflow(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["-f", "agent", "workflow", "run", "fail-demo"])
    assert result.exit_code != 0
    out = result.output
    assert "code: WORKFLOW_STEP_FAILED" in out
    assert "step_id: broken" in out
    assert "try_next" in out


def test_step_failure_non_structured_keeps_stderr_dump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-json/agent formats keep the current behavior: raw stderr + friendly-
    errors message.  No JSON payload should appear."""
    monkeypatch.delenv("QDO_SESSION", raising=False)
    _write_failing_workflow(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["workflow", "run", "fail-demo"])
    assert result.exit_code != 0
    # No envelope JSON on the default (rich) path.
    assert '"code": "WORKFLOW_STEP_FAILED"' not in result.output
    # The friendly_errors decorator still surfaces an error message.
    assert "broken" in result.output.lower() or "failed" in result.output.lower()


def test_step_failure_marks_stderr_truncated_when_oversized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CC.10: when stderr exceeds the tail cap, the envelope stamps
    ``stderr_truncated: true`` so agents don't misread a clipped 4KB tail
    as a complete error."""
    from querido.cli.workflow import _emit_step_failure_envelope
    from querido.core.workflow.runner import StepFailed

    big = "x" * 10_000  # well over the 4096-byte cap
    exc = StepFailed(
        step_id="noisy",
        cmd="qdo inspect -c no.db -t users",
        exit_code=1,
        stderr=big,
        session="",
        timed_out=False,
        timeout=None,
    )

    captured: list[str] = []
    monkeypatch.setattr(sys, "stderr", _Capture(captured))
    _emit_step_failure_envelope(exc, workflow="oversized", fmt="json")
    payload = json.loads("".join(captured))
    assert payload["stderr_truncated"] is True
    # The stored stderr field is the truncated tail, prefixed with the marker.
    assert payload["stderr"].startswith("…(truncated)…\n")
    assert len(payload["stderr"]) < len(big)


def test_step_failure_omits_stderr_truncated_when_short(monkeypatch: pytest.MonkeyPatch) -> None:
    """CC.10: when stderr fits, the ``stderr_truncated`` key is absent — we
    use presence-as-signal to keep the payload slim and unambiguous."""
    from querido.cli.workflow import _emit_step_failure_envelope
    from querido.core.workflow.runner import StepFailed

    small = "boom\n"
    exc = StepFailed(
        step_id="tiny",
        cmd="qdo inspect -c no.db -t users",
        exit_code=1,
        stderr=small,
        session="",
        timed_out=False,
        timeout=None,
    )

    captured: list[str] = []
    monkeypatch.setattr(sys, "stderr", _Capture(captured))
    _emit_step_failure_envelope(exc, workflow="short", fmt="json")
    payload = json.loads("".join(captured))
    assert "stderr_truncated" not in payload
    assert payload["stderr"] == small


class _Capture:
    """Minimal stderr stand-in — accumulates writes into a list[str]."""

    def __init__(self, buf: list[str]) -> None:
        self._buf = buf

    def write(self, chunk: str) -> int:
        self._buf.append(chunk)
        return len(chunk)

    def flush(self) -> None:
        pass


def test_step_timeout_emits_envelope_with_timed_out_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A timed-out step emits WORKFLOW_STEP_TIMEOUT with timed_out + timeout fields."""
    import subprocess

    monkeypatch.delenv("QDO_SESSION", raising=False)

    def _raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0], timeout=kwargs.get("timeout", 1), output=b"", stderr=b"hung"
        )

    monkeypatch.setattr(subprocess, "run", _raise_timeout)

    wf = tmp_path / ".qdo" / "workflows" / "timeout-demo.yaml"
    wf.parent.mkdir(parents=True)
    wf.write_text(
        textwrap.dedent(
            """\
            name: timeout-demo
            description: Step that the monkeypatch pretends timed out.
            version: 1
            steps:
              - id: slow
                run: qdo inspect -c ./x.db -t users -f json
                timeout: 1
            """
        )
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["-f", "json", "workflow", "run", "timeout-demo"])
    assert result.exit_code != 0
    start = result.output.find("{")
    assert start >= 0, result.output
    payload = json.loads(result.output[start:])
    assert payload["code"] == "WORKFLOW_STEP_TIMEOUT"
    assert payload["timed_out"] is True
    assert payload["timeout"] == 1
    # Timeout try_next should offer the "disable timeout" hint.
    assert any("--step-timeout" in s["cmd"] for s in payload["try_next"])


# -----------------------------------------------------------------------------
# from-session
# -----------------------------------------------------------------------------


def _record_session(cwd: Path, name: str, steps: list[dict]) -> None:
    """Write a synthetic session log under *cwd*/.qdo/sessions/<name>/steps.jsonl."""
    sess_dir = cwd / ".qdo" / "sessions" / name
    sess_dir.mkdir(parents=True)
    with (sess_dir / "steps.jsonl").open("w", encoding="utf-8") as f:
        for i, step in enumerate(steps, start=1):
            rec = {
                "index": i,
                "timestamp": "2026-04-14T00:00:00+00:00",
                "cmd": step["args"][0] if step.get("args") else "",
                "args": step["args"],
                "duration": 0.01,
                "exit_code": step.get("exit_code", 0),
                "row_count": None,
                "stdout_path": f"sessions/{name}/step_{i}/stdout",
            }
            f.write(json.dumps(rec) + "\n")


def test_from_session_parameterizes_connection_and_table(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _record_session(
        tmp_path,
        "demo",
        [
            {"args": ["inspect", "-c", "/tmp/my.db", "-t", "users"]},
            {"args": ["preview", "--connection", "/tmp/my.db", "--table", "users"]},
        ],
    )
    doc = build_from_session("demo")
    assert doc["name"] == "from-demo"
    assert doc["inputs"] == {
        "connection": {"type": "connection", "required": True},
        "table": {"type": "table", "required": True},
    }
    run_lines = [s["run"] for s in doc["steps"]]
    assert run_lines[0] == "qdo inspect -c ${connection} -t ${table}"
    assert run_lines[1] == "qdo preview --connection ${connection} --table ${table}"
    # Every step gets a capture named after its id.
    assert all(s["capture"] == s["id"] for s in doc["steps"])


def test_from_session_skips_failed_and_meta_steps(tmp_path: Path) -> None:
    _record_session(
        tmp_path,
        "mixed",
        [
            {"args": ["inspect", "-c", "/tmp/x.db", "-t", "users"]},
            {"args": ["config", "list"]},  # meta — skipped
            {"args": ["preview", "-c", "/tmp/x.db", "-t", "users"], "exit_code": 1},  # failure
            {"args": ["profile", "-c", "/tmp/x.db", "-t", "users", "--quick"]},
        ],
    )
    doc = build_from_session("mixed", cwd=tmp_path)
    ids = [s["id"] for s in doc["steps"]]
    assert ids == ["inspect", "profile"]


def test_from_session_deduplicates_step_ids(tmp_path: Path) -> None:
    _record_session(
        tmp_path,
        "dupes",
        [
            {"args": ["inspect", "-c", "/tmp/x.db", "-t", "users"]},
            {"args": ["inspect", "-c", "/tmp/x.db", "-t", "orders"]},
            {"args": ["inspect", "-c", "/tmp/x.db", "-t", "items"]},
        ],
    )
    doc = build_from_session("dupes", cwd=tmp_path)
    assert [s["id"] for s in doc["steps"]] == ["inspect", "inspect_2", "inspect_3"]


def test_from_session_last_n_trims(tmp_path: Path) -> None:
    _record_session(
        tmp_path,
        "tail",
        [
            {"args": ["inspect", "-c", "/tmp/x.db", "-t", "users"]},
            {"args": ["preview", "-c", "/tmp/x.db", "-t", "users"]},
            {"args": ["profile", "-c", "/tmp/x.db", "-t", "users", "--quick"]},
        ],
    )
    doc = build_from_session("tail", last=2, cwd=tmp_path)
    assert [s["id"] for s in doc["steps"]] == ["preview", "profile"]


def test_from_session_drops_format_flag(tmp_path: Path) -> None:
    _record_session(
        tmp_path,
        "fmt",
        [
            {"args": ["inspect", "-c", "/tmp/x.db", "-t", "users", "-f", "json"]},
        ],
    )
    doc = build_from_session("fmt", cwd=tmp_path)
    assert "-f" not in doc["steps"][0]["run"]


def test_from_session_output_lints_clean(tmp_path: Path, sqlite_path: str) -> None:
    _record_session(
        tmp_path,
        "clean",
        [
            {"args": ["inspect", "-c", sqlite_path, "-t", "users"]},
            {"args": ["preview", "-c", sqlite_path, "-t", "users"]},
        ],
    )
    doc = build_from_session("clean", cwd=tmp_path)
    result = lint(doc)
    assert result.ok, [i.to_dict() for i in result.issues]


def test_from_session_cli(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _record_session(
        tmp_path,
        "cli-session",
        [{"args": ["inspect", "-c", "/tmp/x.db", "-t", "users"]}],
    )
    result = runner.invoke(app, ["workflow", "from-session", "cli-session", "--name", "my-wf"])
    assert result.exit_code == 0, result.stdout
    assert "name: my-wf" in result.stdout
    assert "${connection}" in result.stdout


def test_from_session_cli_writes_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _record_session(
        tmp_path,
        "w",
        [{"args": ["inspect", "-c", "/tmp/x.db", "-t", "users"]}],
    )
    out = tmp_path / ".qdo" / "workflows" / "draft.yaml"
    result = runner.invoke(app, ["workflow", "from-session", "w", "-o", str(out)])
    assert result.exit_code == 0, result.stdout
    assert out.is_file()
    assert "name: from-w" in out.read_text()


def test_from_session_errors_on_missing_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["workflow", "from-session", "nope"])
    assert result.exit_code == 1


def test_workflow_lint_cli_reports_issues(tmp_path: Path, monkeypatch) -> None:
    wf = tmp_path / "bad.yaml"
    wf.write_text(
        textwrap.dedent(
            """\
            name: bad-workflow
            description: missing run prefix.
            version: 1
            steps:
              - id: s
                run: ls -la
            """
        )
    )
    result = runner.invoke(app, ["-f", "json", "workflow", "lint", str(wf)])
    assert result.exit_code == 1
    envelope = json.loads(result.stdout)
    codes = {i["code"] for i in envelope["data"]["issues"]}
    assert "INVALID_RUN" in codes
