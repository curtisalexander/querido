"""Tests for `qdo metadata score` + `qdo metadata suggest` (Phase 1.4)."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import yaml
from typer.testing import CliRunner

from querido.cli.main import app
from querido.core.metadata_score import (
    _freshness_score,
    peek_score,
    score_connection,
    score_table,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Scoring unit tests
# ---------------------------------------------------------------------------


def test_freshness_full_credit_within_week():
    assert _freshness_score(0.0) == 1.0
    assert _freshness_score(7.0) == 1.0


def test_freshness_decays_to_zero_at_90_days():
    assert _freshness_score(90.0) == 0.0
    assert _freshness_score(120.0) == 0.0
    # Midpoint between 7 and 90 should be ~0.5
    mid = _freshness_score((7 + 90) / 2)
    assert 0.45 < mid < 0.55


def test_score_table_empty_columns():
    meta = {"table": "t", "columns": []}
    result = score_table(meta, mtime=time.time())
    # No columns → desc/vv default to 100%, freshness full
    assert result["score"] == 1.0
    assert result["missing_descriptions"] == []


def test_score_table_no_descriptions():
    meta = {
        "table": "orders",
        "columns": [
            {"name": "id", "type": "INTEGER", "description": "<description>"},
            {"name": "name", "type": "VARCHAR", "description": ""},
        ],
    }
    result = score_table(meta, mtime=time.time())
    assert result["column_description_pct"] == 0.0
    assert set(result["missing_descriptions"]) == {"id", "name"}


def test_score_table_counts_valid_values_targets():
    meta = {
        "table": "t",
        "columns": [
            # Low-cardinality string without valid_values → missing
            {
                "name": "status",
                "type": "VARCHAR",
                "description": "order status",
                "distinct_count": 3,
            },
            # Low-cardinality string *with* valid_values → filled
            {
                "name": "tier",
                "type": "VARCHAR",
                "description": "tier",
                "distinct_count": 2,
                "valid_values": ["gold", "silver"],
            },
            # Numeric — not a valid_values target
            {
                "name": "id",
                "type": "INTEGER",
                "description": "id",
                "distinct_count": 9999,
            },
        ],
    }
    result = score_table(meta, mtime=time.time())
    assert result["valid_values_targets"] == 2
    assert result["valid_values_coverage_pct"] == 50.0
    assert result["missing_valid_values"] == ["status"]


def test_score_table_accepts_provenance_wrapped_valid_values():
    meta = {
        "table": "t",
        "columns": [
            {
                "name": "status",
                "type": "VARCHAR",
                "description": "x",
                "distinct_count": 3,
                "valid_values": {
                    "value": ["a", "b"],
                    "source": "values",
                    "confidence": 0.8,
                },
            }
        ],
    }
    result = score_table(meta, mtime=time.time())
    assert result["valid_values_coverage_pct"] == 100.0


def test_score_connection_sorts_worst_first(sqlite_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])
    # Create a second table and init it with a description (higher score)
    db = sqlite3.connect(sqlite_path)
    db.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT)")
    db.commit()
    db.close()
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "products"])

    # Fill description on products to raise its score
    meta_file = tmp_path / ".qdo" / "metadata" / "test" / "products.yaml"
    meta = yaml.safe_load(meta_file.read_text())
    for col in meta["columns"]:
        col["description"] = f"The {col['name']} column"
    meta["table_description"] = "Filled in"
    meta_file.write_text(yaml.safe_dump(meta))

    report = score_connection(sqlite_path)
    tables = report["tables"]
    assert [t["table"] for t in tables] == ["users", "products"]
    assert tables[0]["score"] < tables[1]["score"]
    assert report["average_score"] is not None


# ---------------------------------------------------------------------------
# `qdo metadata score` CLI
# ---------------------------------------------------------------------------


def test_metadata_score_cli_json(sqlite_path, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    result = runner.invoke(app, ["-f", "json", "metadata", "score", "-c", sqlite_path])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    data = payload["data"]
    assert data["connection"] == sqlite_path
    assert len(data["tables"]) == 1
    table_score = data["tables"][0]
    assert table_score["table"] == "users"
    assert 0.0 <= table_score["score"] <= 1.0
    # Low score should produce a next_steps pointer
    next_steps = payload.get("next_steps") or []
    assert any("metadata suggest" in s.get("cmd", "") for s in next_steps)


def test_metadata_score_cli_empty_connection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["-f", "json", "metadata", "score", "-c", "nothing_here"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["data"]["tables"] == []


# ---------------------------------------------------------------------------
# `qdo metadata suggest` CLI
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> str:
    db = tmp_path / "shop.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, status TEXT, "
        "note TEXT, created_at TIMESTAMP)"
    )
    rows = [
        (1, "active", None, "2025-01-01T00:00:00"),
        (2, "active", None, "2025-01-02T00:00:00"),
        (3, "pending", None, "2025-01-03T00:00:00"),
        (4, "active", "hi", "2025-01-04T00:00:00"),
    ]
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return str(db)


def test_metadata_suggest_without_apply(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db(tmp_path)

    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "suggest", "-c", db, "-t", "orders"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    data = payload["data"]
    sugg_by_field = {s["field"]: s for s in data["suggestions"]}
    assert "temporal" in sugg_by_field
    assert sugg_by_field["temporal"]["column"] == "created_at"
    assert "valid_values" in sugg_by_field
    assert sugg_by_field["valid_values"]["column"] == "status"
    # note has 75% nulls — not sparse at >95% threshold so shouldn't appear
    assert "likely_sparse" not in sugg_by_field
    # Without --apply, the YAML should have no provenance-wrapped entries
    assert data["applied"] is None


def test_metadata_suggest_with_apply(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QDO_AUTHOR", "testbot")
    db = _make_db(tmp_path)

    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "suggest", "-c", db, "-t", "orders", "--apply"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    data = payload["data"]
    assert data["applied"] is not None
    assert data["applied"]["written"]  # something got written

    meta_file = tmp_path / ".qdo" / "metadata" / "shop" / "orders.yaml"
    meta = yaml.safe_load(meta_file.read_text())
    cols = {c["name"]: c for c in meta["columns"]}
    # temporal on created_at with profile provenance
    assert cols["created_at"]["temporal"]["source"] == "profile"
    # valid_values on status with values provenance
    assert cols["status"]["valid_values"]["source"] == "values"
    assert cols["status"]["valid_values"]["author"] == "testbot"


def test_metadata_suggest_is_idempotent(tmp_path, monkeypatch):
    """A second `suggest` run after `--apply` should produce no new suggestions."""
    monkeypatch.chdir(tmp_path)
    db = _make_db(tmp_path)

    runner.invoke(
        app,
        ["metadata", "suggest", "-c", db, "-t", "orders", "--apply"],
    )
    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "suggest", "-c", db, "-t", "orders"],
    )
    payload = json.loads(result.output)
    assert payload["data"]["suggestions"] == []


# ---------------------------------------------------------------------------
# next_steps pointer on profile for low-scoring tables
# ---------------------------------------------------------------------------


def test_profile_next_steps_points_to_suggest_when_score_is_low(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db(tmp_path)
    # Init metadata but leave descriptions as placeholders → low score
    runner.invoke(app, ["metadata", "init", "-c", db, "-t", "orders"])

    result = runner.invoke(
        app,
        ["-f", "json", "profile", "-c", db, "-t", "orders"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    steps = payload.get("next_steps") or []
    assert any(
        "metadata suggest" in s.get("cmd", "") and "-t orders" in s.get("cmd", "") for s in steps
    ), steps


def test_peek_score_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert peek_score("no_such_conn", "no_such_table") is None
