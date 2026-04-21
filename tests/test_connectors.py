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
