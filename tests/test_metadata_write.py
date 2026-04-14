"""Tests for --write-metadata on profile / values / quality (Phase 1.3)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import yaml
from typer.testing import CliRunner

from querido.cli.main import app
from querido.core.metadata_write import (
    FieldUpdate,
    _is_human_field,
    apply_updates,
    derive_from_profile,
    derive_from_quality,
    derive_from_values,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Rule derivation (no connector required)
# ---------------------------------------------------------------------------


def test_derive_from_profile_flags_temporal_columns():
    stats = [
        {"column_name": "created_at", "column_type": "TIMESTAMP"},
        {"column_name": "name", "column_type": "VARCHAR"},
        {"column_name": "updated_date", "column_type": "DATE"},
        {"column_name": "amount_at", "column_type": "INTEGER"},  # not a temporal type
    ]
    col_info = [
        {"name": "created_at", "type": "TIMESTAMP"},
        {"name": "name", "type": "VARCHAR"},
        {"name": "updated_date", "type": "DATE"},
        {"name": "amount_at", "type": "INTEGER"},
    ]
    updates = derive_from_profile(stats, col_info)
    assert {u.column for u in updates} == {"created_at", "updated_date"}
    assert all(u.field == "temporal" and u.value is True for u in updates)
    assert all(u.confidence == 0.9 for u in updates)


def test_derive_from_values_low_cardinality_strings():
    result = {
        "column": "status",
        "distinct_count": 3,
        "truncated": False,
        "values": [
            {"value": "active", "count": 10},
            {"value": "inactive", "count": 5},
            {"value": "pending", "count": 1},
        ],
    }
    [upd] = derive_from_values(result)
    assert upd.field == "valid_values"
    assert upd.value == ["active", "inactive", "pending"]
    assert upd.confidence == 0.8


def test_derive_from_values_skips_high_cardinality():
    result = {
        "column": "email",
        "distinct_count": 5000,
        "truncated": True,
        "values": [{"value": "a@b.com", "count": 1}],
    }
    assert derive_from_values(result) == []


def test_derive_from_values_skips_numeric():
    result = {
        "column": "age",
        "distinct_count": 3,
        "truncated": False,
        "values": [{"value": 25, "count": 10}, {"value": 30, "count": 5}],
    }
    assert derive_from_values(result) == []


def test_derive_from_quality_flags_sparse_columns():
    result = {
        "columns": [
            {"name": "notes", "null_pct": 98.5},
            {"name": "name", "null_pct": 5.0},
            {"name": "nickname", "null_pct": 95.01},
            {"name": "title", "null_pct": 95.0},  # boundary — not sparse
        ]
    }
    updates = derive_from_quality(result)
    assert {u.column for u in updates} == {"notes", "nickname"}
    assert all(u.field == "likely_sparse" and u.value is True for u in updates)


# ---------------------------------------------------------------------------
# Human field detection
# ---------------------------------------------------------------------------


def test_is_human_field_detects_plain_values():
    assert _is_human_field("A user table")
    assert _is_human_field(["a", "b"])
    assert _is_human_field({"value": True, "source": "human", "confidence": 1.0})


def test_is_human_field_detects_placeholders_as_empty():
    assert not _is_human_field("<description>")
    assert not _is_human_field("")
    assert not _is_human_field([])
    assert not _is_human_field(None)
    assert not _is_human_field({"value": True, "source": "profile", "confidence": 0.9})


# ---------------------------------------------------------------------------
# End-to-end CLI: `qdo profile --write-metadata`
# ---------------------------------------------------------------------------


def _make_db_with_temporal(tmp_path: Path) -> str:
    db = tmp_path / "shop.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, status TEXT, created_at TIMESTAMP)")
    conn.executemany(
        "INSERT INTO orders VALUES (?, ?, ?)",
        [
            (1, "active", "2025-01-01T00:00:00"),
            (2, "active", "2025-01-02T00:00:00"),
            (3, "pending", "2025-01-03T00:00:00"),
        ],
    )
    conn.commit()
    conn.close()
    return str(db)


def test_profile_write_metadata_creates_yaml_with_provenance(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QDO_AUTHOR", "testbot")
    db = _make_db_with_temporal(tmp_path)

    result = runner.invoke(
        app,
        ["profile", "-c", db, "-t", "orders", "--write-metadata"],
    )
    assert result.exit_code == 0, result.output

    meta_file = tmp_path / ".qdo" / "metadata" / "shop" / "orders.yaml"
    assert meta_file.exists()
    meta = yaml.safe_load(meta_file.read_text())
    cols = {c["name"]: c for c in meta["columns"]}

    temporal = cols["created_at"]["temporal"]
    assert temporal == {
        "value": True,
        "source": "profile",
        "confidence": 0.9,
        "written_at": temporal["written_at"],
        "author": "testbot",
    }
    # non-temporal column should not receive the field
    assert "temporal" not in cols["status"]


def test_profile_write_metadata_is_idempotent(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db_with_temporal(tmp_path)

    runner.invoke(app, ["profile", "-c", db, "-t", "orders", "--write-metadata"])
    meta_file = tmp_path / ".qdo" / "metadata" / "shop" / "orders.yaml"
    first = meta_file.read_text()
    # YAML ordering is stable — re-running should produce the same result
    runner.invoke(app, ["profile", "-c", db, "-t", "orders", "--write-metadata"])
    # Only the `written_at` timestamp may change; structure is the same
    second = yaml.safe_load(meta_file.read_text())
    first_dict = yaml.safe_load(first)
    assert len(first_dict["columns"]) == len(second["columns"])
    for a, b in zip(first_dict["columns"], second["columns"], strict=True):
        assert a.get("name") == b.get("name")
        if "temporal" in a:
            assert a["temporal"]["value"] == b["temporal"]["value"]
            assert a["temporal"]["source"] == b["temporal"]["source"]


# ---------------------------------------------------------------------------
# End-to-end CLI: `qdo values --write-metadata`
# ---------------------------------------------------------------------------


def test_values_write_metadata_writes_valid_values(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db_with_temporal(tmp_path)

    result = runner.invoke(
        app,
        [
            "values",
            "-c",
            db,
            "-t",
            "orders",
            "-C",
            "status",
            "--write-metadata",
        ],
    )
    assert result.exit_code == 0, result.output

    meta_file = tmp_path / ".qdo" / "metadata" / "shop" / "orders.yaml"
    meta = yaml.safe_load(meta_file.read_text())
    cols = {c["name"]: c for c in meta["columns"]}
    assert cols["status"]["valid_values"]["value"] == ["active", "pending"]
    assert cols["status"]["valid_values"]["source"] == "values"
    assert cols["status"]["valid_values"]["confidence"] == 0.8


# ---------------------------------------------------------------------------
# End-to-end CLI: `qdo quality --write-metadata`
# ---------------------------------------------------------------------------


def test_quality_write_metadata_writes_likely_sparse(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "shop.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (id INTEGER, notes TEXT)")
    rows: list[tuple[int, str | None]] = [(i, None) for i in range(99)]
    rows.append((99, "only one note"))
    conn.executemany("INSERT INTO t VALUES (?, ?)", rows)
    conn.commit()
    conn.close()

    result = runner.invoke(
        app,
        ["quality", "-c", str(db), "-t", "t", "--write-metadata"],
    )
    assert result.exit_code == 0, result.output

    meta_file = tmp_path / ".qdo" / "metadata" / "shop" / "t.yaml"
    meta = yaml.safe_load(meta_file.read_text())
    cols = {c["name"]: c for c in meta["columns"]}
    assert cols["notes"]["likely_sparse"]["value"] is True
    assert cols["notes"]["likely_sparse"]["source"] == "quality"
    assert "likely_sparse" not in cols["id"]


# ---------------------------------------------------------------------------
# Human field protection + --force
# ---------------------------------------------------------------------------


def test_write_metadata_preserves_human_fields(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db_with_temporal(tmp_path)

    # First init metadata and hand-author valid_values on `status`
    runner.invoke(app, ["metadata", "init", "-c", db, "-t", "orders"])
    meta_file = tmp_path / ".qdo" / "metadata" / "shop" / "orders.yaml"
    meta = yaml.safe_load(meta_file.read_text())
    for col in meta["columns"]:
        if col["name"] == "status":
            col["valid_values"] = ["active", "inactive", "pending", "cancelled"]
    meta_file.write_text(yaml.safe_dump(meta))

    # Run values --write-metadata (without --force) — should NOT overwrite
    runner.invoke(
        app,
        ["values", "-c", db, "-t", "orders", "-C", "status", "--write-metadata"],
    )
    meta = yaml.safe_load(meta_file.read_text())
    cols = {c["name"]: c for c in meta["columns"]}
    # Human value preserved
    assert cols["status"]["valid_values"] == [
        "active",
        "inactive",
        "pending",
        "cancelled",
    ]

    # With --force it should overwrite
    runner.invoke(
        app,
        [
            "values",
            "-c",
            db,
            "-t",
            "orders",
            "-C",
            "status",
            "--write-metadata",
            "--force",
        ],
    )
    meta = yaml.safe_load(meta_file.read_text())
    cols = {c["name"]: c for c in meta["columns"]}
    vv = cols["status"]["valid_values"]
    assert isinstance(vv, dict)
    assert vv["source"] == "values"
    assert vv["value"] == ["active", "pending"]


# ---------------------------------------------------------------------------
# apply_updates — missing column produces a skip entry
# ---------------------------------------------------------------------------


def test_apply_updates_skips_unknown_column(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _make_db_with_temporal(tmp_path)

    runner.invoke(app, ["metadata", "init", "-c", db, "-t", "orders"])

    from querido.connectors.factory import create_connector

    with create_connector({"type": "sqlite", "path": db}) as conn:
        summary = apply_updates(
            conn,
            db,
            "orders",
            [FieldUpdate(field="temporal", value=True, confidence=0.9, column="ghost")],
            source="profile",
        )
    assert summary["written"] == []
    assert summary["skipped"] == [
        {"column": "ghost", "field": "temporal", "reason": "column_not_found"}
    ]
