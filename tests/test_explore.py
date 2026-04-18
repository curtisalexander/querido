"""Tests for the explore CLI entry point.

The help-rendering and required-flag-enforcement tests were removed
2026-04-17 — those exercise Typer, not our code. The remaining tests cover
our validation and resolve_table integration.
"""

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_explore_invalid_table_name(sqlite_path: str):
    result = runner.invoke(app, ["explore", "-c", sqlite_path, "-t", "DROP TABLE; --"])
    assert result.exit_code != 0


def test_explore_nonexistent_table(sqlite_path: str):
    result = runner.invoke(app, ["explore", "-c", sqlite_path, "-t", "no_such_table"])
    assert result.exit_code != 0
