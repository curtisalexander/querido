import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


@pytest.fixture
def cache_sqlite(tmp_path: Path) -> str:
    db_path = str(tmp_path / "cache_test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@test.com')")
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, total REAL)")
    conn.execute("INSERT INTO orders VALUES (1, 1, 99.99)")
    conn.execute("CREATE VIEW user_summary AS SELECT id, name FROM users")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def cache_duckdb(tmp_path: Path) -> str:
    import duckdb

    db_path = str(tmp_path / "cache_test.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE products (id INTEGER, name VARCHAR, price DOUBLE)")
    conn.execute("INSERT INTO products VALUES (1, 'Widget', 9.99)")
    conn.close()
    return db_path


# -- MetadataCache unit tests -------------------------------------------------


def test_cache_sync_and_search(tmp_path: Path, cache_sqlite: str):
    from querido.cache import MetadataCache
    from querido.connectors.sqlite import SQLiteConnector

    cache_path = tmp_path / "test_cache.db"

    with MetadataCache(cache_path) as cache, SQLiteConnector(cache_sqlite) as conn:
        summary = cache.sync("test-conn", conn)

        assert summary["tables"] == 3  # users, orders, user_summary view
        assert summary["columns"] > 0
        assert summary["elapsed"] >= 0

        # Search by table name
        results = cache.search("test-conn", "user", "table")
        table_names = [r["table_name"] for r in results]
        assert "users" in table_names
        assert "user_summary" in table_names

        # Search by column name
        results = cache.search("test-conn", "email", "column")
        assert len(results) == 1
        assert results[0]["column_name"] == "email"
        assert results[0]["table_name"] == "users"

        # Search all
        results = cache.search("test-conn", "name", "all")
        assert len(results) > 0


def test_cache_status(tmp_path: Path, cache_sqlite: str):
    from querido.cache import MetadataCache
    from querido.connectors.sqlite import SQLiteConnector

    cache_path = tmp_path / "test_cache.db"

    with MetadataCache(cache_path) as cache, SQLiteConnector(cache_sqlite) as conn:
        cache.sync("my-db", conn)
        entries = cache.status()

        assert len(entries) == 1
        assert entries[0]["connection"] == "my-db"
        assert entries[0]["tables"] == 3
        assert entries[0]["columns"] > 0
        assert entries[0]["age_hours"] is not None

        # Status for specific connection
        entries = cache.status("my-db")
        assert len(entries) == 1

        # Status for non-existent connection
        entries = cache.status("no-such")
        assert len(entries) == 0


def test_cache_clear(tmp_path: Path, cache_sqlite: str):
    from querido.cache import MetadataCache
    from querido.connectors.sqlite import SQLiteConnector

    cache_path = tmp_path / "test_cache.db"

    with MetadataCache(cache_path) as cache, SQLiteConnector(cache_sqlite) as conn:
        cache.sync("db1", conn)
        cache.sync("db2", conn)

        # Clear specific connection
        count = cache.clear("db1")
        assert count == 3
        assert len(cache.status("db1")) == 0
        assert len(cache.status("db2")) == 1

        # Clear all
        count = cache.clear()
        assert count == 3
        assert len(cache.status()) == 0


def test_cache_is_fresh(tmp_path: Path, cache_sqlite: str):
    from querido.cache import MetadataCache
    from querido.connectors.sqlite import SQLiteConnector

    cache_path = tmp_path / "test_cache.db"

    with MetadataCache(cache_path) as cache, SQLiteConnector(cache_sqlite) as conn:
        # Empty cache is not fresh
        assert not cache.is_fresh("test-conn")

        cache.sync("test-conn", conn)

        # Just synced, should be fresh
        assert cache.is_fresh("test-conn")

        # With a tiny TTL, should be stale
        assert not cache.is_fresh("test-conn", ttl_seconds=0)


def test_cache_re_sync_overwrites(tmp_path: Path, cache_sqlite: str):
    from querido.cache import MetadataCache
    from querido.connectors.sqlite import SQLiteConnector

    cache_path = tmp_path / "test_cache.db"

    with MetadataCache(cache_path) as cache, SQLiteConnector(cache_sqlite) as conn:
        cache.sync("test-conn", conn)
        first = cache.status("test-conn")
        assert first[0]["tables"] == 3

        # Re-sync should overwrite cleanly
        cache.sync("test-conn", conn)
        second = cache.status("test-conn")
        assert second[0]["tables"] == 3


def test_sync_tables_only(tmp_path: Path, cache_sqlite: str):
    from querido.cache import MetadataCache
    from querido.connectors.sqlite import SQLiteConnector

    cache_path = tmp_path / "test_cache.db"

    with MetadataCache(cache_path) as cache, SQLiteConnector(cache_sqlite) as conn:
        count = cache.sync_tables_only("test-conn", conn)
        assert count == 3  # users, orders, user_summary

        # Cache should be fresh
        assert cache.is_fresh("test-conn")

        # Table lookup should work
        assert cache.has_table("test-conn", "users") is True
        assert cache.has_table("test-conn", "nonexistent") is False

        # Columns should NOT be cached (tables-only sync)
        assert cache.get_cached_columns("test-conn", "users") is None


def test_has_table_and_get_cached(tmp_path: Path, cache_sqlite: str):
    from querido.cache import MetadataCache
    from querido.connectors.sqlite import SQLiteConnector

    cache_path = tmp_path / "test_cache.db"

    with MetadataCache(cache_path) as cache, SQLiteConnector(cache_sqlite) as conn:
        # Empty cache returns None (not False)
        assert cache.has_table("test-conn", "users") is None

        cache.sync("test-conn", conn)

        # Full sync populates both tables and columns
        assert cache.has_table("test-conn", "users") is True
        assert cache.has_table("test-conn", "orders") is True
        assert cache.has_table("test-conn", "nope") is False

        cols = cache.get_cached_columns("test-conn", "users")
        assert cols is not None
        col_names = [c["name"] for c in cols]
        assert "id" in col_names
        assert "name" in col_names

        tables = cache.get_cached_tables("test-conn")
        assert tables is not None
        assert len(tables) == 3


# -- CLI command tests --------------------------------------------------------


def test_cli_cache_sync(cache_sqlite: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QDO_CONFIG", str(tmp_path))
    result = runner.invoke(app, ["cache", "sync", "-c", cache_sqlite])
    assert result.exit_code == 0
    assert "Cached" in result.output or "cached" in result.output.lower()


def test_cli_cache_status_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QDO_CONFIG", str(tmp_path))
    result = runner.invoke(app, ["cache", "status"])
    assert result.exit_code == 0


def test_cli_cache_status_after_sync(
    cache_sqlite: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("QDO_CONFIG", str(tmp_path))
    runner.invoke(app, ["cache", "sync", "-c", cache_sqlite])
    result = runner.invoke(app, ["cache", "status"])
    assert result.exit_code == 0
    assert cache_sqlite in result.output or "tables" in result.output.lower()


def test_cli_cache_status_json(cache_sqlite: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QDO_CONFIG", str(tmp_path))
    runner.invoke(app, ["cache", "sync", "-c", cache_sqlite])
    result = runner.invoke(app, ["--format", "json", "cache", "status"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "entries" in data


def test_cli_cache_clear(cache_sqlite: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QDO_CONFIG", str(tmp_path))
    runner.invoke(app, ["cache", "sync", "-c", cache_sqlite])
    result = runner.invoke(app, ["cache", "clear"])
    assert result.exit_code == 0
    assert "Cleared" in result.output or "cleared" in result.output.lower()


def test_cli_cache_clear_specific(
    cache_sqlite: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("QDO_CONFIG", str(tmp_path))
    runner.invoke(app, ["cache", "sync", "-c", cache_sqlite])
    result = runner.invoke(app, ["cache", "clear", "-c", cache_sqlite])
    assert result.exit_code == 0
    assert "Cleared" in result.output


# -- Search with cache integration -------------------------------------------


def test_search_uses_cache(cache_sqlite: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QDO_CONFIG", str(tmp_path))
    # First sync the cache
    runner.invoke(app, ["cache", "sync", "-c", cache_sqlite])
    # Search should use cache (won't error even if we search)
    result = runner.invoke(
        app,
        ["--format", "json", "search", "-p", "user", "-c", cache_sqlite],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["results"]) > 0


def test_search_no_cache_flag(cache_sqlite: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QDO_CONFIG", str(tmp_path))
    result = runner.invoke(
        app,
        ["--format", "json", "search", "-p", "user", "-c", cache_sqlite, "--no-cache"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data["results"]) > 0


# -- DuckDB cache tests -------------------------------------------------------


def test_cache_sync_duckdb(cache_duckdb: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QDO_CONFIG", str(tmp_path))
    result = runner.invoke(app, ["cache", "sync", "-c", cache_duckdb])
    assert result.exit_code == 0
    assert "Cached" in result.output
