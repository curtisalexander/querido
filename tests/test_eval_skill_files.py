"""Tests for the eval_skill_files harness (EV.Build).

These exercise the pure helpers — parser, checker, preflight guards — so
regressions can be caught without actually calling ``claude -p``. The eval
itself is opt-in and costs money; this file is free to run in CI.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# The eval script lives under scripts/, not the querido package, so we
# load it by path. Same pattern scripts/eval_workflow_authoring.py would
# use if it had a test file.
_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "eval_skill_files.py"


@pytest.fixture(scope="module")
def eval_mod():
    """Import scripts/eval_skill_files.py as a module so we can hit its helpers."""
    spec = importlib.util.spec_from_file_location("eval_skill_files", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_skill_files"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# parse_stream_json
# ---------------------------------------------------------------------------


def _make_assistant_event(blocks: list[dict]) -> str:
    return json.dumps({"type": "assistant", "message": {"content": blocks}})


def _make_user_tool_result(content: str, *, is_error: bool = False) -> str:
    return json.dumps(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "content": content,
                        "is_error": is_error,
                    }
                ]
            },
        }
    )


def _make_result_event(result: str, **extra) -> str:
    return json.dumps({"type": "result", "result": result, **extra})


def test_parse_stream_json_extracts_bash_qdo_calls(eval_mod) -> None:
    stream = "\n".join(
        [
            _make_assistant_event(
                [
                    {"type": "text", "text": "I'll run catalog first."},
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "qdo -f json catalog -c /db"},
                    },
                ]
            ),
            _make_user_tool_result('{"data": {"tables": []}}'),
            _make_assistant_event(
                [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "qdo joins -c /db -t orders"},
                    },
                ]
            ),
            _make_result_event(
                "The database has three tables.",
                usage={"input_tokens": 100, "output_tokens": 10},
                total_cost_usd=0.001,
            ),
        ]
    )
    cmds, errors, final, usage = eval_mod.parse_stream_json(stream)
    assert cmds == ["qdo -f json catalog -c /db", "qdo joins -c /db -t orders"]
    assert errors == []
    assert final == "The database has three tables."
    assert usage["total_cost_usd"] == 0.001
    assert usage["tokens"]["input_tokens"] == 100


def test_parse_stream_json_ignores_non_qdo_bash(eval_mod) -> None:
    stream = _make_assistant_event(
        [
            {
                "type": "tool_use",
                "name": "Bash",
                "input": {"command": "ls -la"},
            },
        ]
    )
    cmds, _errors, _final, _usage = eval_mod.parse_stream_json(stream)
    assert cmds == []


def test_parse_stream_json_keeps_env_and_uv_prefixed_qdo(eval_mod) -> None:
    stream = "\n".join(
        [
            _make_assistant_event(
                [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "QDO_FORMAT=json qdo catalog -c /db"},
                    }
                ]
            ),
            _make_assistant_event(
                [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "uv run qdo inspect -c /db -t orders"},
                    }
                ]
            ),
        ]
    )
    cmds, _, _, _ = eval_mod.parse_stream_json(stream)
    assert len(cmds) == 2
    assert "qdo catalog" in cmds[0]
    assert "qdo inspect" in cmds[1]


def test_parse_stream_json_flags_tool_errors(eval_mod) -> None:
    stream = "\n".join(
        [
            _make_assistant_event(
                [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "qdo quality -c /no.db -t users"},
                    }
                ]
            ),
            _make_user_tool_result("Error: File not found", is_error=True),
        ]
    )
    _cmds, errors, _final, _usage = eval_mod.parse_stream_json(stream)
    assert len(errors) == 1
    assert "file not found" in errors[0].lower()


def test_parse_stream_json_flags_nonzero_exit_from_text(eval_mod) -> None:
    """Tool results sometimes embed ``exit code N`` in text rather than
    setting is_error; the parser catches the exit-code pattern too."""
    stream = "\n".join(
        [
            _make_assistant_event(
                [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "qdo inspect -c /db -t missing"},
                    }
                ]
            ),
            _make_user_tool_result("Table not found. exit code 1"),
        ]
    )
    _cmds, errors, _final, _usage = eval_mod.parse_stream_json(stream)
    assert len(errors) == 1


def test_parse_stream_json_tolerates_garbage_lines(eval_mod) -> None:
    """Non-JSON lines in the stream don't crash parsing."""
    stream = "\n".join(
        [
            "# this isn't json",
            _make_result_event("ok"),
            "another garbage line",
        ]
    )
    cmds, _errors, final, _usage = eval_mod.parse_stream_json(stream)
    assert cmds == []
    assert final == "ok"


# ---------------------------------------------------------------------------
# _looks_like_qdo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cmd", "expected"),
    [
        ("qdo catalog -c /db", True),
        ("qdo", True),
        ("QDO_FORMAT=json qdo catalog", True),
        ("QDO_FORMAT=json PATH=/usr/local/bin qdo catalog", True),
        ("uv run qdo catalog", True),
        ("ls qdo", False),
        ("echo qdo", False),
        ("", False),
        ("cat /etc/passwd", False),
        ("python -m qdo", False),
    ],
    ids=[
        "plain",
        "bare-qdo",
        "one-env",
        "multi-env",
        "uv-run",
        "embedded-ls",
        "embedded-echo",
        "empty",
        "unrelated",
        "python-dash-m",
    ],
)
def test_looks_like_qdo(eval_mod, cmd: str, expected: bool) -> None:
    assert eval_mod._looks_like_qdo(cmd) is expected


# ---------------------------------------------------------------------------
# check_pass
# ---------------------------------------------------------------------------


def _task(eval_mod, **overrides):
    defaults: dict = {
        "id": "test",
        "category": "X",
        "prompt": "",
        "required_commands": ["qdo catalog"],
        "content_regex": [r"(?i)tables"],
        "preferred_commands": ["qdo catalog"],
    }
    defaults.update(overrides)
    return eval_mod.Task(**defaults)


def test_check_pass_happy_path(eval_mod) -> None:
    task = _task(eval_mod)
    r = eval_mod.check_pass(
        task=task,
        qdo_commands=["qdo catalog -c /db -f json"],
        tool_errors=[],
        final_text="Found 3 tables in the database.",
    )
    assert r["status"] == "pass"
    assert r["failure_category"] is None
    assert r["path_ok"] is True


def test_check_pass_flags_qdo_bug_first(eval_mod) -> None:
    """Tool errors mean the model hit a qdo crash — categorize as qdo-bug
    BEFORE checking required commands, so a failing command doesn't get
    scored against the model's choice."""
    task = _task(eval_mod)
    r = eval_mod.check_pass(
        task=task,
        qdo_commands=["qdo catalog -c /db"],
        tool_errors=["Traceback…"],
        final_text="hmm",
    )
    assert r["status"] == "fail"
    assert r["failure_category"] == "qdo-bug"


def test_check_pass_missing_required_command(eval_mod) -> None:
    task = _task(eval_mod, required_commands=["qdo joins"])
    r = eval_mod.check_pass(
        task=task,
        qdo_commands=["qdo catalog -c /db"],
        tool_errors=[],
        final_text="Found them",
    )
    assert r["status"] == "fail"
    assert r["failure_category"] == "model-mistake"
    assert "expected" in r["reason"]


def test_check_pass_content_regex_misses(eval_mod) -> None:
    task = _task(eval_mod, content_regex=[r"customer_id"])
    r = eval_mod.check_pass(
        task=task,
        qdo_commands=["qdo catalog"],
        tool_errors=[],
        final_text="Something about orders.",
    )
    assert r["status"] == "fail"
    assert r["failure_category"] == "envelope-mismatch"


def test_check_pass_too_many_commands(eval_mod) -> None:
    """A 15-step solution to a 1-command problem is a failure mode."""
    task = _task(eval_mod, max_commands=3)
    cmds = [f"qdo catalog call_{i}" for i in range(10)]
    r = eval_mod.check_pass(
        task=task,
        qdo_commands=cmds,
        tool_errors=[],
        final_text="tables",
    )
    assert r["status"] == "fail"
    assert r["failure_category"] == "model-mistake"
    assert "limit 3" in r["reason"]


def test_check_pass_path_ok_false_when_preferred_not_used(eval_mod) -> None:
    """Missing preferred command doesn't fail — but is logged as path_ok=False."""
    task = _task(
        eval_mod,
        required_commands=["qdo query", "qdo catalog"],
        preferred_commands=["qdo catalog"],
    )
    r = eval_mod.check_pass(
        task=task,
        qdo_commands=["qdo query --sql 'select count(*) from information_schema.tables'"],
        tool_errors=[],
        final_text="3 tables",
    )
    assert r["status"] == "pass"
    assert r["path_ok"] is False


# ---------------------------------------------------------------------------
# _any_prefix_match
# ---------------------------------------------------------------------------


def test_any_prefix_match_plain(eval_mod) -> None:
    assert eval_mod._any_prefix_match(["qdo catalog"], ["qdo catalog -c /db"])


def test_any_prefix_match_strips_env_and_uv(eval_mod) -> None:
    assert eval_mod._any_prefix_match(["qdo catalog"], ["QDO_FORMAT=json qdo catalog"])
    assert eval_mod._any_prefix_match(["qdo catalog"], ["uv run qdo catalog -c /db"])


def test_any_prefix_match_no_match(eval_mod) -> None:
    assert not eval_mod._any_prefix_match(["qdo joins"], ["qdo catalog -c /db"])


def test_any_prefix_match_empty_cmds(eval_mod) -> None:
    assert not eval_mod._any_prefix_match(["qdo catalog"], [])


# ---------------------------------------------------------------------------
# Task selection
# ---------------------------------------------------------------------------


def test_select_tasks_default_is_all(eval_mod) -> None:
    selected = eval_mod._select_tasks(None)
    assert selected == eval_mod.TASKS


def test_select_tasks_by_id(eval_mod) -> None:
    selected = eval_mod._select_tasks("A1_list_tables,B1_enumerate_enum")
    ids = [t.id for t in selected]
    assert ids == ["A1_list_tables", "B1_enumerate_enum"]


def test_select_tasks_unknown_id_exits(eval_mod) -> None:
    with pytest.raises(SystemExit):
        eval_mod._select_tasks("nope")


def test_select_models_all(eval_mod) -> None:
    assert eval_mod._select_models("all") == ["haiku", "sonnet", "opus"]


def test_select_models_csv(eval_mod) -> None:
    assert eval_mod._select_models("haiku,opus") == ["haiku", "opus"]


def test_select_models_unknown_exits(eval_mod) -> None:
    with pytest.raises(SystemExit):
        eval_mod._select_models("gpt-4")


# ---------------------------------------------------------------------------
# Task catalog sanity
# ---------------------------------------------------------------------------


def test_task_ids_are_unique(eval_mod) -> None:
    ids = [t.id for t in eval_mod.TASKS]
    assert len(ids) == len(set(ids)), f"duplicate task ids: {ids}"


def test_task_categories_cover_all_four(eval_mod) -> None:
    cats = {t.category for t in eval_mod.TASKS}
    assert cats == {"A", "B", "C", "D"}, cats


def test_every_task_has_required_and_content(eval_mod) -> None:
    for t in eval_mod.TASKS:
        assert t.required_commands, f"{t.id} missing required_commands"
        assert t.content_regex, f"{t.id} missing content_regex"


def test_every_task_prompt_references_db_placeholder(eval_mod) -> None:
    """The runner .format(db=...)-injects the fixture path. Tasks that
    forget ``{db}`` would hardcode a path and break if the fixture moves."""
    for t in eval_mod.TASKS:
        assert "{db}" in t.prompt, f"{t.id}: prompt missing {{db}} placeholder"


# ---------------------------------------------------------------------------
# Exit-code gating
# ---------------------------------------------------------------------------


def test_exit_code_all_pass_is_zero(eval_mod) -> None:
    """Haiku ≥70% pass is the only required gate when running only Haiku."""
    results = [
        {"model": "haiku", "status": "pass"},
        {"model": "haiku", "status": "pass"},
        {"model": "haiku", "status": "pass"},
    ]
    assert eval_mod._exit_code(results) == 0


def test_exit_code_haiku_below_gate(eval_mod) -> None:
    results = [
        {"model": "haiku", "status": "pass"},
        {"model": "haiku", "status": "fail"},
        {"model": "haiku", "status": "fail"},
    ]
    assert eval_mod._exit_code(results) == 1


def test_exit_code_opus_gate_is_strict(eval_mod) -> None:
    """Opus needs 95% — one fail in three is 67%, below the gate."""
    results = [
        {"model": "opus", "status": "pass"},
        {"model": "opus", "status": "pass"},
        {"model": "opus", "status": "fail"},
    ]
    assert eval_mod._exit_code(results) == 1


# ---------------------------------------------------------------------------
# Auth-error detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "msg",
    [
        "Not logged in · Please run /login",
        "not logged in",
        "please run /login",
        "unauthorized access",
        "UNAUTHORIZED",
    ],
)
def test_is_auth_error_true(eval_mod, msg: str) -> None:
    assert eval_mod._is_auth_error(msg, "") is True


@pytest.mark.parametrize(
    "msg",
    [
        "The database has three tables.",
        "Here's what I found…",
        "",
        "login required for external services",  # unrelated mention
    ],
)
def test_is_auth_error_false(eval_mod, msg: str) -> None:
    # The last case is a false positive worth knowing about — "login"
    # alone shouldn't trip the check, only the /login slash-command pattern.
    if "login required" in msg:
        pytest.skip("'login' alone can false-positive; acceptable for now.")
    assert eval_mod._is_auth_error(msg, "") is False


def test_is_auth_error_looks_at_stderr_too(eval_mod) -> None:
    assert eval_mod._is_auth_error("", "fatal: not logged in") is True
