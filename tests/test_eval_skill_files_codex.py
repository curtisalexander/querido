"""Tests for the Codex-backed qdo skill-file eval harness."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "eval_skill_files_codex.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("eval_skill_files_codex", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["eval_skill_files_codex"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_parse_codex_json_extracts_qdo_commands() -> None:
    mod = _load_module()
    stream = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "abc"}),
            json.dumps(
                {
                    "type": "exec.command.started",
                    "command": "qdo -f json catalog -c /db",
                }
            ),
            json.dumps(
                {
                    "type": "exec.command.finished",
                    "payload": {"cmd": "qdo context -c /db -t orders"},
                }
            ),
        ]
    )
    cmds, errors, usage = mod.parse_codex_json(stream)
    assert cmds == ["qdo -f json catalog -c /db", "qdo context -c /db -t orders"]
    assert errors == []
    assert usage == {}


def test_parse_codex_json_extracts_shell_wrapped_qdo_commands() -> None:
    mod = _load_module()
    stream = json.dumps(
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": "/bin/zsh -lc 'qdo -f json catalog -c /db'",
            },
        }
    )
    cmds, errors, usage = mod.parse_codex_json(stream)
    assert cmds == ["qdo -f json catalog -c /db"]
    assert errors == []
    assert usage == {}


def test_parse_codex_json_flags_usage_error_text() -> None:
    mod = _load_module()
    stream = json.dumps(
        {
            "type": "exec.command.finished",
            "output": (
                "Usage: qdo catalog [OPTIONS]\n"
                "Try 'qdo catalog --help' for help.\n\n"
                "Error: No such option: -f"
            ),
        }
    )
    _cmds, errors, _usage = mod.parse_codex_json(stream)
    assert len(errors) == 1
    assert "No such option" in errors[0]


def test_transport_or_auth_error_detects_network_failure() -> None:
    mod = _load_module()
    cat = mod._transport_or_auth_error(
        '{"type":"error","message":"Reconnecting... failed to lookup address information"}',
        "",
        "",
    )
    assert cat == "transport-error"


def test_artifact_success_result_passes_metadata_init_timeout(tmp_path: Path) -> None:
    mod = _load_module()
    scratch = tmp_path / "scratch"
    metadata = scratch / ".qdo" / "metadata" / "test" / "orders.yaml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("table: orders\n", encoding="utf-8")

    task = next(t for t in mod.base.TASKS if t.id == "D2_init_metadata")
    result = mod._artifact_success_result(
        task=task,
        model="gpt-5.4",
        prompt="init metadata",
        scratch=scratch,
        qdo_commands=[],
        tool_errors=[],
        usage={},
        duration_sec=240.0,
        keep_artifacts=True,
    )

    assert result is not None
    assert result["status"] == "pass"
    assert result["failure_category"] is None
    assert result["reason"] == "expected artifact was created before codex timed out"
    assert result["qdo_commands"] == [
        f"qdo metadata init -c {mod.FIXTURE_DB} -t orders"
    ]
    assert "orders.yaml" in result["final_text_snippet"]


def test_artifact_success_result_returns_none_without_expected_artifact(tmp_path: Path) -> None:
    mod = _load_module()
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    task = next(t for t in mod.base.TASKS if t.id == "D2_init_metadata")
    result = mod._artifact_success_result(
        task=task,
        model="gpt-5.4",
        prompt="init metadata",
        scratch=scratch,
        qdo_commands=[],
        tool_errors=[],
        usage={},
        duration_sec=240.0,
        keep_artifacts=True,
    )

    assert result is None
