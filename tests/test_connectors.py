import pytest

from querido.connectors.duckdb import DuckDBConnector
from querido.connectors.factory import create_connector
from querido.connectors.sqlite import SQLiteConnector


def test_sqlite_execute(sqlite_path: str):
    with SQLiteConnector(sqlite_path) as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"
        assert rows[1]["age"] == 25


def test_sqlite_get_columns(sqlite_path: str):
    with SQLiteConnector(sqlite_path) as conn:
        cols = conn.get_columns("users")
        assert len(cols) == 3
        names = [c["name"] for c in cols]
        assert names == ["id", "name", "age"]
        assert cols[0]["primary_key"] is True


def test_duckdb_execute(duckdb_path: str):
    with DuckDBConnector(duckdb_path) as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"
        assert rows[1]["age"] == 25


def test_duckdb_get_columns(duckdb_path: str):
    with DuckDBConnector(duckdb_path) as conn:
        cols = conn.get_columns("users")
        assert len(cols) == 3
        names = [c["name"] for c in cols]
        assert names == ["id", "name", "age"]
        nullable_by_name = {c["name"]: c["nullable"] for c in cols}
        assert nullable_by_name == {"id": False, "name": False, "age": True}


def test_duckdb_mixed_case_table_catalog_lookups():
    # Regression: catalog lookups lowercased the table name in Python while
    # DuckDB preserves as-written case, so a table created as "MyTable"
    # returned no columns and a zero row count.
    with DuckDBConnector(":memory:") as conn:
        conn.execute('create table "MyTable" ("Id" integer, "FullName" varchar)')
        conn.execute("insert into \"MyTable\" values (1, 'Alice'), (2, 'Bob')")

        cols = conn.get_columns("MyTable")
        assert [c["name"] for c in cols] == ["Id", "FullName"]
        assert conn.get_row_count("MyTable") == 2

        # DuckDB resolves identifiers case-insensitively, so lowercase
        # input must still find the mixed-case table.
        assert [c["name"] for c in conn.get_columns("mytable")] == ["Id", "FullName"]
        assert conn.get_row_count("mytable") == 2


def test_factory_sqlite(sqlite_path: str):
    with create_connector({"type": "sqlite", "path": sqlite_path}) as conn:
        rows = conn.execute("SELECT count(*) as cnt FROM users")
        assert rows[0]["cnt"] == 2


def test_factory_duckdb(duckdb_path: str):
    with create_connector({"type": "duckdb", "path": duckdb_path}) as conn:
        rows = conn.execute("SELECT count(*) as cnt FROM users")
        assert rows[0]["cnt"] == 2


def test_duckdb_file_backed_connector_uses_read_only(tmp_path):
    import duckdb

    db_path = str(tmp_path / "shared.duckdb")
    bootstrap = duckdb.connect(db_path)
    bootstrap.execute("create table users(id integer, name varchar)")
    bootstrap.execute("insert into users values (1, 'Alice')")
    bootstrap.close()

    with DuckDBConnector(db_path) as left, DuckDBConnector(db_path) as right:
        left_rows = left.execute("select count(*) as cnt from users")
        right_rows = right.execute("select count(*) as cnt from users")
        assert left_rows[0]["cnt"] == 1
        assert right_rows[0]["cnt"] == 1


# ---------------------------------------------------------------------------
# SQLite read-only by default (M5) — a read-oriented exploration tool must
# never mutate the user's database file or create one that doesn't exist.
# ---------------------------------------------------------------------------


def test_sqlite_nonexistent_path_raises_instead_of_creating(tmp_path):
    from querido.connectors.base import DatabaseOpenError

    missing = tmp_path / "does_not_exist.db"
    with pytest.raises(DatabaseOpenError):
        SQLiteConnector(str(missing))
    assert not missing.exists()


def test_sqlite_connector_does_not_mutate_journal_mode_or_create_sidecars(sqlite_path: str):
    import sqlite3
    from pathlib import Path

    def journal_mode() -> str:
        raw = sqlite3.connect(sqlite_path)
        try:
            return raw.execute("pragma journal_mode").fetchone()[0]
        finally:
            raw.close()

    before = journal_mode()
    with SQLiteConnector(sqlite_path) as conn:
        rows = conn.execute("select count(*) as cnt from users")
        assert rows[0].get("cnt") == 2
    assert journal_mode() == before
    assert not Path(sqlite_path + "-wal").exists()
    assert not Path(sqlite_path + "-shm").exists()


def test_sqlite_read_only_by_default_rejects_writes(sqlite_path: str):
    from querido.connectors.base import ConnectorError

    with SQLiteConnector(sqlite_path) as conn, pytest.raises(ConnectorError):
        conn.execute("update users set age = 99 where id = 1")


def test_sqlite_read_only_opt_out_allows_writes(sqlite_path: str):
    with SQLiteConnector(sqlite_path, read_only=False) as conn:
        conn.execute("update users set age = 99 where id = 1")
        conn.conn.commit()
        rows = conn.execute("select age from users where id = 1")
        assert rows[0].get("age") == 99


def test_sqlite_memory_path_stays_writable():
    with SQLiteConnector(":memory:") as conn:
        conn.execute("create table t (id integer)")
        conn.execute("insert into t values (1)")
        rows = conn.execute("select count(*) as cnt from t")
        assert rows[0].get("cnt") == 1


def test_factory_sqlite_read_only_flag(sqlite_path: str):
    from querido.connectors.base import ConnectorError

    config = {"type": "sqlite", "path": sqlite_path}
    with create_connector(config) as conn, pytest.raises(ConnectorError):
        conn.execute("delete from users")
    with create_connector(config, read_only=False) as conn:
        conn.execute("delete from users where id = 2")
        rows = conn.execute("select count(*) as cnt from users")
        assert rows[0].get("cnt") == 1


# ---------------------------------------------------------------------------
# ConnectorError hierarchy (R.23) — driver exceptions surface as typed errors
# so CLI and core code can isinstance-check instead of parsing messages.
# ---------------------------------------------------------------------------


def test_sqlite_missing_table_raises_table_not_found(sqlite_path: str):
    from querido.connectors.base import TableNotFoundError

    with SQLiteConnector(sqlite_path) as conn, pytest.raises(TableNotFoundError):
        conn.execute("select * from nonexistent_table")


def test_duckdb_missing_table_raises_table_not_found(duckdb_path: str):
    from querido.connectors.base import TableNotFoundError

    with DuckDBConnector(duckdb_path) as conn, pytest.raises(TableNotFoundError):
        conn.execute("select * from nonexistent_table")


def test_sqlite_missing_column_raises_column_not_found(sqlite_path: str):
    from querido.connectors.base import ColumnNotFoundError

    with SQLiteConnector(sqlite_path) as conn, pytest.raises(ColumnNotFoundError):
        conn.execute("select nonexistent_col from users")


def test_wrap_driver_error_unclassified_returns_none():
    """Unrecognized driver messages leave the exception alone for un-wrapped re-raise."""
    from querido.connectors.base import wrap_driver_error

    assert wrap_driver_error(Exception("syntax error at line 1")) is None


def test_wrap_driver_error_column_not_misclassified_as_table():
    """A column 'does not exist' message must not become a TableNotFoundError (L12).

    Snowflake/DuckDB reuse 'does not exist' / 'invalid identifier' for columns;
    a too-broad table match used to wrap these as TableNotFoundError with the
    whole message stuffed into .table.
    """
    from querido.connectors.base import (
        ColumnNotFoundError,
        TableNotFoundError,
        wrap_driver_error,
    )

    col = wrap_driver_error(Exception("invalid identifier 'STATUS'"))
    assert isinstance(col, ColumnNotFoundError)
    col2 = wrap_driver_error(Exception("Column 'amount' does not exist"))
    assert isinstance(col2, ColumnNotFoundError)
    assert not isinstance(col2, TableNotFoundError)

    tbl = wrap_driver_error(Exception("Object 'ORDERS' does not exist or not authorized"))
    assert isinstance(tbl, TableNotFoundError)


def test_wrap_driver_error_password_word_not_treated_as_auth():
    """A message merely mentioning 'password' (e.g. a column) is not an auth error (L12)."""
    from querido.connectors.base import AuthenticationError, wrap_driver_error

    not_auth = wrap_driver_error(Exception("no such column: password"))
    assert not isinstance(not_auth, AuthenticationError)

    auth = wrap_driver_error(Exception("Incorrect username or password was specified"))
    assert isinstance(auth, AuthenticationError)


def test_validate_identifier_message_explains_safety():
    """The rejection message states why and what's allowed (L14)."""
    from querido.connectors.base import validate_column_name

    with pytest.raises(ValueError, match="plain identifiers"):
        validate_column_name("full name")


def test_sqlite_rejects_dotted_table_name(sqlite_path: str):
    """SQLite connector rejects schema-qualified names consistently (L15).

    pragma table_info(main.users) is a syntax error, so dotted names were
    broken/inconsistent; the connector now rejects them with a clear message.
    """
    with SQLiteConnector(sqlite_path) as conn, pytest.raises(ValueError, match="unqualified"):
        conn.get_columns("main.users")


def test_wrap_driver_error_preserves_original_as_cause(sqlite_path: str):
    """__cause__ is set so tracebacks still show the driver exception."""
    from querido.connectors.base import TableNotFoundError

    with SQLiteConnector(sqlite_path) as conn:
        try:
            conn.execute("select * from nonexistent_table")
        except TableNotFoundError as exc:
            assert exc.__cause__ is not None
            assert "nonexistent_table" in str(exc.__cause__)


# ---------------------------------------------------------------------------
# sample_source validates table names (R.24) so integrations/tests can't
# bypass the CLI-layer identifier check.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_name",
    ["users; drop table x", "users'--", "users(1)", "1bad"],
    ids=["semicolon", "sql-comment", "parens", "leading-digit"],
)
def test_sqlite_sample_source_rejects_unsafe_names(sqlite_path: str, bad_name: str):
    with SQLiteConnector(sqlite_path) as conn, pytest.raises(ValueError, match="Invalid table"):
        conn.sample_source(bad_name, 10)


@pytest.mark.parametrize(
    "bad_name",
    ["users; drop table x", "users'--", "users(1)"],
    ids=["semicolon", "sql-comment", "parens"],
)
def test_duckdb_sample_source_rejects_unsafe_names(duckdb_path: str, bad_name: str):
    with DuckDBConnector(duckdb_path) as conn, pytest.raises(ValueError, match="Invalid table"):
        conn.sample_source(bad_name, 10)
