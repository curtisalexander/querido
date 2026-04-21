import json
from pathlib import Path

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


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
