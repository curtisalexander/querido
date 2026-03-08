"""Tests for improved error messages across the CLI."""

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_path(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def duckdb_path(tmp_path: Path) -> str:
    import duckdb

    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, age INTEGER)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Table not found
# ---------------------------------------------------------------------------


def test_inspect_table_not_found(sqlite_path: str):
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "not found" in (result.stderr or "").lower()


def test_preview_table_not_found(sqlite_path: str):
    result = runner.invoke(app, ["preview", "-c", sqlite_path, "-t", "nonexistent"])
    assert result.exit_code != 0


def test_profile_table_not_found(sqlite_path: str):
    result = runner.invoke(app, ["profile", "-c", sqlite_path, "-t", "nonexistent"])
    assert result.exit_code != 0


def test_dist_table_not_found(sqlite_path: str):
    result = runner.invoke(app, ["dist", "-c", sqlite_path, "-t", "nonexistent", "-col", "id"])
    assert result.exit_code != 0


def test_sql_select_table_not_found(sqlite_path: str):
    result = runner.invoke(app, ["sql", "select", "-c", sqlite_path, "-t", "nonexistent"])
    assert result.exit_code != 0


def test_table_not_found_lists_available(sqlite_path: str):
    """Error message should list available tables."""
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "nonexistent"])
    assert result.exit_code != 0
    assert "users" in result.output


# ---------------------------------------------------------------------------
# Column not found
# ---------------------------------------------------------------------------


def test_dist_column_not_found(sqlite_path: str):
    result = runner.invoke(app, ["dist", "-c", sqlite_path, "-t", "users", "-col", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_dist_column_not_found_lists_available(sqlite_path: str):
    result = runner.invoke(app, ["dist", "-c", sqlite_path, "-t", "users", "-col", "nonexistent"])
    assert result.exit_code != 0
    # Should list available columns
    assert "name" in result.output or "id" in result.output


def test_profile_column_filter_not_found(sqlite_path: str):
    result = runner.invoke(
        app, ["profile", "-c", sqlite_path, "-t", "users", "--columns", "nonexistent"]
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "No matching" in result.output


# ---------------------------------------------------------------------------
# Database file not found
# ---------------------------------------------------------------------------


def test_connection_file_not_found(tmp_path: Path):
    missing = str(tmp_path / "missing.db")
    result = runner.invoke(app, ["inspect", "-c", missing, "-t", "users"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_connection_file_not_found_suggests_config(tmp_path: Path):
    missing = str(tmp_path / "missing.db")
    result = runner.invoke(app, ["inspect", "-c", missing, "-t", "users"])
    assert result.exit_code != 0
    assert "qdo config add" in result.output


# ---------------------------------------------------------------------------
# Invalid identifiers
# ---------------------------------------------------------------------------


def test_invalid_table_name(sqlite_path: str):
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "DROP TABLE; --"])
    assert result.exit_code != 0


def test_invalid_column_name(sqlite_path: str):
    result = runner.invoke(
        app, ["dist", "-c", sqlite_path, "-t", "users", "-col", "col; DROP TABLE"]
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Case-insensitive column matching
# ---------------------------------------------------------------------------


def test_dist_case_insensitive_column_sqlite(sqlite_path: str):
    """Column name matching should be case-insensitive."""
    result = runner.invoke(app, ["dist", "-c", sqlite_path, "-t", "users", "-col", "NAME"])
    assert result.exit_code == 0


def test_dist_case_insensitive_column_duckdb(duckdb_path: str):
    result = runner.invoke(app, ["dist", "-c", duckdb_path, "-t", "users", "-col", "NAME"])
    assert result.exit_code == 0


def test_profile_case_insensitive_column_filter(sqlite_path: str):
    """Profile --columns should be case-insensitive."""
    result = runner.invoke(app, ["profile", "-c", sqlite_path, "-t", "users", "--columns", "NAME"])
    assert result.exit_code == 0
    assert "name" in result.output.lower()


# ---------------------------------------------------------------------------
# Case-insensitive metadata lookups (DuckDB)
# ---------------------------------------------------------------------------


def test_duckdb_get_columns_case_insensitive(duckdb_path: str):
    """DuckDB get_columns should work regardless of table name case."""
    from querido.connectors.duckdb import DuckDBConnector

    with DuckDBConnector(duckdb_path) as conn:
        # Table was created as "users" (lowercase)
        cols_lower = conn.get_columns("users")
        cols_upper = conn.get_columns("USERS")
        cols_mixed = conn.get_columns("Users")

        assert len(cols_lower) > 0
        assert len(cols_upper) == len(cols_lower)
        assert len(cols_mixed) == len(cols_lower)


def test_duckdb_get_table_comment_case_insensitive(tmp_path: Path):
    import duckdb

    db_path = str(tmp_path / "comments.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER)")
    conn.execute("COMMENT ON TABLE users IS 'Test comment'")
    conn.close()

    from querido.connectors.duckdb import DuckDBConnector

    with DuckDBConnector(db_path) as connector:
        assert connector.get_table_comment("users") == "Test comment"
        assert connector.get_table_comment("USERS") == "Test comment"


# ---------------------------------------------------------------------------
# Friendly error formatting (no tracebacks)
# ---------------------------------------------------------------------------


def test_no_traceback_on_table_not_found(sqlite_path: str):
    """Errors should show clean messages, not Python tracebacks."""
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "nonexistent"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output


def test_no_traceback_on_missing_file(tmp_path: Path):
    missing = str(tmp_path / "missing.db")
    result = runner.invoke(app, ["inspect", "-c", missing, "-t", "users"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
