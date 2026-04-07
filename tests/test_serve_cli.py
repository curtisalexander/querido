"""Tests for the qdo serve CLI entry point."""

import re

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def test_serve_help() -> None:
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    plain = _ANSI_RE.sub("", result.output)
    assert "--connection" in plain
    assert "--port" in plain
    assert "--host" in plain


def test_serve_requires_connection() -> None:
    result = runner.invoke(app, ["serve"])
    assert result.exit_code != 0


def test_serve_invalid_path() -> None:
    """Serve with a nonexistent path should fail."""
    result = runner.invoke(app, ["serve", "-c", "/nonexistent/path.db"])
    assert result.exit_code != 0
