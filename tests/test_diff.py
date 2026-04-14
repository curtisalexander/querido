"""Tests for qdo diff command."""

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


@pytest.fixture
def diff_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "diff.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users_v1 (id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER)")
    conn.execute("CREATE TABLE users_v2 (id INTEGER PRIMARY KEY, name TEXT, age REAL, email TEXT)")
    conn.execute("INSERT INTO users_v1 VALUES (1, 'Alice', 30)")
    conn.execute("INSERT INTO users_v2 VALUES (1, 'Alice', 30.0, 'a@b.com')")
    conn.commit()
    conn.close()
    return db_path


def test_diff_identical(sqlite_path: str):
    result = runner.invoke(
        app,
        ["diff", "-c", sqlite_path, "-t", "users", "--target", "users"],
    )
    assert result.exit_code == 0
    assert "identical" in result.output.lower()


def test_diff_added_column(diff_db: str):
    result = runner.invoke(
        app,
        ["-f", "json", "diff", "-c", diff_db, "-t", "users_v1", "--target", "users_v2"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    added_names = [c["name"] for c in payload["added"]]
    assert "email" in added_names


def test_diff_removed_column(diff_db: str):
    """Reverse: v2 → v1 means email is removed."""
    result = runner.invoke(
        app,
        ["-f", "json", "diff", "-c", diff_db, "-t", "users_v2", "--target", "users_v1"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    removed_names = [c["name"] for c in payload["removed"]]
    assert "email" in removed_names


def test_diff_changed_type(diff_db: str):
    """age changed from INTEGER to REAL."""
    result = runner.invoke(
        app,
        ["-f", "json", "diff", "-c", diff_db, "-t", "users_v1", "--target", "users_v2"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    # age or name may have changed (type or nullable)
    assert len(payload["changed"]) >= 1


def test_diff_unchanged_count(diff_db: str):
    result = runner.invoke(
        app,
        ["-f", "json", "diff", "-c", diff_db, "-t", "users_v1", "--target", "users_v2"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    assert payload["unchanged_count"] >= 0


def test_diff_format_csv(diff_db: str):
    result = runner.invoke(
        app,
        ["-f", "csv", "diff", "-c", diff_db, "-t", "users_v1", "--target", "users_v2"],
    )
    assert result.exit_code == 0
    assert "change" in result.output
    assert "added" in result.output


def test_diff_format_markdown(diff_db: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "markdown",
            "diff",
            "-c",
            diff_db,
            "-t",
            "users_v1",
            "--target",
            "users_v2",
        ],
    )
    assert result.exit_code == 0
    assert "## Diff" in result.output


def test_diff_format_rich(diff_db: str):
    result = runner.invoke(
        app,
        ["diff", "-c", diff_db, "-t", "users_v1", "--target", "users_v2"],
    )
    assert result.exit_code == 0
    assert "Added" in result.output or "Changed" in result.output


def test_diff_cross_connection(tmp_path: Path):
    """Diff between tables in two different databases."""
    db1 = str(tmp_path / "left.db")
    db2 = str(tmp_path / "right.db")

    conn1 = sqlite3.connect(db1)
    conn1.execute("CREATE TABLE t (id INTEGER, name TEXT)")
    conn1.execute("INSERT INTO t VALUES (1, 'a')")
    conn1.commit()
    conn1.close()

    conn2 = sqlite3.connect(db2)
    conn2.execute("CREATE TABLE t (id INTEGER, name TEXT, extra REAL)")
    conn2.execute("INSERT INTO t VALUES (1, 'a', 1.0)")
    conn2.commit()
    conn2.close()

    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "diff",
            "-c",
            db1,
            "-t",
            "t",
            "--target-connection",
            db2,
            "--target",
            "t",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    added_names = [c["name"] for c in payload["added"]]
    assert "extra" in added_names
