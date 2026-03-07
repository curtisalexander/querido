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
