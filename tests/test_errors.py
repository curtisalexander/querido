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
# Validation-error contract
# ---------------------------------------------------------------------------
#
# Validation errors (table / column not found, missing connection file) raise
# ``typer.BadParameter``, which bypasses the structured JSON error envelope —
# Typer formats them as human-readable prose on stderr.  Until R.22 / R.23
# route these through the envelope, the test surface is unavoidably prose-
# matched.  These tests therefore assert on *content* (identifier names,
# expected candidates) rather than prose framing where we can avoid it, and
# the whole contract is centralized here so reshaping the error path later
# is a one-file change.
#
# Every validation error must: exit non-zero, not leak a Python traceback,
# and echo the offending identifier back to the user.


@pytest.mark.parametrize(
    ("argv", "expected_identifier"),
    [
        (["inspect", "-t", "nonexistent"], "nonexistent"),
        (["preview", "-t", "nonexistent"], "nonexistent"),
        (["profile", "-t", "nonexistent"], "nonexistent"),
        (["dist", "-t", "nonexistent", "-C", "id"], "nonexistent"),
        (["sql", "select", "-t", "nonexistent"], "nonexistent"),
        (["dist", "-t", "users", "-C", "nonexistent"], "nonexistent"),
    ],
    ids=[
        "inspect-missing-table",
        "preview-missing-table",
        "profile-missing-table",
        "dist-missing-table",
        "sql-select-missing-table",
        "dist-missing-column",
    ],
)
def test_validation_error_contract(
    sqlite_path: str, argv: list[str], expected_identifier: str
) -> None:
    """Non-zero exit, no traceback, offending identifier echoed back."""
    result = runner.invoke(app, [*argv, "-c", sqlite_path])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert expected_identifier in result.output


def test_profile_column_filter_missing(sqlite_path: str) -> None:
    """``profile --columns nonexistent`` has a distinct error path that says
    "No matching columns" rather than echoing the bad identifier verbatim.
    Kept as a separate test so the product can change without failing the
    main validation contract above.
    """
    result = runner.invoke(
        app, ["profile", "-c", sqlite_path, "-t", "users", "--columns", "nonexistent"]
    )
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "No matching columns" in result.output or "nonexistent" in result.output


def test_table_not_found_lists_available(sqlite_path: str) -> None:
    """The list of available tables shows up when one isn't found."""
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "nonexistent"])
    assert result.exit_code != 0
    assert "users" in result.output


def test_column_not_found_lists_available(sqlite_path: str) -> None:
    """The list of available columns shows up when one isn't found."""
    result = runner.invoke(app, ["dist", "-c", sqlite_path, "-t", "users", "-C", "nonexistent"])
    assert result.exit_code != 0
    assert "name" in result.output or "id" in result.output


def test_missing_connection_file_contract(tmp_path: Path) -> None:
    """Missing DB file: non-zero, no traceback, suggests `qdo config add`."""
    missing = str(tmp_path / "missing.db")
    result = runner.invoke(app, ["inspect", "-c", missing, "-t", "users"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    # ``qdo config add`` is the try_next hint surfaced to the user — stable
    # wording, worth asserting on until R.22/R.23 route this through the
    # structured envelope.
    assert "qdo config add" in result.output


# ---------------------------------------------------------------------------
# Fuzzy-suggestion content contract
# ---------------------------------------------------------------------------
#
# When a typo has a close match, the candidate identifier must appear in the
# output so the user can retry.  We intentionally don't assert on the
# "Did you mean" prose framing — that's covered by the _format_not_found
# unit tests below — only that the right candidate shows up.


@pytest.mark.parametrize(
    ("argv", "expected_candidate"),
    [
        (["inspect", "-t", "usrs"], "users"),
        (["inspect", "-t", "user"], "users"),
        (["dist", "-t", "users", "-C", "emal"], "email"),
        (["dist", "-t", "users", "-C", "nam"], "name"),
    ],
    ids=["table-typo", "table-partial", "column-typo-email", "column-typo-name"],
)
def test_fuzzy_suggestion_surfaces_candidate(
    sqlite_path: str, argv: list[str], expected_candidate: str
) -> None:
    result = runner.invoke(app, [*argv, "-c", sqlite_path])
    assert result.exit_code != 0
    assert expected_candidate in result.output


def test_fuzzy_no_crash_on_gibberish(sqlite_path: str) -> None:
    """Unrelated input produces a clean validation error (no traceback)."""
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "zzzzzzz"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output


# ---------------------------------------------------------------------------
# Invalid identifiers
# ---------------------------------------------------------------------------


def test_invalid_table_name(sqlite_path: str):
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "DROP TABLE; --"])
    assert result.exit_code != 0


def test_invalid_column_name(sqlite_path: str):
    result = runner.invoke(
        app, ["dist", "-c", sqlite_path, "-t", "users", "-C", "col; DROP TABLE"]
    )
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Case-insensitive column matching
# ---------------------------------------------------------------------------


def test_dist_case_insensitive_column(sqlite_path: str):
    """Column name matching should be case-insensitive.

    ``resolve_column()`` normalizes at the CLI boundary regardless of
    dialect, so one fixture is enough to prove the contract (the DuckDB
    variant was dropped 2026-04-17).
    """
    result = runner.invoke(app, ["dist", "-c", sqlite_path, "-t", "users", "-C", "NAME"])
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


# The standalone ``test_no_traceback_*`` pair was folded into
# ``test_validation_error_contract`` / ``test_missing_connection_file_contract``
# above — every validation error already asserts ``"Traceback" not in``.


# ---------------------------------------------------------------------------
# Unit tests for _format_not_found / _fuzzy_suggestions
# ---------------------------------------------------------------------------


def test_format_not_found_with_close_match():
    from querido.cli._validation import _format_not_found

    msg = _format_not_found("Table", "usrs", ["users", "orders", "products"])
    assert "Did you mean" in msg
    assert "users" in msg
    assert "Available" in msg


def test_format_not_found_large_list_no_available():
    from querido.cli._validation import _format_not_found

    candidates = [f"table_{i}" for i in range(100)]
    msg = _format_not_found("Table", "table_1", candidates, max_available=30)
    assert "Did you mean" in msg
    assert "Available" not in msg


def test_format_not_found_preserves_original_casing():
    from querido.cli._validation import _format_not_found

    msg = _format_not_found("Column", "usr_id", ["USER_ID", "ORDER_ID", "TOTAL"])
    assert "Did you mean" in msg
    assert "USER_ID" in msg


def test_fuzzy_suggestions_returns_matches():
    from querido.cli._validation import _fuzzy_suggestions

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


def test_resolve_table_case_insensitive(sqlite_path: str):
    """User types USERS, table is users — resolver returns canonical name.

    ``resolve_table()`` delegates to ``connector.get_tables()`` and does the
    case-insensitive match in Python; it's dialect-neutral. The DuckDB
    variant was dropped 2026-04-17.
    """
    from querido.cli._validation import resolve_table
    from querido.connectors.sqlite import SQLiteConnector

    with SQLiteConnector(sqlite_path) as conn:
        assert resolve_table(conn, "USERS") == "users"
        assert resolve_table(conn, "Users") == "users"
        assert resolve_table(conn, "ORDERS") == "orders"


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


@pytest.mark.parametrize(
    "argv",
    [
        ["preview", "-t", "USERS", "-r", "1"],
        ["inspect", "-t", "USERS"],
        ["sql", "select", "-t", "USERS"],
        ["profile", "-t", "USERS"],
    ],
    ids=["preview", "inspect", "sql-select", "profile"],
)
def test_cli_accepts_case_insensitive_table(sqlite_path: str, argv: list[str]) -> None:
    """Contract: every table-scoped command resolves USERS → users."""
    result = runner.invoke(app, [*argv, "-c", sqlite_path])
    assert result.exit_code == 0


def test_sql_select_case_insensitive_emits_canonical_name(sqlite_path: str) -> None:
    """sql select should output the canonical (lowercase) table name."""
    result = runner.invoke(app, ["sql", "select", "-c", sqlite_path, "-t", "USERS"])
    assert result.exit_code == 0
    assert "from users;" in result.output
