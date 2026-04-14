"""Tests for Phase 4.2 — workflow runner, lint, list, show."""

from __future__ import annotations

import json
import os
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
from querido.core.workflow.runner import InputError, bind_inputs, run_workflow

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


def test_run_workflow_aborts_on_step_failure(tmp_path: Path) -> None:
    from querido.core.workflow.runner import StepFailed

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
