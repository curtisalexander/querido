"""Tests for qdo completion show.

Typer generates the shell-completion output itself; we don't own it.  So the
only tests here exercise *our* code: the hint text we print and the invalid
shell rejection.  The earlier per-shell "produces output" / "contains marker"
tests were dropped (2026-04-17) — they asserted on Typer's generated text.
"""

import re

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _plain(output: str) -> str:
    return _ANSI_RE.sub("", output)


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish", "powershell"])
def test_completion_show_hint(shell: str) -> None:
    """The hint text mentions either qdo or the shell it's configuring."""
    result = runner.invoke(app, ["completion", "show", shell, "--hint"])
    assert result.exit_code == 0
    plain = _plain(result.output)
    assert "qdo" in plain.lower() or shell in plain.lower()


def test_completion_invalid_shell() -> None:
    """Unknown shell names are rejected with a message naming the shell."""
    result = runner.invoke(app, ["completion", "show", "nushell"])
    assert result.exit_code != 0
    assert "nushell" in result.output or "nushell" in str(result.exception or "")
