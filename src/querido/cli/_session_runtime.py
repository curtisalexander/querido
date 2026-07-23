"""CLI-owned session recording and replay process orchestration."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class _Tee(io.TextIOBase):
    def __init__(self, original: Any, buffer: io.StringIO) -> None:
        self._original = original
        self._buffer = buffer

    def write(self, value: str) -> int:
        self._original.write(value)
        self._buffer.write(value)
        return len(value)

    def flush(self) -> None:
        self._original.flush()

    def writable(self) -> bool:
        return True

    def __getattr__(self, name: str) -> Any:
        return getattr(self._original, name)


@dataclass
class SessionRecorder:
    """Capture CLI stdout and append one session step when stopped."""

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
        if self._stopped:
            return
        self._stopped = True
        if self._original_stdout is not None:
            sys.stdout = self._original_stdout

    def stop(self, exit_code: int = 0) -> dict:
        if self._stopped:
            return {}
        self._stopped = True

        duration = round(time.monotonic() - self._start_time, 4)
        if self._original_stdout is not None:
            sys.stdout = self._original_stdout
        captured = self._buffer.getvalue() if self._buffer is not None else ""

        from querido.core.session import (
            SESSION_FORMAT_VERSION,
            STDOUT_FILE,
            STEPS_FILE,
            _derive_cmd,
            _extract_row_count,
            next_step_index,
            session_dir,
        )

        dir_ = session_dir(self.name, self.cwd)
        dir_.mkdir(parents=True, exist_ok=True)
        index = next_step_index(dir_)

        step_dir = dir_ / f"step_{index}"
        step_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = step_dir / STDOUT_FILE
        stdout_path.write_text(captured, encoding="utf-8")

        record = {
            "format_version": SESSION_FORMAT_VERSION,
            "index": index,
            "timestamp": self._started_at,
            "cmd": _derive_cmd(self.argv),
            "args": list(self.argv),
            "duration": duration,
            "exit_code": exit_code,
            "row_count": _extract_row_count(captured),
            "stdout_path": str(stdout_path.relative_to(dir_.parent.parent)),
        }
        with (dir_ / STEPS_FILE).open("a", encoding="utf-8") as file:
            file.write(json.dumps(record) + "\n")
        return record


@dataclass
class ReplayStepResult:
    source_index: int | None
    cmd: str
    args: list[str]
    exit_code: int
    duration: float
    stdout: str = ""
    stderr: str = ""


@dataclass
class ReplayResult:
    source_session: str
    replay_session: str
    steps: list[ReplayStepResult]

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def failed_step(self) -> ReplayStepResult | None:
        return next((step for step in self.steps if step.exit_code != 0), None)


def replay_session(
    name: str,
    *,
    last: int | None = None,
    into: str | None = None,
    continue_on_error: bool = False,
    cwd: Path | None = None,
    stream_output: bool = False,
    stderr: Any = None,
    on_step_start: Any = None,
) -> ReplayResult:
    """Re-execute successful recorded steps and record the child invocations."""
    from querido._runtime import qdo_argv
    from querido.core.session import _derive_cmd, iter_steps, session_dir

    dir_ = session_dir(name, cwd)
    if not dir_.is_dir():
        raise ValueError(f"Session not found: {name}")

    source_steps = [
        step
        for step in iter_steps(name, cwd)
        if step.get("exit_code") == 0 and isinstance(step.get("args"), list) and step.get("args")
    ]
    if last is not None and last > 0:
        source_steps = source_steps[-last:]
    if not source_steps:
        raise ValueError(
            f"Session {name!r} has no successful recorded steps to replay. "
            "Run 'qdo session show' to inspect."
        )

    replay_name = into or f"replay-{name}-{int(time.time())}"
    env = os.environ.copy()
    env["QDO_SESSION"] = replay_name
    run_cwd = cwd or Path.cwd()
    err = stderr if stderr is not None else sys.stderr
    results: list[ReplayStepResult] = []
    total = len(source_steps)

    for position, step in enumerate(source_steps, start=1):
        args = [str(part) for part in step.get("args", []) if isinstance(part, str)]
        if not args:
            continue
        if callable(on_step_start):
            on_step_start(step, position, total)

        started = time.monotonic()
        proc = subprocess.run(
            [*qdo_argv(), *args],
            cwd=run_cwd,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        duration = round(time.monotonic() - started, 4)

        if stream_output:
            if proc.stdout:
                sys.stdout.write(proc.stdout)
            if proc.stderr:
                err.write(proc.stderr)

        result = ReplayStepResult(
            source_index=step.get("index") if isinstance(step.get("index"), int) else None,
            cmd=_derive_cmd(args),
            args=args,
            exit_code=proc.returncode,
            duration=duration,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
        results.append(result)
        if proc.returncode != 0 and not continue_on_error:
            break

    return ReplayResult(source_session=name, replay_session=replay_name, steps=results)
