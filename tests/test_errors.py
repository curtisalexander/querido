"""Tests for error messages, fuzzy suggestions, and input validation across the CLI."""

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


@pytest.mark.parametrize(
    "args",
    [
        ["inspect", "-t", "nonexistent"],
        ["preview", "-t", "nonexistent"],
        ["profile", "-t", "nonexistent"],
        ["dist", "-t", "nonexistent", "-col", "id"],
        ["sql", "select", "-t", "nonexistent"],
    ],
    ids=["inspect", "preview", "profile", "dist", "sql-select"],
)
def test_table_not_found(sqlite_path: str, args: list[str]):
    result = runner.invoke(app, [*args, "-c", sqlite_path])
    assert result.exit_code != 0


def test_table_not_found_lists_available(sqlite_path: str):
    """Error message should list available tables."""
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "nonexistent"])
    assert result.exit_code != 0
    assert "users" in result.output


# ---------------------------------------------------------------------------
# Table fuzzy suggestions
# ---------------------------------------------------------------------------


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
# Column fuzzy suggestions
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Unit tests for _format_not_found / _fuzzy_suggestions
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# resolve_table — case-insensitive table name resolution
# ---------------------------------------------------------------------------


def test_resolve_table_exact_match(sqlite_path: str):
    from querido.cli._validation import resolve_table
    from querido.connectors.sqlite import SQLiteConnector

    with SQLiteConnector(sqlite_path) as conn:
        assert resolve_table(conn, "users") == "users"


def test_resolve_table_case_insensitive_sqlite(sqlite_path: str):
    """User types USERS, table is users — should resolve to canonical name."""
    from querido.cli._validation import resolve_table
    from querido.connectors.sqlite import SQLiteConnector

    with SQLiteConnector(sqlite_path) as conn:
        assert resolve_table(conn, "USERS") == "users"
        assert resolve_table(conn, "Users") == "users"
        assert resolve_table(conn, "ORDERS") == "orders"


def test_resolve_table_case_insensitive_duckdb(duckdb_path: str):
    from querido.cli._validation import resolve_table
    from querido.connectors.duckdb import DuckDBConnector

    with DuckDBConnector(duckdb_path) as conn:
        assert resolve_table(conn, "USERS") == "users"
        assert resolve_table(conn, "Users") == "users"


def test_resolve_table_not_found_raises(sqlite_path: str):
    import typer

    from querido.cli._validation import resolve_table
    from querido.connectors.sqlite import SQLiteConnector

    with (
        SQLiteConnector(sqlite_path) as conn,
        pytest.raises(typer.BadParameter, match="not found"),
    ):
        resolve_table(conn, "nonexistent")


def test_resolve_table_not_found_has_suggestions(sqlite_path: str):
    """resolve_table error should include fuzzy suggestions."""
    import typer

    from querido.cli._validation import resolve_table
    from querido.connectors.sqlite import SQLiteConnector

    with (
        SQLiteConnector(sqlite_path) as conn,
        pytest.raises(typer.BadParameter, match="Did you mean"),
    ):
        resolve_table(conn, "usrs")


# ---------------------------------------------------------------------------
# CLI commands accept case-insensitive table names
# ---------------------------------------------------------------------------


def test_preview_case_insensitive_table(sqlite_path: str):
    result = runner.invoke(app, ["preview", "-c", sqlite_path, "-t", "USERS", "-r", "1"])
    assert result.exit_code == 0


def test_inspect_case_insensitive_table(sqlite_path: str):
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "USERS"])
    assert result.exit_code == 0


def test_sql_select_case_insensitive_table(sqlite_path: str):
    result = runner.invoke(app, ["sql", "select", "-c", sqlite_path, "-t", "USERS"])
    assert result.exit_code == 0
    # Should use the canonical table name (lowercase) in output
    assert "from users;" in result.output


def test_profile_case_insensitive_table(sqlite_path: str):
    result = runner.invoke(app, ["profile", "-c", sqlite_path, "-t", "USERS"])
    assert result.exit_code == 0
