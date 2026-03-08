import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_preview_sqlite(sqlite_path: str):
    result = runner.invoke(app, ["preview", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_preview_duckdb(duckdb_path: str):
    result = runner.invoke(app, ["preview", "--connection", duckdb_path, "--table", "users"])
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_preview_respects_rows_flag(sqlite_path: str):
    result = runner.invoke(
        app, ["preview", "--connection", sqlite_path, "--table", "users", "--rows", "1"]
    )
    assert result.exit_code == 0
    assert "1 row(s)" in result.output


def test_preview_default_limit_shown(sqlite_path: str):
    result = runner.invoke(app, ["preview", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "limit 20" in result.output


def test_preview_duckdb_with_rows_flag(duckdb_path: str):
    result = runner.invoke(
        app, ["preview", "--connection", duckdb_path, "--table", "users", "--rows", "1"]
    )
    assert result.exit_code == 0
    assert "1 row(s)" in result.output


@pytest.fixture
def empty_preview_sqlite(tmp_path: Path) -> str:
    db_path = str(tmp_path / "empty_preview.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, label TEXT)")
    conn.commit()
    conn.close()
    return db_path


def test_preview_empty_table(empty_preview_sqlite: str):
    result = runner.invoke(
        app, ["preview", "--connection", empty_preview_sqlite, "--table", "items"]
    )
    assert result.exit_code == 0
    assert "No rows found" in result.output
