import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def _seed_session_query_step(
    cwd: Path,
    *,
    name: str,
    index: int,
    sql: str,
    connection: str | None = None,
    command: str = "query",
    structured: bool = True,
) -> None:
    session_dir = cwd / ".qdo" / "sessions" / name
    step_dir = session_dir / f"step_{index}"
    step_dir.mkdir(parents=True, exist_ok=True)

    stdout_path = step_dir / "stdout"
    if structured:
        payload = {
            "command": command,
            "data": {"sql": sql, "rows": [], "columns": [], "row_count": 0, "limited": False},
            "next_steps": [],
            "meta": {"connection": connection} if connection else {},
        }
        stdout_path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        stdout_path.write_text("plain text output", encoding="utf-8")

    steps_path = session_dir / "steps.jsonl"
    record = {
        "index": index,
        "timestamp": "2026-04-22T00:00:00+00:00",
        "cmd": f"qdo {command}",
        "args": [command],
        "duration": 0.1,
        "exit_code": 0,
        "stdout_path": str(stdout_path.relative_to(cwd / ".qdo")),
    }
    with steps_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def test_query_inline_sql(sqlite_path: str):
    result = runner.invoke(app, ["query", "-c", sqlite_path, "--sql", "select * from users"])
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_query_inline_sql_duckdb(duckdb_path: str):
    result = runner.invoke(app, ["query", "-c", duckdb_path, "--sql", "select * from users"])
    assert result.exit_code == 0
    assert "Alice" in result.output


def test_query_from_file(sqlite_path: str, tmp_path: Path):
    sql_file = tmp_path / "test.sql"
    sql_file.write_text("select name from users where age > 26")
    result = runner.invoke(app, ["query", "-c", sqlite_path, "--file", str(sql_file)])
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" not in result.output


def test_query_from_stdin(sqlite_path: str):
    result = runner.invoke(
        app,
        ["query", "-c", sqlite_path],
        input="select name from users where id = 1",
    )
    assert result.exit_code == 0
    assert "Alice" in result.output


def test_query_sql_takes_priority_over_file(sqlite_path: str, tmp_path: Path):
    sql_file = tmp_path / "other.sql"
    sql_file.write_text("select name from users where id = 2")
    result = runner.invoke(
        app,
        [
            "query",
            "-c",
            sqlite_path,
            "--sql",
            "select name from users where id = 1",
            "--file",
            str(sql_file),
        ],
    )
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" not in result.output


def test_query_limit_flag(sqlite_path: str):
    result = runner.invoke(
        app, ["query", "-c", sqlite_path, "--sql", "select * from users", "--limit", "1"]
    )
    assert result.exit_code == 0
    assert "1" in result.output
    # Should only show 1 row
    assert "row(s) returned" in result.output


def test_query_limit_zero_no_limit(sqlite_path: str):
    result = runner.invoke(
        app, ["query", "-c", sqlite_path, "--sql", "select * from users", "--limit", "0"]
    )
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_query_empty_result(sqlite_path: str):
    result = runner.invoke(
        app,
        ["query", "-c", sqlite_path, "--sql", "select * from users where id = 999"],
    )
    assert result.exit_code == 0
    assert "no rows" in result.output.lower()


def test_query_sql_error(sqlite_path: str):
    result = runner.invoke(
        app,
        ["query", "-c", sqlite_path, "--sql", "select * from nonexistent_table"],
    )
    assert result.exit_code == 1


def test_query_no_sql_provided(sqlite_path: str):
    # No --sql, --file, and stdin is a tty → error
    result = runner.invoke(app, ["query", "-c", sqlite_path])
    assert result.exit_code != 0
    assert "No SQL provided" in result.output


def test_query_no_sql_provided_json(sqlite_path: str):
    result = runner.invoke(app, ["-f", "json", "query", "-c", sqlite_path])
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "SQL_REQUIRED"


def test_query_from_session_step(sqlite_path: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_session_query_step(
        tmp_path,
        name="scratch",
        index=7,
        sql="select name from users where age > 26",
        connection=sqlite_path,
    )

    result = runner.invoke(app, ["query", "-c", sqlite_path, "--from", "scratch:7"])
    assert result.exit_code == 0, result.output
    assert "Alice" in result.output
    assert "Bob" not in result.output


def test_query_from_session_step_json_includes_provenance(
    sqlite_path: str, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_session_query_step(
        tmp_path,
        name="scratch",
        index=7,
        sql="select name from users where age > 26",
        connection=sqlite_path,
    )

    result = runner.invoke(app, ["-f", "json", "query", "-c", sqlite_path, "--from", "scratch:7"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"]["row_count"] == 1
    assert payload["meta"]["source_session"] == "scratch"
    assert payload["meta"]["source_step"] == 7
    assert payload["meta"]["source_command"] == "query"
    assert payload["meta"]["source_connection"] == sqlite_path


def test_query_from_session_step_last_alias(sqlite_path: str, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_session_query_step(
        tmp_path,
        name="scratch",
        index=1,
        sql="select name from users where id = 2",
        connection=sqlite_path,
    )
    _seed_session_query_step(
        tmp_path,
        name="scratch",
        index=2,
        sql="select name from users where id = 1",
        connection=sqlite_path,
    )

    result = runner.invoke(app, ["query", "-c", sqlite_path, "--from", "scratch:last"])
    assert result.exit_code == 0, result.output
    assert "Alice" in result.output
    assert "Bob" not in result.output


def test_query_file_not_found(sqlite_path: str):
    result = runner.invoke(app, ["query", "-c", sqlite_path, "--file", "/nonexistent/path.sql"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_query_file_not_found_json(sqlite_path: str):
    result = runner.invoke(
        app,
        ["-f", "json", "query", "-c", sqlite_path, "--file", "/nonexistent/path.sql"],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "SQL_FILE_NOT_FOUND"


def test_query_format_json(sqlite_path: str):
    result = runner.invoke(
        app,
        ["-f", "json", "query", "-c", sqlite_path, "--sql", "select * from users"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    assert payload["row_count"] == 2
    assert payload["columns"] == ["id", "name", "age"]
    assert len(payload["rows"]) == 2


def test_query_format_csv(sqlite_path: str):
    result = runner.invoke(
        app,
        ["-f", "csv", "query", "-c", sqlite_path, "--sql", "select * from users"],
    )
    assert result.exit_code == 0
    assert "id,name,age" in result.output
    assert "Alice" in result.output


def test_query_format_markdown(sqlite_path: str):
    result = runner.invoke(
        app,
        ["-f", "markdown", "query", "-c", sqlite_path, "--sql", "select * from users"],
    )
    assert result.exit_code == 0
    assert "| id" in result.output
    assert "Alice" in result.output


def test_query_show_sql(sqlite_path: str):
    result = runner.invoke(
        app,
        ["--show-sql", "query", "-c", sqlite_path, "--sql", "select 1 as n"],
    )
    assert result.exit_code == 0


def test_query_with_semicolon(sqlite_path: str):
    """SQL with trailing semicolons should work fine."""
    result = runner.invoke(
        app,
        ["query", "-c", sqlite_path, "--sql", "select * from users;"],
    )
    assert result.exit_code == 0
    assert "Alice" in result.output


def test_query_aggregate(sqlite_path: str):
    result = runner.invoke(
        app,
        ["-f", "json", "query", "-c", sqlite_path, "--sql", "select count(*) as cnt from users"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    assert payload["rows"][0]["cnt"] == 2


def test_query_write_requires_allow_write(sqlite_path: str):
    result = runner.invoke(
        app,
        ["query", "-c", sqlite_path, "--sql", "update users set age = age + 1 where id = 1"],
    )
    assert result.exit_code != 0
    assert "--allow-write" in result.output


def test_query_write_requires_allow_write_json(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "query",
            "-c",
            sqlite_path,
            "--sql",
            "delete from users where id = 1",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["code"] == "WRITE_REQUIRES_ALLOW_WRITE"
    assert any("--allow-write" in step["cmd"] for step in payload["try_next"])


def test_query_allow_write_persists_sqlite_mutation(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "query",
            "-c",
            sqlite_path,
            "--allow-write",
            "--sql",
            "update users set age = 41 where id = 1",
        ],
    )
    assert result.exit_code == 0

    conn = sqlite3.connect(sqlite_path)
    try:
        age = conn.execute("select age from users where id = 1").fetchone()[0]
    finally:
        conn.close()
    assert age == 41


def test_query_plan_json_read_only(sqlite_path: str):
    result = runner.invoke(
        app,
        ["-f", "json", "query", "-c", sqlite_path, "--sql", "select * from users", "--plan"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["command"] == "query"
    assert payload["data"]["mode"] == "plan"
    assert payload["data"]["action"] == "query"
    assert payload["data"]["executable"] is True


def test_query_plan_write_without_allow_write_is_preview_only(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "query",
            "-c",
            sqlite_path,
            "--sql",
            "update users set age = 99 where id = 1",
            "--plan",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"]["mode"] == "plan"
    assert payload["data"]["destructive"] is True
    assert payload["data"]["executable"] is False

    conn = sqlite3.connect(sqlite_path)
    try:
        age = conn.execute("select age from users where id = 1").fetchone()[0]
    finally:
        conn.close()
    assert age == 30


def test_query_estimate_json_read_only(sqlite_path: str):
    result = runner.invoke(
        app,
        ["-f", "json", "query", "-c", sqlite_path, "--sql", "select * from users", "--estimate"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["command"] == "query"
    assert payload["data"]["mode"] == "estimate"
    assert payload["data"]["action"] == "query"
    assert payload["data"]["cost_hint"] in {"low", "medium", "high"}


def test_query_estimate_write_does_not_mutate(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "query",
            "-c",
            sqlite_path,
            "--sql",
            "update users set age = 99 where id = 1",
            "--estimate",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"]["mode"] == "estimate"
    assert payload["data"]["destructive"] is True

    conn = sqlite3.connect(sqlite_path)
    try:
        age = conn.execute("select age from users where id = 1").fetchone()[0]
    finally:
        conn.close()
    assert age == 30
