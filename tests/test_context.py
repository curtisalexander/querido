"""Tests for qdo context command."""

from __future__ import annotations

import json
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
    db_path = str(tmp_path / "context_test.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE orders ("
        "id INTEGER PRIMARY KEY, "
        "status TEXT NOT NULL, "
        "amount REAL, "
        "customer TEXT"
        ")"
    )
    conn.execute("INSERT INTO orders VALUES (1, 'shipped', 99.99, 'Alice')")
    conn.execute("INSERT INTO orders VALUES (2, 'pending', 49.50, 'Bob')")
    conn.execute("INSERT INTO orders VALUES (3, 'shipped', 25.00, 'Alice')")
    conn.execute("INSERT INTO orders VALUES (4, 'cancelled', NULL, 'Charlie')")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def duckdb_path(tmp_path: Path) -> str:
    import duckdb

    db_path = str(tmp_path / "context_test.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute(
        "CREATE TABLE orders ("
        "id INTEGER PRIMARY KEY, "
        "status VARCHAR NOT NULL, "
        "amount DOUBLE, "
        "customer VARCHAR"
        ")"
    )
    conn.execute("INSERT INTO orders VALUES (1, 'shipped', 99.99, 'Alice')")
    conn.execute("INSERT INTO orders VALUES (2, 'pending', 49.50, 'Bob')")
    conn.execute("INSERT INTO orders VALUES (3, 'shipped', 25.00, 'Alice')")
    conn.execute("INSERT INTO orders VALUES (4, 'cancelled', NULL, 'Charlie')")
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# SQLite — Rich output
# ---------------------------------------------------------------------------


def test_context_sqlite_rich(sqlite_path: str) -> None:
    result = runner.invoke(app, ["context", "-c", sqlite_path, "-t", "orders"])
    assert result.exit_code == 0, result.output
    assert "orders" in result.output


def test_context_sqlite_json(sqlite_path: str) -> None:
    result = runner.invoke(app, ["--format", "json", "context", "-c", sqlite_path, "-t", "orders"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert data["table"] == "orders"
    assert data["dialect"] == "sqlite"
    assert data["row_count"] == 4
    cols = {c["name"]: c for c in data["columns"]}
    assert "id" in cols
    assert "status" in cols
    assert "amount" in cols
    # null_pct should be computed
    assert cols["amount"]["null_pct"] == 25.0
    # id is numeric — no sample_values
    assert cols["id"]["sample_values"] is None
    # status sample values should contain the unique statuses
    assert cols["status"]["sample_values"] is not None


def test_context_sqlite_json_no_sample_values(sqlite_path: str) -> None:
    result = runner.invoke(
        app,
        ["--format", "json", "context", "-c", sqlite_path, "-t", "orders", "--sample-values", "0"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    for col in data["columns"]:
        assert col["sample_values"] is None


def test_context_sqlite_markdown(sqlite_path: str) -> None:
    result = runner.invoke(
        app, ["--format", "markdown", "context", "-c", sqlite_path, "-t", "orders"]
    )
    assert result.exit_code == 0
    assert "## Context: orders" in result.output
    assert "status" in result.output


def test_context_sqlite_csv(sqlite_path: str) -> None:
    result = runner.invoke(app, ["--format", "csv", "context", "-c", sqlite_path, "-t", "orders"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert "column" in lines[0]
    assert len(lines) > 1  # header + at least one row


# ---------------------------------------------------------------------------
# DuckDB — single-scan path with approx_top_k
# ---------------------------------------------------------------------------


def test_context_duckdb_rich(duckdb_path: str) -> None:
    result = runner.invoke(app, ["context", "-c", duckdb_path, "-t", "orders"])
    assert result.exit_code == 0, result.output
    assert "orders" in result.output


def test_context_duckdb_json(duckdb_path: str) -> None:
    result = runner.invoke(app, ["--format", "json", "context", "-c", duckdb_path, "-t", "orders"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert data["table"] == "orders"
    assert data["dialect"] == "duckdb"
    assert data["row_count"] == 4
    cols = {c["name"]: c for c in data["columns"]}
    # amount has one null out of 4 rows
    assert cols["amount"]["null_pct"] == 25.0
    # status should have sample values from approx_top_k
    assert cols["status"]["sample_values"] is not None
    assert len(cols["status"]["sample_values"]) > 0
    # amount is numeric — no sample values
    assert cols["amount"]["sample_values"] is None


def test_context_honors_show_sql_sqlite(sqlite_path: str) -> None:
    """R.12: ``context`` should print rendered SQL to stderr under ``--show-sql``."""
    result = runner.invoke(app, ["--show-sql", "context", "-c", sqlite_path, "-t", "orders"])
    assert result.exit_code == 0, result.output
    # The SQLite context path uses the profile template, which does null_count /
    # min / max aggregations — distinctive enough to prove SQL was emitted.
    blob = result.output.lower()
    assert "select" in blob
    assert "from " in blob


def test_context_honors_show_sql_duckdb(duckdb_path: str) -> None:
    """R.12: same contract on the DuckDB approx_top_k single-scan path."""
    result = runner.invoke(app, ["--show-sql", "context", "-c", duckdb_path, "-t", "orders"])
    assert result.exit_code == 0, result.output
    blob = result.output.lower()
    assert "approx_top_k" in blob or "select" in blob


def test_context_envelope_carries_sql_field(sqlite_path: str) -> None:
    """The rendered SQL is threaded through the envelope's ``data`` for
    agents that want to understand what ran (consistent with ``pivot``)."""
    result = runner.invoke(app, ["-f", "json", "context", "-c", sqlite_path, "-t", "orders"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["data"]
    assert data["sql"]
    assert "select" in data["sql"].lower()


def test_context_duckdb_json_no_sample_values(duckdb_path: str) -> None:
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "context",
            "-c",
            duckdb_path,
            "-t",
            "orders",
            "--sample-values",
            "0",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    # When sample_values=0, no top_values computed but stats still present
    cols = {c["name"]: c for c in data["columns"]}
    assert cols["status"]["sample_values"] is None
    # Stats should still be present
    assert cols["amount"]["null_pct"] == 25.0


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_context_missing_table_arg(sqlite_path: str) -> None:
    result = runner.invoke(app, ["context", "-c", sqlite_path])
    assert result.exit_code != 0


def test_context_nonexistent_table(sqlite_path: str) -> None:
    result = runner.invoke(app, ["context", "-c", sqlite_path, "-t", "no_such_table"])
    assert result.exit_code != 0


def test_context_invalid_table_name(sqlite_path: str) -> None:
    result = runner.invoke(app, ["context", "-c", sqlite_path, "-t", "'; DROP TABLE--"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# core.context unit tests
# ---------------------------------------------------------------------------


def test_get_context_sqlite(sqlite_path: str) -> None:
    from querido.connectors.sqlite import SQLiteConnector
    from querido.core.context import get_context

    with SQLiteConnector(sqlite_path) as conn:
        result = get_context(conn, "orders", sqlite_path, sample_values=3)

    assert result["table"] == "orders"
    assert result["dialect"] == "sqlite"
    assert result["row_count"] == 4
    cols = {c["name"]: c for c in result["columns"]}
    assert cols["amount"]["null_pct"] == 25.0
    assert cols["id"]["sample_values"] is None  # numeric
    # status has 3 distinct values, so sample_values should be populated
    status_samples = cols["status"]["sample_values"]
    assert status_samples is not None
    assert len(status_samples) <= 3


def test_get_context_duckdb(duckdb_path: str) -> None:
    from querido.connectors.duckdb import DuckDBConnector
    from querido.core.context import get_context

    with DuckDBConnector(duckdb_path) as conn:
        result = get_context(conn, "orders", duckdb_path, sample_values=5)

    assert result["table"] == "orders"
    assert result["dialect"] == "duckdb"
    assert result["row_count"] == 4
    cols = {c["name"]: c for c in result["columns"]}
    assert cols["amount"]["null_pct"] == 25.0
    # DuckDB uses approx_top_k — sample values should be present
    assert cols["status"]["sample_values"] is not None


def test_get_context_no_sample_values(sqlite_path: str) -> None:
    from querido.connectors.sqlite import SQLiteConnector
    from querido.core.context import get_context

    with SQLiteConnector(sqlite_path) as conn:
        result = get_context(conn, "orders", sqlite_path, sample_values=0)

    for col in result["columns"]:
        assert col["sample_values"] is None


def test_get_context_no_sample_flag(sqlite_path: str) -> None:
    from querido.connectors.sqlite import SQLiteConnector
    from querido.core.context import get_context

    with SQLiteConnector(sqlite_path) as conn:
        result = get_context(conn, "orders", sqlite_path, no_sample=True)

    assert result["sampled"] is False
    assert result["row_count"] == 4
