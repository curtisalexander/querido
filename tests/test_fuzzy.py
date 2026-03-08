"""Tests for fuzzy table/column name suggestions in error messages (F15)."""

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


@pytest.fixture
def sqlite_path(tmp_path: Path) -> str:
    db_path = str(tmp_path / "fuzzy.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    conn.execute("CREATE TABLE orders (id INTEGER, user_id INTEGER, total REAL)")
    conn.execute("CREATE TABLE products (id INTEGER, product_name TEXT, price REAL)")
    conn.execute("CREATE TABLE user_roles (user_id INTEGER, role TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@test.com')")
    conn.execute("INSERT INTO orders VALUES (1, 1, 99.99)")
    conn.execute("INSERT INTO products VALUES (1, 'Widget', 9.99)")
    conn.execute("INSERT INTO user_roles VALUES (1, 'admin')")
    conn.commit()
    conn.close()
    return db_path


# -- Table fuzzy suggestions --------------------------------------------------


def test_table_fuzzy_suggestion_typo(sqlite_path: str):
    """Misspelling 'users' as 'usrs' should suggest 'users'."""
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "usrs"])
    assert result.exit_code != 0
    assert "Did you mean" in result.output
    assert "users" in result.output


def test_table_fuzzy_suggestion_partial(sqlite_path: str):
    """Partial name 'user' should suggest 'users' and 'user_roles'."""
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "user"])
    assert result.exit_code != 0
    assert "Did you mean" in result.output
    assert "users" in result.output


def test_table_fuzzy_no_suggestion_for_gibberish(sqlite_path: str):
    """Completely unrelated name should not crash, may not have suggestions."""
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "zzzzzzz"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_table_fuzzy_still_lists_available(sqlite_path: str):
    """Available tables should still be listed for small table counts."""
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "usrs"])
    assert result.exit_code != 0
    assert "Available" in result.output


# -- Column fuzzy suggestions -------------------------------------------------


def test_column_fuzzy_suggestion_typo(sqlite_path: str):
    """Misspelling 'email' as 'emal' should suggest 'email'."""
    result = runner.invoke(app, ["dist", "-c", sqlite_path, "-t", "users", "-col", "emal"])
    assert result.exit_code != 0
    assert "Did you mean" in result.output
    assert "email" in result.output


def test_column_fuzzy_suggestion_partial(sqlite_path: str):
    """'nam' should suggest 'name'."""
    result = runner.invoke(app, ["dist", "-c", sqlite_path, "-t", "users", "-col", "nam"])
    assert result.exit_code != 0
    assert "Did you mean" in result.output
    assert "name" in result.output


def test_column_fuzzy_context_message(sqlite_path: str):
    """Error message should mention the table name for context."""
    result = runner.invoke(app, ["dist", "-c", sqlite_path, "-t", "users", "-col", "nonexistent"])
    assert result.exit_code != 0
    assert "table 'users'" in result.output


# -- Unit tests for _format_not_found -----------------------------------------


def test_format_not_found_with_close_match():
    from querido.cli._util import _format_not_found

    msg = _format_not_found("Table", "usrs", ["users", "orders", "products"])
    assert "Did you mean" in msg
    assert "users" in msg
    assert "Available" in msg


def test_format_not_found_large_list_no_available():
    from querido.cli._util import _format_not_found

    candidates = [f"table_{i}" for i in range(100)]
    msg = _format_not_found("Table", "table_1", candidates, max_available=30)
    assert "Did you mean" in msg
    assert "Available" not in msg


def test_format_not_found_preserves_original_casing():
    from querido.cli._util import _format_not_found

    msg = _format_not_found("Column", "usr_id", ["USER_ID", "ORDER_ID", "TOTAL"])
    assert "Did you mean" in msg
    assert "USER_ID" in msg


def test_fuzzy_suggestions_returns_matches():
    from querido.cli._util import _fuzzy_suggestions

    matches = _fuzzy_suggestions("usrs", ["users", "orders", "products"])
    assert "users" in matches
