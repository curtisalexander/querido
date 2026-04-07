"""Tests for qdo explain command."""

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_explain_sqlite(sqlite_path: str):
    result = runner.invoke(
        app,
        ["explain", "-c", sqlite_path, "--sql", "select * from users"],
    )
    assert result.exit_code == 0
    assert "SCAN" in result.output.upper() or "plan" in result.output.lower()


def test_explain_duckdb(duckdb_path: str):
    result = runner.invoke(
        app,
        ["explain", "-c", duckdb_path, "--sql", "select * from users"],
    )
    assert result.exit_code == 0


def test_explain_format_json(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "-f", "json", "explain", "-c", sqlite_path,
            "--sql", "select * from users where age > 25",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert "plan" in payload
    assert payload.get("dialect") == "sqlite"
    assert payload.get("analyzed") is False
    assert len(payload.get("plan", "")) > 0


def test_explain_format_csv(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "-f", "csv", "explain", "-c", sqlite_path,
            "--sql", "select * from users",
        ],
    )
    assert result.exit_code == 0
    # CSV just returns the plan text
    assert len(result.output.strip()) > 0


def test_explain_format_markdown(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "-f", "markdown", "explain", "-c", sqlite_path,
            "--sql", "select * from users",
        ],
    )
    assert result.exit_code == 0
    assert "## Query Plan" in result.output
    assert "```" in result.output


def test_explain_analyze_duckdb(duckdb_path: str):
    result = runner.invoke(
        app,
        [
            "-f", "json", "explain", "-c", duckdb_path,
            "--sql", "select * from users", "--analyze",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload.get("analyzed") is True


def test_explain_from_stdin(sqlite_path: str):
    result = runner.invoke(
        app,
        ["explain", "-c", sqlite_path],
        input="select * from users",
    )
    assert result.exit_code == 0


def test_explain_no_sql(sqlite_path: str):
    result = runner.invoke(
        app,
        ["explain", "-c", sqlite_path],
    )
    assert result.exit_code != 0
    assert "No SQL provided" in result.output


def test_explain_sql_error(sqlite_path: str):
    result = runner.invoke(
        app,
        ["explain", "-c", sqlite_path, "--sql", "select * from nope"],
    )
    assert result.exit_code == 1


def test_explain_with_where_clause(sqlite_path: str):
    """EXPLAIN on a filtered query should show the plan."""
    result = runner.invoke(
        app,
        [
            "-f", "json", "explain", "-c", sqlite_path,
            "--sql", "select * from users where name = 'Alice'",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert len(payload.get("plan", "")) > 0
