"""Tests for the qdo serve CLI entry point."""

import re
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(output: str) -> str:
    return _ANSI_RE.sub("", output)


# ---------------------------------------------------------------------------
# Help / flag presence
# ---------------------------------------------------------------------------


def test_serve_help() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    plain = _plain(result.output)
    assert "--connection" in plain
    assert "--port" in plain
    assert "--host" in plain


def test_serve_help_shows_db_type_flag() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--db-type" in _plain(result.output)


# ---------------------------------------------------------------------------
# Missing / invalid arguments
# ---------------------------------------------------------------------------


def test_serve_requires_connection() -> None:
    result = runner.invoke(app, ["serve"])
    assert result.exit_code != 0


def test_serve_invalid_path() -> None:
    """Serve with a nonexistent path should fail."""
    result = runner.invoke(app, ["serve", "-c", "/nonexistent/path.db"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Missing optional dependency (web extra not installed in test env)
# ---------------------------------------------------------------------------


def test_serve_missing_uvicorn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When uvicorn is not installed, serve should exit with code 1 and print install hint."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()

    import sys

    # Simulate uvicorn not being installed
    monkeypatch.setitem(sys.modules, "uvicorn", None)

    result = runner.invoke(app, ["serve", "-c", db_path])
    assert result.exit_code == 1
    output = _plain(result.output)
    assert "querido" in output.lower() or "web" in output.lower() or "uvicorn" in output.lower()


# ---------------------------------------------------------------------------
# Default flag values
# ---------------------------------------------------------------------------


def test_serve_default_port_in_help() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert "8888" in result.output


def test_serve_default_host_in_help() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert "127.0.0.1" in result.output
