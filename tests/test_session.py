"""Tests for Phase 1.2 session MVP."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from querido.cli.main import app
from querido.core import session

runner = CliRunner()


def _run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> Result:
    """Invoke the CLI with a temporary cwd and optional env overrides."""
    env_full = {**os.environ, **(env or {})}
    old_cwd = Path.cwd()
    try:
        os.chdir(cwd)
        return runner.invoke(app, args, env=env_full)
    finally:
        os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# core/session.py unit tests
# ---------------------------------------------------------------------------


def test_session_dir_rejects_invalid_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        session.session_dir("foo/bar", cwd=tmp_path)
    with pytest.raises(ValueError):
        session.session_dir("", cwd=tmp_path)


def test_list_sessions_empty(tmp_path: Path) -> None:
    assert session.list_sessions(cwd=tmp_path) == []


def test_next_step_index_counts_jsonl_lines(tmp_path: Path) -> None:
    dir_ = tmp_path / "s"
    dir_.mkdir()
    assert session.next_step_index(dir_) == 1
    (dir_ / "steps.jsonl").write_text('{"a":1}\n{"a":2}\n\n')
    assert session.next_step_index(dir_) == 3


def test_extract_row_count_from_envelope() -> None:
    payload = {"command": "preview", "data": [{"x": 1}, {"x": 2}], "meta": {}}
    assert session._extract_row_count(json.dumps(payload)) == 2

    payload = {"command": "ctx", "data": {}, "meta": {"row_count": 42}}
    assert session._extract_row_count(json.dumps(payload)) == 42

    assert session._extract_row_count("not json") is None
    assert session._extract_row_count("") is None


# ---------------------------------------------------------------------------
# end-to-end CLI capture tests
# ---------------------------------------------------------------------------


def test_qdo_session_captures_step(tmp_path: Path, sqlite_path: str) -> None:
    result = _run(
        [
            "-f",
            "json",
            "preview",
            "--connection",
            sqlite_path,
            "--table",
            "users",
            "--rows",
            "1",
        ],
        cwd=tmp_path,
        env={"QDO_SESSION": "test"},
    )
    assert result.exit_code == 0

    session_path = tmp_path / ".qdo" / "sessions" / "test"
    assert session_path.is_dir()

    steps_file = session_path / "steps.jsonl"
    assert steps_file.is_file()
    lines = [json.loads(line) for line in steps_file.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    record = lines[0]

    assert record["index"] == 1
    assert record["cmd"] == "preview"
    assert record["exit_code"] == 0
    assert record["duration"] >= 0
    assert record["row_count"] == 1
    assert "timestamp" in record

    stdout_file = session_path / "step_1" / "stdout"
    assert stdout_file.is_file()
    assert stdout_file.read_text().strip().startswith("{")


def test_qdo_session_records_multiple_steps(tmp_path: Path, sqlite_path: str) -> None:
    for _ in range(3):
        result = _run(
            ["inspect", "--connection", sqlite_path, "--table", "users"],
            cwd=tmp_path,
            env={"QDO_SESSION": "multi"},
        )
        assert result.exit_code == 0

    steps_file = tmp_path / ".qdo" / "sessions" / "multi" / "steps.jsonl"
    lines = [json.loads(line) for line in steps_file.read_text().splitlines() if line.strip()]
    assert len(lines) == 3
    assert [rec["index"] for rec in lines] == [1, 2, 3]

    for i in range(1, 4):
        assert (tmp_path / ".qdo" / "sessions" / "multi" / f"step_{i}" / "stdout").is_file()


def test_qdo_session_skips_session_subcommand(tmp_path: Path) -> None:
    result = _run(
        ["session", "list"],
        cwd=tmp_path,
        env={"QDO_SESSION": "meta"},
    )
    assert result.exit_code == 0
    # `session list` must not record itself into its own session.
    assert not (tmp_path / ".qdo" / "sessions" / "meta").exists()


def test_qdo_session_records_failures(tmp_path: Path, sqlite_path: str) -> None:
    result = _run(
        ["inspect", "--connection", sqlite_path, "--table", "no_such_table"],
        cwd=tmp_path,
        env={"QDO_SESSION": "failures"},
    )
    assert result.exit_code != 0

    steps_file = tmp_path / ".qdo" / "sessions" / "failures" / "steps.jsonl"
    assert steps_file.is_file()
    record = json.loads(steps_file.read_text().splitlines()[0])
    assert record["exit_code"] != 0


# ---------------------------------------------------------------------------
# `qdo session` subcommand tests
# ---------------------------------------------------------------------------


def test_session_start_creates_dir(tmp_path: Path) -> None:
    result = _run(["session", "start", "investigation"], cwd=tmp_path)
    assert result.exit_code == 0
    assert (tmp_path / ".qdo" / "sessions" / "investigation").is_dir()
    assert "investigation" in result.output


def test_session_start_rejects_invalid_name(tmp_path: Path) -> None:
    result = _run(["session", "start", "bad/name"], cwd=tmp_path)
    assert result.exit_code != 0


def test_session_start_suggests_name_when_omitted(tmp_path: Path) -> None:
    result = _run(["session", "start", "--yes"], cwd=tmp_path)
    assert result.exit_code == 0
    created = list((tmp_path / ".qdo" / "sessions").iterdir())
    assert len(created) == 1
    # Generated names have the shape adjective-noun-noun.
    assert created[0].name.count("-") == 2


def test_generate_session_name_format() -> None:
    name = session.generate_session_name()
    parts = name.split("-")
    assert len(parts) == 3
    assert all(p.isalpha() and p.islower() for p in parts)


def test_session_list_empty(tmp_path: Path) -> None:
    result = _run(["session", "list"], cwd=tmp_path)
    assert result.exit_code == 0
    assert "No sessions" in result.output


def test_session_list_shows_sessions(tmp_path: Path, sqlite_path: str) -> None:
    _run(
        ["inspect", "--connection", sqlite_path, "--table", "users"],
        cwd=tmp_path,
        env={"QDO_SESSION": "alpha"},
    )
    _run(
        ["inspect", "--connection", sqlite_path, "--table", "users"],
        cwd=tmp_path,
        env={"QDO_SESSION": "beta"},
    )
    result = _run(["session", "list"], cwd=tmp_path)
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output
    assert "1 step" in result.output


def test_session_list_json_uses_structured_envelope(tmp_path: Path, sqlite_path: str) -> None:
    _run(
        ["inspect", "--connection", sqlite_path, "--table", "users"],
        cwd=tmp_path,
        env={"QDO_SESSION": "alpha"},
    )
    result = _run(["-f", "json", "session", "list"], cwd=tmp_path)
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "session list"
    assert payload["data"]["sessions"] == [
        {
            "name": "alpha",
            "step_count": 1,
            "last_timestamp": payload["data"]["sessions"][0]["last_timestamp"],
        }
    ]


def test_session_show_prints_steps(tmp_path: Path, sqlite_path: str) -> None:
    for _ in range(2):
        _run(
            ["preview", "--connection", sqlite_path, "--table", "users"],
            cwd=tmp_path,
            env={"QDO_SESSION": "s1"},
        )
    result = _run(["session", "show", "s1"], cwd=tmp_path)
    assert result.exit_code == 0
    assert "s1" in result.output
    assert "[  1]" in result.output
    assert "[  2]" in result.output


def test_session_show_json_uses_structured_envelope(tmp_path: Path, sqlite_path: str) -> None:
    _run(
        ["preview", "--connection", sqlite_path, "--table", "users"],
        cwd=tmp_path,
        env={"QDO_SESSION": "s1"},
    )
    result = _run(["-f", "json", "session", "show", "s1"], cwd=tmp_path)
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "session show"
    assert payload["meta"]["session"] == "s1"
    assert payload["data"]["name"] == "s1"
    assert len(payload["data"]["steps"]) == 1


def test_session_show_missing(tmp_path: Path) -> None:
    result = _run(["session", "show", "nope"], cwd=tmp_path)
    assert result.exit_code != 0


def test_session_replay_reexecutes_successful_steps(tmp_path: Path, sqlite_path: str) -> None:
    _run(
        ["-f", "json", "preview", "--connection", sqlite_path, "--table", "users", "--rows", "1"],
        cwd=tmp_path,
        env={"QDO_SESSION": "source"},
    )
    _run(
        ["-f", "json", "query", "--connection", sqlite_path, "--sql", "select name from users"],
        cwd=tmp_path,
        env={"QDO_SESSION": "source"},
    )

    result = _run(["session", "replay", "source"], cwd=tmp_path)
    assert result.exit_code == 0, result.output
    assert "into session 'replay-source-" in result.output

    sessions = [
        name for name in session.list_sessions(cwd=tmp_path) if name.startswith("replay-source-")
    ]
    assert len(sessions) == 1
    replay_name = sessions[0]
    replay_steps = list(session.iter_steps(replay_name, cwd=tmp_path))
    assert len(replay_steps) == 2
    assert replay_steps[0]["args"] == [
        "preview",
        "--connection",
        sqlite_path,
        "--table",
        "users",
        "--rows",
        "1",
    ]
    assert replay_steps[1]["args"] == [
        "query",
        "--connection",
        sqlite_path,
        "--sql",
        "select name from users",
    ]


def test_session_replay_into_named_session(tmp_path: Path, sqlite_path: str) -> None:
    _run(
        ["inspect", "--connection", sqlite_path, "--table", "users"],
        cwd=tmp_path,
        env={"QDO_SESSION": "source"},
    )

    result = _run(["session", "replay", "source", "--into", "rerun"], cwd=tmp_path)
    assert result.exit_code == 0, result.output

    replay_steps = list(session.iter_steps("rerun", cwd=tmp_path))
    assert len(replay_steps) == 1
    assert replay_steps[0]["cmd"] == "inspect"


def test_session_replay_json_uses_structured_envelope(tmp_path: Path, sqlite_path: str) -> None:
    _run(
        ["preview", "--connection", sqlite_path, "--table", "users"],
        cwd=tmp_path,
        env={"QDO_SESSION": "source"},
    )

    result = _run(["-f", "json", "session", "replay", "source", "--into", "rerun"], cwd=tmp_path)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["command"] == "session replay"
    assert payload["meta"]["session"] == "source"
    assert payload["meta"]["replay_session"] == "rerun"
    assert payload["data"]["source_session"] == "source"
    assert payload["data"]["replay_session"] == "rerun"
    assert payload["data"]["step_count"] == 1
    assert any("qdo session show rerun" in step["cmd"] for step in payload["next_steps"])


def test_session_replay_stops_on_first_failure(tmp_path: Path, sqlite_path: str) -> None:
    _run(
        ["preview", "--connection", sqlite_path, "--table", "users"],
        cwd=tmp_path,
        env={"QDO_SESSION": "source"},
    )
    _run(
        ["query", "--connection", sqlite_path, "--sql", "select * from no_such_table"],
        cwd=tmp_path,
        env={"QDO_SESSION": "source"},
    )
    _run(
        ["inspect", "--connection", sqlite_path, "--table", "users"],
        cwd=tmp_path,
        env={"QDO_SESSION": "source"},
    )

    result = _run(["session", "replay", "source", "--into", "rerun"], cwd=tmp_path)
    assert result.exit_code == 0, result.output

    replay_steps = list(session.iter_steps("rerun", cwd=tmp_path))
    # Only successful source steps are replayable, so the failed query is skipped.
    assert len(replay_steps) == 2
    assert replay_steps[0]["cmd"] == "preview"
    assert replay_steps[1]["cmd"] == "inspect"


def test_session_replay_last_limits_replayed_steps(tmp_path: Path, sqlite_path: str) -> None:
    for rows in ("1", "2"):
        _run(
            ["preview", "--connection", sqlite_path, "--table", "users", "--rows", rows],
            cwd=tmp_path,
            env={"QDO_SESSION": "source"},
        )

    result = _run(["session", "replay", "source", "--into", "rerun", "--last", "1"], cwd=tmp_path)
    assert result.exit_code == 0, result.output

    replay_steps = list(session.iter_steps("rerun", cwd=tmp_path))
    assert len(replay_steps) == 1
    assert replay_steps[0]["args"][-1] == "2"
