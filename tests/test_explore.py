"""Tests for the explore CLI entry point."""

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_explore_help():
    result = runner.invoke(app, ["explore", "--help"])
    assert result.exit_code == 0
    assert "explore" in result.output.lower()
    assert "--table" in result.output
    assert "--connection" in result.output


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
