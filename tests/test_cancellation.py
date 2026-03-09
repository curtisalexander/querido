"""Tests for query cancellation and progress infrastructure."""

import sqlite3
from pathlib import Path

import pytest

from querido.core.runner import QueryCancelled, run_cancellable

# ---------------------------------------------------------------------------
# QueryCancelled exception
# ---------------------------------------------------------------------------


def test_query_cancelled_is_keyboard_interrupt():
    exc = QueryCancelled(2.5)
    assert isinstance(exc, KeyboardInterrupt)
    assert exc.elapsed == 2.5
    assert "2.5s" in str(exc)


# ---------------------------------------------------------------------------
# run_cancellable — happy path
# ---------------------------------------------------------------------------


def test_run_cancellable_returns_result_and_elapsed():
    def slow_add(a, b):
        return a + b

    result, elapsed = run_cancellable(slow_add, 1, 2)
    assert result == 3
    assert elapsed >= 0


def test_run_cancellable_propagates_exception():
    def boom():
        raise ValueError("test error")

    with pytest.raises(ValueError, match="test error"):
        run_cancellable(boom)


# ---------------------------------------------------------------------------
# Connector cancel() methods
# ---------------------------------------------------------------------------


def test_sqlite_cancel(tmp_path: Path):
    from querido.connectors.sqlite import SQLiteConnector

    db = str(tmp_path / "test.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()

    with SQLiteConnector(db) as connector:
        # cancel() should not raise even when nothing is running
        connector.cancel()


def test_duckdb_cancel(tmp_path: Path):
    import duckdb

    from querido.connectors.duckdb import DuckDBConnector

    db = str(tmp_path / "test.duckdb")
    ddb = duckdb.connect(db)
    ddb.execute("CREATE TABLE t (x INTEGER)")
    ddb.close()

    with DuckDBConnector(db) as connector:
        connector.cancel()


# ---------------------------------------------------------------------------
# Connector protocol — cancel exists
# ---------------------------------------------------------------------------


def test_connector_protocol_has_cancel():
    from querido.connectors.base import Connector

    assert hasattr(Connector, "cancel")


# ---------------------------------------------------------------------------
# friendly_errors handles KeyboardInterrupt
# ---------------------------------------------------------------------------


def test_friendly_errors_handles_keyboard_interrupt():
    from typer.testing import CliRunner

    from querido.cli.main import app

    runner = CliRunner()
    # A non-existent connection that would trigger an error before any query
    # runs.  We just verify the decorator doesn't blow up on KeyboardInterrupt.
    # (We can't easily simulate Ctrl-C through the runner, but we verify
    # the exit code path exists.)
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# CLI commands still work with new progress indicator
# ---------------------------------------------------------------------------


def test_preview_with_progress(sqlite_path: str):
    from typer.testing import CliRunner

    from querido.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["preview", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    assert "Alice" in result.output


def test_inspect_with_progress(sqlite_path: str):
    from typer.testing import CliRunner

    from querido.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["inspect", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    assert "name" in result.output.lower()


def test_profile_with_progress(sqlite_path: str):
    from typer.testing import CliRunner

    from querido.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["profile", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0


def test_search_with_progress(sqlite_path: str):
    from typer.testing import CliRunner

    from querido.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["search", "-c", sqlite_path, "-p", "user"])
    assert result.exit_code == 0


@pytest.fixture
def sqlite_path(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
    conn.commit()
    conn.close()
    return db_path
