"""Tests for the metadata write→read compounding loop (R.1).

These tests enforce the contract: ``values --write-metadata`` writes
``valid_values`` with provenance, and every scanning command that
accepts ``--connection`` surfaces that stored value on its next call.

If you wire a new scanning command to read stored metadata (R.1's
pattern — call ``load_column_metadata()`` and merge onto the output),
add a row to :data:`_READBACK_CASES` describing where in the payload
the stored value should appear. The parameterized test will pick it up
automatically and fail if the write→read loop is broken for that
command.

The enum-violation check (``quality`` with stored ``valid_values``) is a
distinct contract — stored metadata drives a new SQL query, not just an
output merge — so it has its own standalone test.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


@pytest.fixture
def orders_db(tmp_path: Path, make_sqlite_db) -> str:
    """Orders table with a low-cardinality ``status`` column."""
    return make_sqlite_db(
        str(tmp_path / "shop.db"),
        tables={
            ("CREATE TABLE orders (id INTEGER PRIMARY KEY, status TEXT NOT NULL, amount REAL)"): [
                "INSERT INTO orders VALUES (1, 'active', 10.0)",
                "INSERT INTO orders VALUES (2, 'inactive', 20.0)",
                "INSERT INTO orders VALUES (3, 'pending', 30.0)",
                "INSERT INTO orders VALUES (4, 'active', 40.0)",
                "INSERT INTO orders VALUES (5, 'pending', 50.0)",
            ],
        },
    )


def _write_valid_values(db: str) -> None:
    """Run ``values --write-metadata`` to seed ``valid_values``."""
    result = runner.invoke(
        app,
        ["values", "-c", db, "-t", "orders", "--columns", "status", "--write-metadata"],
    )
    assert result.exit_code == 0, result.output


def _status_entry(stats: list[dict]) -> dict:
    """Pluck the ``status`` column entry from a stats/columns list."""
    for entry in stats:
        name = entry.get("column_name") or entry.get("name")
        if name == "status":
            return entry
    raise AssertionError(f"No 'status' column in stats: {stats!r}")


def _valid_values_on_column(payload: dict) -> list | None:
    """Extract stored ``valid_values`` when merged onto the column entry.

    Used by ``profile`` and ``context`` — both emit a table-level envelope
    with per-column stats, and R.1 merges stored fields onto those entries.
    """
    return _status_entry(payload["data"]["columns"]).get("valid_values")


def _valid_values_in_stored_metadata(payload: dict) -> list | None:
    """Extract stored ``valid_values`` from the top-level ``stored_metadata``.

    Used by ``values`` — it's column-scoped, so stored metadata is attached
    at the payload root rather than per column.
    """
    return (payload["data"].get("stored_metadata") or {}).get("valid_values")


# -- readback contract --------------------------------------------------------
#
# (label, argv, extractor).  ``argv`` is run under ``-f json`` against the
# fixture DB; ``extractor`` pulls the stored ``valid_values`` out of the
# parsed payload.  Adding a new command to this list is the one-liner that
# extends the contract.

_READBACK_CASES: list[tuple[str, list[str], Callable[[dict], list | None]]] = [
    ("profile", ["profile", "-t", "orders"], _valid_values_on_column),
    ("context", ["context", "-t", "orders"], _valid_values_on_column),
    (
        "values",
        ["values", "-t", "orders", "--columns", "status"],
        _valid_values_in_stored_metadata,
    ),
]


@pytest.mark.parametrize(
    ("label", "argv", "extract"), _READBACK_CASES, ids=[c[0] for c in _READBACK_CASES]
)
def test_command_surfaces_stored_valid_values(
    orders_db: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    argv: list[str],
    extract: Callable[[dict], list | None],
) -> None:
    """Contract: every scan command that accepts ``-c`` reads stored metadata."""
    monkeypatch.chdir(tmp_path)
    _write_valid_values(orders_db)

    result = runner.invoke(app, ["-f", "json", *argv, "-c", orders_db])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    assert sorted(extract(payload) or []) == ["active", "inactive", "pending"]


@pytest.mark.parametrize(
    ("label", "argv", "extract"), _READBACK_CASES, ids=[c[0] for c in _READBACK_CASES]
)
def test_readback_absent_without_metadata(
    orders_db: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    argv: list[str],
    extract: Callable[[dict], list | None],
) -> None:
    """Without a written metadata YAML, no scan command surfaces stored fields."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["-f", "json", *argv, "-c", orders_db])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    assert extract(payload) is None


# -- enum-violation check: a distinct contract -------------------------------
#
# Stored ``valid_values`` should not just appear in output — ``quality`` runs
# an extra SQL query and flags rows that violate the allowed set.  This is a
# different invariant (side-effectful behavioral change) and stays standalone.


def test_quality_flags_rows_violating_stored_valid_values(
    tmp_path: Path, make_sqlite_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stored valid_values drive an enum-membership check in quality."""
    monkeypatch.chdir(tmp_path)
    db = make_sqlite_db(
        str(tmp_path / "violations.db"),
        tables={
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, status TEXT NOT NULL)": [
                "INSERT INTO orders VALUES (1, 'active')",
                "INSERT INTO orders VALUES (2, 'inactive')",
                "INSERT INTO orders VALUES (3, 'pending')",
            ],
        },
    )
    _write_valid_values(db)

    # Introduce a violating row after valid_values were captured.
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO orders VALUES (4, 'archived')")
    conn.commit()
    conn.close()

    result = runner.invoke(
        app,
        ["-f", "json", "quality", "-c", db, "-t", "orders"],
    )
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    status = _status_entry(payload["data"]["columns"])
    assert status.get("invalid_count") == 1
    assert any("not in valid_values" in issue for issue in status.get("issues") or [])
    assert status.get("status") in ("warn", "fail")
