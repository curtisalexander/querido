"""Shared terminal helpers for the qdo tutorial runners."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

_IS_TTY = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _color(code: str, text: str) -> str:
    if not _IS_TTY:
        return text
    return f"\033[{code}m{text}\033[0m"


def _cyan(text: str) -> str:
    return _color("36", text)


def _bold(text: str) -> str:
    return _color("1", text)


def _dim(text: str) -> str:
    return _color("2", text)


def _green(text: str) -> str:
    return _color("32", text)


def _banner(title: str) -> None:
    width = shutil.get_terminal_size((80, 24)).columns
    line = "=" * min(width, 60)
    print(f"\n{_cyan(line)}")
    print(f"  {_bold(title)}")
    print(f"{_cyan(line)}\n")


def _pause() -> None:
    try:
        input(_dim("  [Press Enter to continue] "))
    except (KeyboardInterrupt, EOFError):
        print()
        raise SystemExit(0) from None


def _find_qdo() -> list[str]:
    """Return the command prefix for running qdo."""
    if shutil.which("qdo"):
        return ["qdo"]
    return [sys.executable, "-m", "querido"]


def _run_qdo(cmd: str, *, env: dict | None = None) -> None:
    """Run a qdo command and print its output."""
    prefix = _find_qdo()
    args = prefix + shlex.split(cmd)
    print(f"  {_green('$')} {_green(' '.join(prefix))} {cmd}")
    print()
    subprocess.run(args, cwd=Path.cwd(), env=env)
    print()
