"""Tests for qdo quality command."""

import json
import sqlite3
from pathlib import Path
from typing import cast

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
    payload = json.loads(result.output)["data"]
    assert payload["table"] == "users"
    assert payload["row_count"] == 2
    assert len(payload["columns"]) == 3
    for col in payload["columns"]:
        assert "null_count" in col
        assert "distinct_count" in col
        assert "status" in col
        assert "signals" in col


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
    """High null rates are descriptive unless metadata declares a constraint."""
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
    payload = json.loads(result.output)["data"]
    by_name = {c["name"]: c for c in payload["columns"]}

    # notes is 100% null, but no contract says that is invalid.
    assert by_name["notes"]["status"] == "ok"
    assert by_name["notes"]["null_pct"] == 100.0
    assert "100.0% null" in by_name["notes"]["signals"]
    assert by_name["notes"]["issues"] == []

    # name is 20% null and remains an observed metric.
    assert by_name["name"]["null_pct"] == 20.0
    assert by_name["name"]["status"] == "ok"

    # id is 0% null → ok
    assert by_name["id"]["null_pct"] == 0.0
    assert by_name["id"]["status"] == "ok"


def test_quality_column_filter(sqlite_path: str):
    result = runner.invoke(
        app,
        ["-f", "json", "quality", "-c", sqlite_path, "-t", "users", "--columns", "name,age"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)["data"]
    col_names = [c["name"] for c in payload["columns"]]
    assert "name" in col_names
    assert "age" in col_names
    assert "id" not in col_names


def test_quality_short_C_flag(sqlite_path: str):
    """``-C`` is the short form of ``--columns`` — parity with values/dist (R.8)."""
    result = runner.invoke(
        app,
        ["-f", "json", "quality", "-c", sqlite_path, "-t", "users", "-C", "age"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)["data"]
    col_names = [c["name"] for c in payload["columns"]]
    assert col_names == ["age"]


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
    payload = json.loads(result.output)["data"]
    assert payload["duplicate_rows"] == 2  # 3 copies - 1 = 2 extra


def test_quality_no_duplicates_flag_means_null(sqlite_path: str):
    """Without --check-duplicates, duplicate_rows should be null."""
    result = runner.invoke(app, ["-f", "json", "quality", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    payload = json.loads(result.output)["data"]
    assert payload["duplicate_rows"] is None


def test_quality_uniqueness(sqlite_path: str):
    """Each user has unique id/name/age so uniqueness should be 100%."""
    result = runner.invoke(app, ["-f", "json", "quality", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    payload = json.loads(result.output)["data"]
    by_name = {c["name"]: c for c in payload["columns"]}
    assert by_name["id"]["uniqueness_pct"] == 100.0
    assert by_name["name"]["uniqueness_pct"] == 100.0


def test_quality_low_cardinality_is_a_signal_not_a_violation(tmp_path: Path) -> None:
    """Healthy enum-like columns must not fail a generic uniqueness heuristic."""
    db_path = str(tmp_path / "enums.db")
    with sqlite3.connect(db_path) as connection:
        connection.execute("create table events (id integer, active integer)")
        connection.executemany(
            "insert into events values (?, ?)",
            [(index, index % 2) for index in range(1000)],
        )

    result = runner.invoke(app, ["-f", "json", "quality", "-c", db_path, "-t", "events"])
    assert result.exit_code == 0, result.output
    columns = {col["name"]: col for col in json.loads(result.output)["data"]["columns"]}
    active = columns["active"]
    assert active["status"] == "ok"
    assert active["issues"] == []
    assert active["signals"] == ["0.2% unique"]


def test_compute_column_quality_clamps_approx_distinct_to_row_count() -> None:
    """Approximate distinct estimates should not surface impossible counts."""
    from querido.connectors.base import Connector
    from querido.core.quality import _compute_column_quality

    class FakeConnector:
        def execute(self, sql: str) -> list[dict]:
            return [
                {
                    "_total_rows": 5,
                    "id_nulls": 0,
                    "id_distinct": 7,
                    "id_min": 1,
                    "id_max": 5,
                }
            ]

    columns = [{"name": "id", "type": "INTEGER"}]
    result, row_count = _compute_column_quality(
        cast(Connector, FakeConnector()), "orders", columns, approx=True
    )
    assert row_count == 5
    assert result[0]["distinct_count"] == 5
    assert result[0]["uniqueness_pct"] == 100.0


def test_print_quality_rich_summary_uses_status_counts() -> None:
    """Rich quality output should include a compact summary before the detail table."""
    from rich.console import Console

    from querido.output.console import print_quality

    console = Console(record=True, width=120)
    print_quality(
        {
            "table": "orders",
            "row_count": 1000,
            "sampled": False,
            "sample_size": None,
            "duplicate_rows": 3,
            "columns": [
                {
                    "name": "id",
                    "type": "INTEGER",
                    "null_count": 0,
                    "null_pct": 0.0,
                    "distinct_count": 1000,
                    "uniqueness_pct": 100.0,
                    "status": "ok",
                    "signals": [],
                    "issues": [],
                },
                {
                    "name": "status",
                    "type": "TEXT",
                    "null_count": 200,
                    "null_pct": 20.0,
                    "distinct_count": 4,
                    "uniqueness_pct": 0.4,
                    "status": "ok",
                    "signals": ["20.0% null", "0.4% unique"],
                    "issues": [],
                },
                {
                    "name": "notes",
                    "type": "TEXT",
                    "null_count": 1000,
                    "null_pct": 100.0,
                    "distinct_count": 0,
                    "uniqueness_pct": 0.0,
                    "status": "fail",
                    "signals": ["100.0% null", "0 distinct values (all null)"],
                    "issues": ["3 values not in valid_values"],
                },
            ],
        },
        console=console,
    )
    text = console.export_text()
    assert "Quality Summary" in text
    assert "2 ok" in text.lower()
    assert "0 warn" in text.lower()
    assert "1 fail" in text.lower()
    assert "3 duplicate rows" in text.lower()
    assert "Column Detail" in text


def test_print_quality_rich_sample_note() -> None:
    """Rich quality output should surface sampling context."""
    from rich.console import Console

    from querido.output.console import print_quality

    console = Console(record=True, width=120)
    print_quality(
        {
            "table": "users",
            "row_count": 50000,
            "sampled": True,
            "sample_size": 1000,
            "duplicate_rows": None,
            "columns": [
                {
                    "name": "email",
                    "type": "TEXT",
                    "null_count": 0,
                    "null_pct": 0.0,
                    "distinct_count": 50000,
                    "uniqueness_pct": 100.0,
                    "status": "ok",
                    "signals": [],
                    "issues": [],
                }
            ],
        },
        console=console,
    )
    text = console.export_text()
    assert "sampled 1,000" in text.lower()
    assert "use --no-sample for exact results" in text.lower()
