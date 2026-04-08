"""Tests for qdo completion show."""

import re

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(output: str) -> str:
    return _ANSI_RE.sub("", output)


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish", "powershell"])
def test_completion_show_produces_output(shell: str) -> None:
    result = runner.invoke(app, ["completion", "show", shell])
    assert result.exit_code == 0, result.output
    assert len(result.output.strip()) > 0


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish", "powershell"])
def test_completion_show_hint(shell: str) -> None:
    result = runner.invoke(app, ["completion", "show", shell, "--hint"])
    assert result.exit_code == 0
    plain = _plain(result.output)
    assert "qdo" in plain.lower() or shell in plain.lower()


def test_completion_invalid_shell() -> None:
    result = runner.invoke(app, ["completion", "show", "nushell"])
    assert result.exit_code != 0
    assert "nushell" in result.output or "nushell" in str(result.exception or "")


def test_completion_bash_contains_complete_marker() -> None:
    result = runner.invoke(app, ["completion", "show", "bash"])
    assert result.exit_code == 0
    assert "complete" in result.output.lower() or "_QDO" in result.output


def test_completion_fish_hint_shows_save_path() -> None:
    result = runner.invoke(app, ["completion", "show", "fish", "--hint"])
    assert result.exit_code == 0
    assert "fish" in result.output.lower()


def test_completion_help() -> None:
    result = runner.invoke(app, ["completion", "--help"])
    assert result.exit_code == 0
