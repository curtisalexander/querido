import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


@pytest.fixture
def dist_sqlite(tmp_path: Path) -> str:
    """SQLite database with numeric and text columns for distribution testing."""
    db_path = str(tmp_path / "dist.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE sales (id INTEGER PRIMARY KEY, amount REAL, category TEXT, notes TEXT)"
    )
    # Insert data with known distribution
    rows = []
    for i in range(100):
        if i < 40:
            amount = 10.0 + i * 0.5  # cluster in 10-30 range
            category = "electronics"
        elif i < 70:
            amount = 50.0 + i * 0.3  # cluster in 50-70 range
            category = "clothing"
        elif i < 90:
            amount = 80.0 + i * 0.1  # cluster in 80-90 range
            category = "food"
        else:
            amount = 100.0 + i * 0.2
            category = "other"
        rows.append((amount, category, f"note-{i}"))
    # Add some nulls
    rows.append((None, None, None))
    rows.append((None, None, None))
    conn.executemany("INSERT INTO sales (amount, category, notes) VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def dist_duckdb(tmp_path: Path) -> str:
    """DuckDB database with numeric and text columns for distribution testing."""
    import duckdb

    db_path = str(tmp_path / "dist.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE sales (id INTEGER, amount DOUBLE, category VARCHAR)")
    for i in range(50):
        if i < 20:
            conn.execute("INSERT INTO sales VALUES (?, ?, ?)", [i, 10.0 + i, "electronics"])
        elif i < 35:
            conn.execute("INSERT INTO sales VALUES (?, ?, ?)", [i, 50.0 + i, "clothing"])
        else:
            conn.execute("INSERT INTO sales VALUES (?, ?, ?)", [i, 80.0 + i, "food"])
    conn.execute("INSERT INTO sales VALUES (?, ?, ?)", [99, None, None])
    conn.close()
    return db_path


# -- Numeric distribution (SQLite) -------------------------------------------


def test_dist_numeric_sqlite(dist_sqlite: str):
    result = runner.invoke(
        app, ["dist", "-t", "sales", "-col", "amount", "-c", dist_sqlite, "-b", "5"]
    )
    assert result.exit_code == 0
    assert "Distribution" in result.output
    assert "amount" in result.output
    # Should show bucket ranges
    assert "–" in result.output


def test_dist_numeric_buckets_count(dist_sqlite: str):
    """Should have at most the requested number of buckets."""
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "dist",
            "-t",
            "sales",
            "-col",
            "amount",
            "-c",
            dist_sqlite,
            "-b",
            "5",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["mode"] == "numeric"
    assert len(data["buckets"]) <= 5
    assert data["null_count"] == 2


# -- Categorical distribution (SQLite) ---------------------------------------


def test_dist_categorical_sqlite(dist_sqlite: str):
    result = runner.invoke(app, ["dist", "-t", "sales", "-col", "category", "-c", dist_sqlite])
    assert result.exit_code == 0
    assert "Distribution" in result.output
    assert "electronics" in result.output
    assert "clothing" in result.output


def test_dist_categorical_json(dist_sqlite: str):
    result = runner.invoke(
        app,
        ["--format", "json", "dist", "-t", "sales", "-col", "category", "-c", dist_sqlite],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["mode"] == "categorical"
    assert len(data["values"]) > 0
    # electronics has the most rows
    assert data["values"][0]["value"] == "electronics"


# -- Null handling ------------------------------------------------------------


def test_dist_shows_null_count(dist_sqlite: str):
    result = runner.invoke(
        app,
        ["--format", "json", "dist", "-t", "sales", "-col", "amount", "-c", dist_sqlite],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["null_count"] == 2
    assert data["total_rows"] == 102


# -- DuckDB ------------------------------------------------------------------


def test_dist_numeric_duckdb(dist_duckdb: str):
    result = runner.invoke(
        app, ["dist", "-t", "sales", "-col", "amount", "-c", dist_duckdb, "-b", "5"]
    )
    assert result.exit_code == 0
    assert "Distribution" in result.output
    assert "–" in result.output


def test_dist_categorical_duckdb(dist_duckdb: str):
    result = runner.invoke(app, ["dist", "-t", "sales", "-col", "category", "-c", dist_duckdb])
    assert result.exit_code == 0
    assert "electronics" in result.output
    assert "clothing" in result.output


# -- Output formats -----------------------------------------------------------


def test_dist_markdown_format(dist_sqlite: str):
    result = runner.invoke(
        app,
        [
            "--format",
            "markdown",
            "dist",
            "-t",
            "sales",
            "-col",
            "amount",
            "-c",
            dist_sqlite,
            "-b",
            "5",
        ],
    )
    assert result.exit_code == 0
    assert "## Distribution:" in result.output
    assert "| Bucket |" in result.output


def test_dist_csv_format(dist_sqlite: str):
    result = runner.invoke(
        app,
        ["--format", "csv", "dist", "-t", "sales", "-col", "amount", "-c", dist_sqlite, "-b", "5"],
    )
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert "bucket_min" in lines[0]
    assert "count" in lines[0]


# -- Error cases --------------------------------------------------------------


def test_dist_invalid_column(dist_sqlite: str):
    result = runner.invoke(app, ["dist", "-t", "sales", "-col", "nonexistent", "-c", dist_sqlite])
    assert result.exit_code != 0


def test_dist_bar_chart_has_blocks(dist_sqlite: str):
    """Rich output should contain unicode block characters."""
    result = runner.invoke(
        app, ["dist", "-t", "sales", "-col", "amount", "-c", dist_sqlite, "-b", "5"]
    )
    assert result.exit_code == 0
    assert "█" in result.output
