import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_values_sqlite(sqlite_path: str):
    result = runner.invoke(
        app, ["values", "-c", sqlite_path, "-t", "users", "-C", "name"]
    )
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_values_duckdb(duckdb_path: str):
    result = runner.invoke(
        app, ["values", "-c", duckdb_path, "-t", "users", "-C", "name"]
    )
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_values_format_json(sqlite_path: str):
    result = runner.invoke(
        app, ["-f", "json", "values", "-c", sqlite_path, "-t", "users", "-C", "name"]
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["column"] == "name"
    assert payload["distinct_count"] == 2
    assert payload["truncated"] is False
    vals = [v["value"] for v in payload["values"]]
    assert "Alice" in vals
    assert "Bob" in vals


def test_values_format_csv(sqlite_path: str):
    result = runner.invoke(
        app, ["-f", "csv", "values", "-c", sqlite_path, "-t", "users", "-C", "name"]
    )
    assert result.exit_code == 0
    assert "value,count" in result.output
    assert "Alice" in result.output


def test_values_format_markdown(sqlite_path: str):
    result = runner.invoke(
        app,
        ["-f", "markdown", "values", "-c", sqlite_path, "-t", "users", "-C", "name"],
    )
    assert result.exit_code == 0
    assert "| Value" in result.output
    assert "Alice" in result.output


def test_values_sort_frequency(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "-f", "json", "values", "-c", sqlite_path,
            "-t", "users", "-C", "name", "--sort", "frequency",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    # Both have count 1, so order doesn't matter much
    assert len(payload["values"]) == 2


def test_values_truncated(tmp_path: Path):
    """When distinct count exceeds --max, result should be truncated."""
    db_path = str(tmp_path / "many.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, label TEXT)")
    for i in range(50):
        conn.execute("INSERT INTO items VALUES (?, ?)", (i, f"item_{i:03d}"))
    conn.commit()
    conn.close()

    result = runner.invoke(
        app,
        ["-f", "json", "values", "-c", db_path, "-t", "items", "-C", "label", "--max", "10"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["distinct_count"] == 50
    assert payload["truncated"] is True
    assert len(payload["values"]) == 10


def test_values_with_nulls(tmp_path: Path):
    db_path = str(tmp_path / "nulls.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER, status TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'active')")
    conn.execute("INSERT INTO t VALUES (2, NULL)")
    conn.execute("INSERT INTO t VALUES (3, 'inactive')")
    conn.execute("INSERT INTO t VALUES (4, NULL)")
    conn.commit()
    conn.close()

    result = runner.invoke(
        app, ["-f", "json", "values", "-c", db_path, "-t", "t", "-C", "status"]
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["null_count"] == 2
    assert payload["distinct_count"] == 2
    # Values should not include NULLs (they're counted separately)
    vals = [v["value"] for v in payload["values"]]
    assert None not in vals
    assert "active" in vals
    assert "inactive" in vals


def test_values_nonexistent_column(sqlite_path: str):
    result = runner.invoke(
        app, ["values", "-c", sqlite_path, "-t", "users", "-C", "nonexistent"]
    )
    assert result.exit_code != 0


def test_values_invalid_sort(sqlite_path: str):
    result = runner.invoke(
        app,
        ["values", "-c", sqlite_path, "-t", "users", "-C", "name", "--sort", "bad"],
    )
    assert result.exit_code != 0


def test_values_numeric_column(sqlite_path: str):
    """Works with numeric columns too."""
    result = runner.invoke(
        app, ["-f", "json", "values", "-c", sqlite_path, "-t", "users", "-C", "age"]
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    vals = [v["value"] for v in payload["values"]]
    assert 25 in vals
    assert 30 in vals
