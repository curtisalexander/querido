import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


@pytest.fixture
def dist_sqlite(tmp_path: Path) -> str:
    db_path = str(tmp_path / "dist.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE sales (id INTEGER PRIMARY KEY, amount REAL, category TEXT, notes TEXT)"
    )
    rows = []
    for i in range(100):
        if i < 40:
            amount = 10.0 + i * 0.5
            category = "electronics"
        elif i < 70:
            amount = 50.0 + i * 0.3
            category = "clothing"
        elif i < 90:
            amount = 80.0 + i * 0.1
            category = "food"
        else:
            amount = 100.0 + i * 0.2
            category = "other"
        rows.append((amount, category, f"note-{i}"))
    rows.append((None, None, None))
    rows.append((None, None, None))
    conn.executemany("INSERT INTO sales (amount, category, notes) VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def dist_duckdb(tmp_path: Path) -> str:
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


@pytest.fixture
def single_value_sqlite(tmp_path: Path) -> str:
    db_path = str(tmp_path / "single.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE mono (id INTEGER PRIMARY KEY, val REAL, label TEXT)")
    for _i in range(10):
        conn.execute("INSERT INTO mono (val, label) VALUES (?, ?)", (42.0, "same"))
    conn.commit()
    conn.close()
    return db_path


# -- Numeric distribution (SQLite) -------------------------------------------


def test_dist_numeric_sqlite(dist_sqlite: str):
    result = runner.invoke(
        app, ["dist", "-t", "sales", "-C", "amount", "-c", dist_sqlite, "-b", "5"]
    )
    assert result.exit_code == 0
    assert "Distribution" in result.output
    assert "amount" in result.output
    assert " - " in result.output


def test_dist_numeric_buckets_count(dist_sqlite: str):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "dist",
            "-t",
            "sales",
            "-C",
            "amount",
            "-c",
            dist_sqlite,
            "-b",
            "5",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["mode"] == "numeric"
    assert len(data["buckets"]) <= 5
    assert data["null_count"] == 2


# -- Categorical distribution (SQLite) ---------------------------------------


def test_dist_categorical_sqlite(dist_sqlite: str):
    result = runner.invoke(app, ["dist", "-t", "sales", "-C", "category", "-c", dist_sqlite])
    assert result.exit_code == 0
    assert "Distribution" in result.output
    assert "electronics" in result.output
    assert "clothing" in result.output


def test_dist_categorical_json(dist_sqlite: str):
    result = runner.invoke(
        app,
        ["--format", "json", "dist", "-t", "sales", "-C", "category", "-c", dist_sqlite],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["mode"] == "categorical"
    assert len(data["values"]) > 0
    assert data["values"][0]["value"] == "electronics"


# -- Null handling ------------------------------------------------------------


# -- DuckDB ------------------------------------------------------------------


def test_dist_numeric_duckdb(dist_duckdb: str):
    result = runner.invoke(
        app, ["dist", "-t", "sales", "-C", "amount", "-c", dist_duckdb, "-b", "5"]
    )
    assert result.exit_code == 0
    assert "Distribution" in result.output
    assert " - " in result.output


def test_dist_categorical_duckdb(dist_duckdb: str):
    result = runner.invoke(app, ["dist", "-t", "sales", "-C", "category", "-c", dist_duckdb])
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
            "-C",
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
        ["--format", "csv", "dist", "-t", "sales", "-C", "amount", "-c", dist_sqlite, "-b", "5"],
    )
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert "bucket_min" in lines[0]
    assert "count" in lines[0]


# -- Error cases --------------------------------------------------------------


def test_dist_invalid_column(dist_sqlite: str):
    result = runner.invoke(app, ["dist", "-t", "sales", "-C", "nonexistent", "-c", dist_sqlite])
    assert result.exit_code != 0


def test_dist_bar_chart_has_blocks(dist_sqlite: str):
    result = runner.invoke(
        app, ["dist", "-t", "sales", "-C", "amount", "-c", dist_sqlite, "-b", "5"]
    )
    assert result.exit_code == 0
    assert "\u2588" in result.output


# -- Single value column ------------------------------------------------------


def test_dist_single_value_numeric(single_value_sqlite: str):
    result = runner.invoke(
        app,
        ["--format", "json", "dist", "-t", "mono", "-C", "val", "-c", single_value_sqlite],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["mode"] == "numeric"


def test_print_dist_rich_summary() -> None:
    """Rich distribution output should summarize mode, bucket/value count, and nulls."""
    from rich.console import Console

    from querido.output.console import print_dist

    console = Console(record=True, width=120)
    print_dist(
        {
            "table": "sales",
            "column": "category",
            "mode": "categorical",
            "total_rows": 102,
            "null_count": 2,
            "values": [
                {"value": "electronics", "count": 40},
                {"value": "clothing", "count": 30},
                {"value": "food", "count": 20},
                {"value": "other", "count": 10},
            ],
        },
        console=console,
    )
    text = console.export_text()
    assert "Distribution Summary" in text
    assert "4 values" in text
    assert "100 non-null rows" in text
    assert "2 nulls" in text
    assert "Distribution Detail" in text


def test_dist_single_value_categorical(single_value_sqlite: str):
    result = runner.invoke(
        app,
        ["--format", "json", "dist", "-t", "mono", "-C", "label", "-c", single_value_sqlite],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["mode"] == "categorical"
    assert len(data["values"]) == 1
    assert data["values"][0]["value"] == "same"


# -- Top flag -----------------------------------------------------------------


def test_dist_categorical_top_1(dist_sqlite: str):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "dist",
            "-t",
            "sales",
            "-C",
            "category",
            "-c",
            dist_sqlite,
            "--top",
            "1",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["mode"] == "categorical"
    assert len(data["values"]) == 1
    assert data["values"][0]["value"] == "electronics"


def test_dist_empty_table(tmp_path: Path):
    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE empty_t (id INTEGER PRIMARY KEY, name TEXT NOT NULL, score REAL)")
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["dist", "-c", db_path, "-t", "empty_t", "-C", "score"])
    assert result.exit_code == 0


def test_dist_long_flag_works(dist_sqlite: str):
    """``--columns`` (long form) is the canonical name post-R.8."""
    result = runner.invoke(app, ["dist", "-c", dist_sqlite, "-t", "sales", "--columns", "amount"])
    assert result.exit_code == 0


def test_dist_rejects_multi_column_list(dist_sqlite: str):
    """``qdo dist`` visualizes one column; a CSV of length > 1 is a clear error."""
    result = runner.invoke(
        app, ["dist", "-c", dist_sqlite, "-t", "sales", "--columns", "amount,category"]
    )
    assert result.exit_code != 0
    assert "exactly one column" in result.output
