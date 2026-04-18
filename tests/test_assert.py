"""Tests for qdo assert command."""

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_assert_eq_pass(sqlite_path: str):
    result = runner.invoke(
        app,
        ["assert", "-c", sqlite_path, "--sql", "select count(*) from users", "--expect", "2"],
    )
    assert result.exit_code == 0
    assert "PASSED" in result.output


def test_assert_eq_fail(sqlite_path: str):
    result = runner.invoke(
        app,
        ["assert", "-c", sqlite_path, "--sql", "select count(*) from users", "--expect", "99"],
    )
    assert result.exit_code == 1
    assert "FAILED" in result.output


def test_assert_gt_pass(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select count(*) from users",
            "--expect-gt",
            "1",
        ],
    )
    assert result.exit_code == 0


def test_assert_gt_fail(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select count(*) from users",
            "--expect-gt",
            "100",
        ],
    )
    assert result.exit_code == 1


def test_assert_lt_pass(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select count(*) from users",
            "--expect-lt",
            "10",
        ],
    )
    assert result.exit_code == 0


def test_assert_gte_pass(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select count(*) from users",
            "--expect-gte",
            "2",
        ],
    )
    assert result.exit_code == 0


def test_assert_lte_pass(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select count(*) from users",
            "--expect-lte",
            "2",
        ],
    )
    assert result.exit_code == 0


def test_assert_quiet_pass(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select count(*) from users",
            "--expect",
            "2",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_assert_quiet_fail(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select count(*) from users",
            "--expect",
            "99",
            "--quiet",
        ],
    )
    assert result.exit_code == 1
    assert result.output.strip() == ""


def test_assert_with_name(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select count(*) from users",
            "--expect",
            "2",
            "--name",
            "user count check",
        ],
    )
    assert result.exit_code == 0
    assert "user count check" in result.output


def test_assert_sql_error(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select * from nonexistent",
            "--expect",
            "0",
        ],
    )
    assert result.exit_code == 1


def test_assert_no_operator(sqlite_path: str):
    result = runner.invoke(
        app,
        ["assert", "-c", sqlite_path, "--sql", "select 1"],
    )
    assert result.exit_code != 0
    assert "Must provide one of" in result.output


def test_assert_format_json(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select count(*) from users",
            "--expect",
            "2",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["command"] == "assert"
    data = payload["data"]
    assert data["passed"] is True
    assert data["actual"] == 2.0
    assert data["expected"] == 2.0
    assert data["operator"] == "eq"


def test_assert_format_json_fail(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select count(*) from users",
            "--expect",
            "99",
        ],
    )
    assert result.exit_code == 1
    import json

    payload = json.loads(result.output)
    data = payload["data"]
    assert data["passed"] is False
    assert data["actual"] == 2.0
    # A failing assert should point the agent at the underlying query.
    assert any("qdo query" in s["cmd"] for s in payload["next_steps"])


def test_assert_format_csv(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "csv",
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select count(*) from users",
            "--expect",
            "2",
        ],
    )
    assert result.exit_code == 0
    assert "passed" in result.output


def test_assert_format_markdown(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "markdown",
            "assert",
            "-c",
            sqlite_path,
            "--sql",
            "select count(*) from users",
            "--expect",
            "2",
        ],
    )
    assert result.exit_code == 0
    assert "PASSED" in result.output


def test_assert_from_stdin(sqlite_path: str):
    result = runner.invoke(
        app,
        ["assert", "-c", sqlite_path, "--expect", "2"],
        input="select count(*) from users",
    )
    assert result.exit_code == 0
