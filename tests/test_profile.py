import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_profile_sqlite(sqlite_path: str):
    result = runner.invoke(app, ["profile", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "Numeric Columns" in result.output


def test_profile_top_values(sqlite_path: str):
    result = runner.invoke(
        app,
        ["profile", "--connection", sqlite_path, "--table", "users", "--top", "3"],
    )
    assert result.exit_code == 0
    assert "Top values" in result.output
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_profile_top_zero_hides_frequencies(sqlite_path: str):
    result = runner.invoke(app, ["profile", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "Top values" not in result.output


def test_profile_sample_flag(sqlite_path: str):
    result = runner.invoke(
        app,
        ["profile", "--connection", sqlite_path, "--table", "users", "--sample", "1"],
    )
    assert result.exit_code == 0


def test_profile_no_sample_flag(sqlite_path: str):
    result = runner.invoke(
        app,
        ["profile", "--connection", sqlite_path, "--table", "users", "--no-sample"],
    )
    assert result.exit_code == 0


def test_profile_columns_filter(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "profile",
            "--connection",
            sqlite_path,
            "--table",
            "users",
            "--columns",
            "name",
        ],
    )
    assert result.exit_code == 0
    import json

    data = json.loads(result.output)
    col_names = [c["column_name"] for c in data["columns"]]
    assert "name" in col_names
    assert "id" not in col_names


@pytest.fixture
def string_only_sqlite(tmp_path: Path) -> str:
    db_path = str(tmp_path / "strings.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE names (first TEXT, last TEXT)")
    conn.execute("INSERT INTO names VALUES ('Alice', 'Smith')")
    conn.execute("INSERT INTO names VALUES ('Bob', 'Jones')")
    conn.commit()
    conn.close()
    return db_path


def test_profile_string_only_columns(string_only_sqlite: str):
    result = runner.invoke(
        app,
        ["profile", "--connection", string_only_sqlite, "--table", "names"],
    )
    assert result.exit_code == 0
    assert "String Columns" in result.output


def test_profile_duckdb(duckdb_path: str):
    result = runner.invoke(app, ["profile", "--connection", duckdb_path, "--table", "users"])
    assert result.exit_code == 0
    assert "Numeric Columns" in result.output


def test_profile_top_with_columns(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "profile",
            "--connection",
            sqlite_path,
            "--table",
            "users",
            "--columns",
            "name",
            "--top",
            "2",
        ],
    )
    assert result.exit_code == 0
    assert "Top values" in result.output
    assert "Alice" in result.output
