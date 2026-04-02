"""Tests for the qdo overview command."""

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_overview_runs() -> None:
    result = runner.invoke(app, ["overview"])
    assert result.exit_code == 0
    assert "qdo" in result.output.lower()


def test_overview_contains_commands() -> None:
    result = runner.invoke(app, ["overview"])
    assert result.exit_code == 0
    for cmd in ("inspect", "preview", "profile", "dist", "search", "lineage"):
        assert cmd in result.output


def test_overview_contains_global_flags() -> None:
    result = runner.invoke(app, ["overview"])
    assert result.exit_code == 0
    assert "--format" in result.output
    assert "--show-sql" in result.output
