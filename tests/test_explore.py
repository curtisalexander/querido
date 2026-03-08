"""Tests for the explore CLI entry point."""

import re

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def test_explore_help():
    result = runner.invoke(app, ["explore", "--help"])
    assert result.exit_code == 0
    plain = _ANSI_RE.sub("", result.output)
    assert "explore" in plain.lower()
    assert "--table" in plain
    assert "--connection" in plain


def test_explore_missing_table():
    result = runner.invoke(app, ["explore", "-c", "dummy.db"])
    assert result.exit_code != 0


def test_explore_missing_connection():
    result = runner.invoke(app, ["explore", "-t", "users"])
    assert result.exit_code != 0


def test_explore_invalid_table_name(sqlite_path: str):
    result = runner.invoke(app, ["explore", "-c", sqlite_path, "-t", "DROP TABLE; --"])
    assert result.exit_code != 0


def test_explore_nonexistent_table(sqlite_path: str):
    result = runner.invoke(app, ["explore", "-c", sqlite_path, "-t", "no_such_table"])
    assert result.exit_code != 0
