"""Tests for the qdo overview command."""

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


# ``test_overview_runs`` dropped (2026-04-17) — pure smoke; the content test
# below exercises the same command and asserts something meaningful.


def test_overview_contains_expected_content() -> None:
    """Overview must list representative commands and global flags.

    This is the content we generate; Typer isn't responsible for it.
    """
    result = runner.invoke(app, ["overview"])
    assert result.exit_code == 0
    for cmd in ("inspect", "preview", "profile", "dist", "catalog", "view-def"):
        assert cmd in result.output, f"missing command '{cmd}' in overview output"
    assert "--format" in result.output
    assert "--show-sql" in result.output
