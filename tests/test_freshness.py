import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def _make_freshness_db(path: Path) -> str:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE events (id INTEGER, created_at TEXT, updated_at TEXT, note TEXT)")
    now = datetime.now()
    rows = [
        (
            1,
            (now - timedelta(days=10)).isoformat(timespec="seconds"),
            (now - timedelta(days=1)).isoformat(timespec="seconds"),
            "recent",
        ),
        (
            2,
            (now - timedelta(days=20)).isoformat(timespec="seconds"),
            (now - timedelta(days=3)).isoformat(timespec="seconds"),
            "older",
        ),
        (
            3,
            (now - timedelta(days=30)).isoformat(timespec="seconds"),
            None,
            "missing update",
        ),
    ]
    conn.executemany("INSERT INTO events VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return str(path)


def test_freshness_auto_detects_updated_at(tmp_path: Path) -> None:
    db_path = _make_freshness_db(tmp_path / "freshness.db")
    result = runner.invoke(app, ["-f", "json", "freshness", "-c", db_path, "-t", "events"])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)["data"]
    assert payload["status"] == "fresh"
    assert payload["selected_column"] == "updated_at"
    assert payload["candidate_count"] >= 2
    assert any(c["name"] == "created_at" for c in payload["candidates"])


def test_freshness_explicit_column_override(tmp_path: Path) -> None:
    db_path = _make_freshness_db(tmp_path / "explicit.db")
    result = runner.invoke(
        app,
        ["-f", "json", "freshness", "-c", db_path, "-t", "events", "--column", "created_at"],
    )
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)["data"]
    assert payload["selected_column"] == "created_at"
    assert payload["status"] == "stale"


def test_freshness_no_temporal_columns_is_unknown(tmp_path: Path) -> None:
    db_path = str(tmp_path / "plain.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice')")
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["-f", "json", "freshness", "-c", db_path, "-t", "users"])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)["data"]
    assert payload["status"] == "unknown"
    assert payload["selected_column"] is None
    assert payload["candidate_count"] == 0


def test_freshness_stale_after_threshold(tmp_path: Path) -> None:
    db_path = _make_freshness_db(tmp_path / "stale_after.db")
    result = runner.invoke(
        app,
        ["-f", "json", "freshness", "-c", db_path, "-t", "events", "--stale-after", "0"],
    )
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)["data"]
    assert payload["status"] == "stale"
