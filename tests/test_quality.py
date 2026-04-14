"""Tests for qdo quality command."""

import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_quality_sqlite(sqlite_path: str):
    result = runner.invoke(app, ["quality", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    assert "ok" in result.output.lower()


def test_quality_duckdb(duckdb_path: str):
    result = runner.invoke(app, ["quality", "-c", duckdb_path, "-t", "users"])
    assert result.exit_code == 0
    assert "ok" in result.output.lower()


def test_quality_format_json(sqlite_path: str):
    result = runner.invoke(app, ["-f", "json", "quality", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    assert payload["table"] == "users"
    assert payload["row_count"] == 2
    assert len(payload["columns"]) == 3
    for col in payload["columns"]:
        assert "null_count" in col
        assert "distinct_count" in col
        assert "status" in col


def test_quality_format_csv(sqlite_path: str):
    result = runner.invoke(app, ["-f", "csv", "quality", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    assert "column" in result.output
    assert "null_count" in result.output


def test_quality_format_markdown(sqlite_path: str):
    result = runner.invoke(app, ["-f", "markdown", "quality", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    assert "| Column" in result.output


def test_quality_with_nulls(tmp_path: Path):
    """Columns with high null rates should get warn/fail status."""
    db_path = str(tmp_path / "nulls.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER, name TEXT, notes TEXT)")
    for i in range(10):
        name = f"user_{i}" if i < 8 else None
        conn.execute("INSERT INTO t VALUES (?, ?, NULL)", (i, name))
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["-f", "json", "quality", "-c", db_path, "-t", "t"])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    by_name = {c["name"]: c for c in payload["columns"]}

    # notes is 100% null → fail
    assert by_name["notes"]["status"] == "fail"
    assert by_name["notes"]["null_pct"] == 100.0

    # name is 20% null → warn
    assert by_name["name"]["null_pct"] == 20.0

    # id is 0% null → ok
    assert by_name["id"]["null_pct"] == 0.0
    assert by_name["id"]["status"] == "ok"


def test_quality_column_filter(sqlite_path: str):
    result = runner.invoke(
        app,
        ["-f", "json", "quality", "-c", sqlite_path, "-t", "users", "--columns", "name,age"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    col_names = [c["name"] for c in payload["columns"]]
    assert "name" in col_names
    assert "age" in col_names
    assert "id" not in col_names


def test_quality_check_duplicates_none(sqlite_path: str):
    """No duplicates in standard test table."""
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "quality",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "--check-duplicates",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    assert payload["duplicate_rows"] == 0


def test_quality_check_duplicates_found(tmp_path: Path):
    db_path = str(tmp_path / "dupes.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (name TEXT, value INTEGER)")
    conn.execute("INSERT INTO t VALUES ('a', 1)")
    conn.execute("INSERT INTO t VALUES ('a', 1)")  # duplicate
    conn.execute("INSERT INTO t VALUES ('a', 1)")  # duplicate
    conn.execute("INSERT INTO t VALUES ('b', 2)")
    conn.commit()
    conn.close()

    result = runner.invoke(
        app,
        ["-f", "json", "quality", "-c", db_path, "-t", "t", "--check-duplicates"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    assert payload["duplicate_rows"] == 2  # 3 copies - 1 = 2 extra


def test_quality_no_duplicates_flag_means_null(sqlite_path: str):
    """Without --check-duplicates, duplicate_rows should be null."""
    result = runner.invoke(app, ["-f", "json", "quality", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    assert payload["duplicate_rows"] is None


def test_quality_uniqueness(sqlite_path: str):
    """Each user has unique id/name/age so uniqueness should be 100%."""
    result = runner.invoke(app, ["-f", "json", "quality", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    by_name = {c["name"]: c for c in payload["columns"]}
    assert by_name["id"]["uniqueness_pct"] == 100.0
    assert by_name["name"]["uniqueness_pct"] == 100.0
