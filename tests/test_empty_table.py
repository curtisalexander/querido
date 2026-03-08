import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


@pytest.fixture
def empty_sqlite(tmp_path: Path) -> str:
    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE empty_t (id INTEGER PRIMARY KEY, name TEXT NOT NULL, score REAL)")
    conn.commit()
    conn.close()
    return db_path


def test_inspect_empty_table(empty_sqlite: str):
    result = runner.invoke(app, ["inspect", "-c", empty_sqlite, "-t", "empty_t"])
    assert result.exit_code == 0
    assert "id" in result.output
    assert "name" in result.output
    assert "score" in result.output
    assert "0" in result.output


def test_preview_empty_table(empty_sqlite: str):
    result = runner.invoke(app, ["preview", "-c", empty_sqlite, "-t", "empty_t"])
    assert result.exit_code == 0
    assert "No rows found" in result.output


def test_profile_empty_table(empty_sqlite: str):
    result = runner.invoke(app, ["profile", "-c", empty_sqlite, "-t", "empty_t"])
    assert result.exit_code == 0


def test_dist_empty_table(empty_sqlite: str):
    result = runner.invoke(app, ["dist", "-c", empty_sqlite, "-t", "empty_t", "-col", "score"])
    assert result.exit_code == 0


def test_search_finds_empty_table(empty_sqlite: str):
    result = runner.invoke(app, ["search", "-p", "empty_t", "-c", empty_sqlite])
    assert result.exit_code == 0
    assert "empty_t" in result.output


def test_sql_select_empty_table(empty_sqlite: str):
    result = runner.invoke(app, ["sql", "select", "-c", empty_sqlite, "-t", "empty_t"])
    assert result.exit_code == 0
    assert "SELECT" in result.output
    assert "FROM empty_t;" in result.output


def test_sql_ddl_empty_table(empty_sqlite: str):
    result = runner.invoke(app, ["sql", "ddl", "-c", empty_sqlite, "-t", "empty_t"])
    assert result.exit_code == 0
    assert "CREATE TABLE empty_t" in result.output


def test_sql_insert_empty_table(empty_sqlite: str):
    result = runner.invoke(app, ["sql", "insert", "-c", empty_sqlite, "-t", "empty_t"])
    assert result.exit_code == 0
    assert "INSERT INTO empty_t" in result.output
