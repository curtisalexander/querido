"""Session MVP — append-only step log for agent workflows.

When ``QDO_SESSION=<name>`` is set, every ``qdo`` invocation appends a JSONL
record to ``.qdo/sessions/<name>/steps.jsonl`` with timestamp, command,
args, duration, exit code, row count, and the path to a saved copy of the
step's stdout (``.qdo/sessions/<name>/step_<n>/stdout``).

No daemon, no DB, no server — everything is plain files in the cwd.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator


SESSIONS_ROOT = ".qdo/sessions"
STEPS_FILE = "steps.jsonl"
STDOUT_FILE = "stdout"


def sessions_root(cwd: Path | None = None) -> Path:
    """Return the sessions root directory (``.qdo/sessions``) for *cwd*."""
    return (cwd or Path.cwd()) / SESSIONS_ROOT


def session_dir(name: str, cwd: Path | None = None) -> Path:
    """Return the directory for a named session. Does not create it."""
    if not name or any(c in name for c in "/\\:"):
        raise ValueError(f"Invalid session name: {name!r}")
    return sessions_root(cwd) / name


def list_sessions(cwd: Path | None = None) -> list[str]:
    """Return sorted list of session names under ``.qdo/sessions``."""
    root = sessions_root(cwd)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def iter_steps(name: str, cwd: Path | None = None) -> Iterator[dict]:
    """Yield each step record from ``steps.jsonl`` in order."""
    path = session_dir(name, cwd) / STEPS_FILE
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def next_step_index(dir_: Path) -> int:
    """Return the 1-based index for the next step in the given session dir."""
    path = dir_ / STEPS_FILE
    if not path.is_file():
        return 1
    # Count non-empty lines without loading everything into memory.
    count = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count + 1


class _Tee(io.TextIOBase):
    """Write-through text stream that duplicates writes into a buffer."""

    def __init__(self, original: Any, buffer: io.StringIO) -> None:
        self._original = original
        self._buffer = buffer

    def write(self, s: str) -> int:
        self._original.write(s)
        self._buffer.write(s)
        return len(s)

    def flush(self) -> None:
        self._original.flush()

    def writable(self) -> bool:
        return True

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)


@dataclass
class SessionRecorder:
    """Captures stdout and records a step when ``stop()`` is called.

    Designed to be started in the CLI root callback and stopped from a
    ``ctx.call_on_close`` hook so the step is recorded regardless of how the
    command exits.
    """

    name: str
    argv: list[str]
    cwd: Path | None = None
    _buffer: io.StringIO | None = None
    _original_stdout: Any = None
    _start_time: float = 0.0
    _started_at: str = ""
    _stopped: bool = False

    def start(self) -> None:
        self._buffer = io.StringIO()
        self._original_stdout = sys.stdout
        sys.stdout = _Tee(self._original_stdout, self._buffer)
        self._start_time = time.monotonic()
        self._started_at = datetime.now(UTC).isoformat(timespec="seconds")

    def cancel(self) -> None:
        """Restore stdout without writing a record (used for skipped commands)."""
        if self._stopped:
            return
        self._stopped = True
        if self._original_stdout is not None:
            sys.stdout = self._original_stdout

    def stop(self, exit_code: int = 0) -> dict:
        """Restore stdout and append a step record. Returns the record."""
        if self._stopped:
            return {}
        self._stopped = True

        duration = round(time.monotonic() - self._start_time, 4)
        if self._original_stdout is not None:
            sys.stdout = self._original_stdout
        captured = self._buffer.getvalue() if self._buffer is not None else ""

        dir_ = session_dir(self.name, self.cwd)
        dir_.mkdir(parents=True, exist_ok=True)
        index = next_step_index(dir_)

        step_dir = dir_ / f"step_{index}"
        step_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = step_dir / STDOUT_FILE
        stdout_path.write_text(captured, encoding="utf-8")

        record = {
            "index": index,
            "timestamp": self._started_at,
            "cmd": _derive_cmd(self.argv),
            "args": list(self.argv),
            "duration": duration,
            "exit_code": exit_code,
            "row_count": _extract_row_count(captured),
            "stdout_path": str(stdout_path.relative_to(dir_.parent.parent)),
        }

        with (dir_ / STEPS_FILE).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        return record


def _derive_cmd(argv: list[str]) -> str:
    """Return the ``qdo <subcommand> [<subsub>]`` portion of *argv* (best effort)."""
    tokens: list[str] = []
    for tok in argv:
        if tok.startswith("-"):
            break
        tokens.append(tok)
        # Stop after two tokens — handles "config add", "snowflake semantic"
        if len(tokens) >= 2:
            break
    return " ".join(tokens) if tokens else ""


def _extract_row_count(stdout: str) -> int | None:
    """Best-effort row count extraction from a JSON envelope in *stdout*."""
    stripped = stdout.strip()
    if not stripped or not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    meta = payload.get("meta")
    if isinstance(meta, dict):
        rc = meta.get("row_count")
        if isinstance(rc, int):
            return rc

    data = payload.get("data")
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("rows", "results", "values", "items"):
            seq = data.get(key)
            if isinstance(seq, list):
                return len(seq)
    return None


def active_session_name() -> str | None:
    """Return the session name from ``QDO_SESSION`` or None."""
    name = os.environ.get("QDO_SESSION", "").strip()
    return name or None
