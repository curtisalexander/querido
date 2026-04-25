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
import subprocess
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


# Short, memorable word lists for generated session names. Picked to be
# pronounceable, non-offensive, and distinguishable at a glance
# (no plurals, no near-homophones). ~40 words each => ~64k combinations.
_ADJECTIVES = (
    "amber",
    "brave",
    "brisk",
    "bronze",
    "calm",
    "cheerful",
    "clever",
    "cobalt",
    "crimson",
    "crisp",
    "eager",
    "fierce",
    "gentle",
    "golden",
    "happy",
    "hardy",
    "jolly",
    "keen",
    "lively",
    "loyal",
    "lucid",
    "mellow",
    "merry",
    "mighty",
    "nimble",
    "olive",
    "plucky",
    "polite",
    "proud",
    "quiet",
    "quick",
    "rapid",
    "rustic",
    "silver",
    "spry",
    "sunny",
    "swift",
    "tender",
    "velvet",
    "witty",
)
_NOUNS = (
    "badger",
    "beacon",
    "canyon",
    "cedar",
    "comet",
    "coral",
    "delta",
    "ember",
    "falcon",
    "forest",
    "glacier",
    "harbor",
    "hawk",
    "heron",
    "island",
    "juniper",
    "lagoon",
    "lantern",
    "marble",
    "meadow",
    "orchid",
    "otter",
    "parrot",
    "pebble",
    "pine",
    "puffin",
    "quail",
    "raven",
    "reef",
    "ridge",
    "river",
    "robin",
    "sparrow",
    "tundra",
    "valley",
    "willow",
)
_NOUNS2 = (
    "arcade",
    "bridge",
    "cabin",
    "canoe",
    "compass",
    "cottage",
    "drift",
    "festival",
    "harvest",
    "journey",
    "lantern",
    "legend",
    "map",
    "market",
    "monsoon",
    "orbit",
    "outpost",
    "parade",
    "pavilion",
    "picnic",
    "quest",
    "ramble",
    "rhythm",
    "safari",
    "summit",
    "sunrise",
    "temple",
    "thicket",
    "trek",
    "trellis",
    "vacation",
    "voyage",
    "wander",
    "whisper",
)


def generate_session_name() -> str:
    """Return a random ``adjective-noun-noun`` identifier.

    Example: ``amber-falcon-voyage``. Uses :mod:`secrets` for picking so
    repeated suggestions in the same second don't collide.
    """
    import secrets

    return "-".join((secrets.choice(_ADJECTIVES), secrets.choice(_NOUNS), secrets.choice(_NOUNS2)))


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


def read_step_stdout(step: dict, cwd: Path | None = None) -> str:
    """Return the saved stdout for *step*, or ``""`` if it can't be read."""
    rel = step.get("stdout_path")
    if not isinstance(rel, str) or not rel:
        return ""
    path = (cwd or Path.cwd()) / ".qdo" / rel
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def find_latest_table_snapshot(
    name: str,
    *,
    connection: str,
    table: str,
    cwd: Path | None = None,
) -> dict | None:
    """Return the latest structured inspect/context snapshot for *table*."""
    steps = list(iter_steps(name, cwd))
    for step in reversed(steps):
        payload = _parse_structured_stdout(read_step_stdout(step, cwd))
        if payload is None:
            continue
        if payload.get("command") not in {"inspect", "context"}:
            continue

        meta = payload.get("meta")
        data = payload.get("data")
        if not isinstance(meta, dict) or not isinstance(data, dict):
            continue
        if meta.get("connection") != connection:
            continue

        snapshot_table = data.get("table") or meta.get("table")
        columns = data.get("columns")
        row_count = data.get("row_count")
        if not isinstance(snapshot_table, str) or snapshot_table.lower() != table.lower():
            continue
        if not isinstance(columns, list):
            continue

        return {
            "session": name,
            "step_index": step.get("index"),
            "timestamp": step.get("timestamp"),
            "command": payload.get("command"),
            "table": snapshot_table,
            "columns": columns,
            "row_count": row_count if isinstance(row_count, int) else None,
        }
    return None


def resolve_query_step_reference(ref: str, *, cwd: Path | None = None) -> dict[str, Any]:
    """Resolve ``<session>:<step>`` to reusable SQL from a prior ``query`` step."""
    session_name, step_token = _parse_step_reference(ref)

    dir_ = session_dir(session_name, cwd)
    if not dir_.is_dir():
        raise ValueError(f"Session not found: {session_name}")

    steps = list(iter_steps(session_name, cwd))
    step = _select_step(steps, step_token)
    if step is None:
        raise ValueError(f"Session step not found: {ref}")

    payload = _parse_structured_stdout(read_step_stdout(step, cwd))
    if payload is None:
        raise ValueError(
            f"Session step {ref} was recorded as rich output, not JSON; --from needs the "
            "step's structured envelope. Re-record the source step with -f json (or "
            "QDO_FORMAT=json) so its SQL can be replayed."
        )

    command = payload.get("command")
    if command != "query":
        raise ValueError(
            f"Session step {ref} is a '{command}' step; --from only replays recorded "
            "'query' steps. Pick a step where qdo ran `query --sql` with -f json."
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(
            f"Session step {ref} has no reusable SQL in its envelope. The recorded JSON "
            "is missing a `data` object — the source step may have failed before emitting."
        )

    sql = data.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError(
            f"Session step {ref} has no reusable SQL in its envelope. The recorded JSON "
            "has no `data.sql` — the source step may have failed before emitting."
        )

    meta = payload.get("meta")
    source_connection = meta.get("connection") if isinstance(meta, dict) else None
    if not isinstance(source_connection, str):
        source_connection = None

    step_index = step.get("index")
    return {
        "ref": ref,
        "session": session_name,
        "step_index": step_index if isinstance(step_index, int) else None,
        "source_command": command,
        "source_connection": source_connection,
        "sql": sql,
    }


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


@dataclass
class ReplayStepResult:
    """One replayed step from a recorded session."""

    source_index: int | None
    cmd: str
    args: list[str]
    exit_code: int
    duration: float
    stdout: str = ""
    stderr: str = ""


@dataclass
class ReplayResult:
    """Summary of replaying a recorded session."""

    source_session: str
    replay_session: str
    steps: list[ReplayStepResult]

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def failed_step(self) -> ReplayStepResult | None:
        return next((step for step in self.steps if step.exit_code != 0), None)


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


def generate_replay_session_name(source: str) -> str:
    """Return a deterministic-ish session name for replay output."""
    return f"replay-{source}-{int(time.time())}"


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
    """Re-execute successful recorded steps from *name* in order.

    The replay itself is recorded into *into* (or an auto-generated
    ``replay-<name>-<ts>`` session) by setting ``QDO_SESSION`` on the child
    processes. Steps stop on first failure unless ``continue_on_error`` is
    true.
    """
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

    replay_name = into or generate_replay_session_name(name)
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
            [*_qdo_argv(), *args],
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


def _qdo_argv() -> list[str]:
    """Return the argv prefix that invokes qdo as a subprocess.

    Uses ``sys.executable -m querido`` unconditionally rather than looking up
    ``qdo`` on PATH.  This guarantees the child runs the same interpreter and
    module code as the parent and sidesteps Windows launcher / PATHEXT quirks
    that caused `shutil.which("qdo")` to resolve to an `.exe` whose argument
    forwarding broke ``session replay`` on Windows CI.
    """
    return [sys.executable, "-m", "querido"]


def _extract_row_count(stdout: str) -> int | None:
    """Best-effort row count extraction from a JSON envelope in *stdout*."""
    payload = _parse_structured_stdout(stdout)
    if payload is None:
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


def _parse_structured_stdout(stdout: str) -> dict | None:
    stripped = stdout.strip()
    if not stripped or not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _parse_step_reference(ref: str) -> tuple[str, str]:
    """Parse ``<session>:<step>`` where step is an integer or ``last``."""
    text = ref.strip()
    if not text or ":" not in text:
        raise ValueError(f"Invalid session step reference: {ref!r}. Use <session>:<step>.")
    session_name, step_token = text.split(":", 1)
    session_name = session_name.strip()
    step_token = step_token.strip().lower()
    if not session_name or not step_token:
        raise ValueError(f"Invalid session step reference: {ref!r}. Use <session>:<step>.")
    if step_token != "last":
        try:
            index = int(step_token)
        except ValueError as exc:
            raise ValueError(
                f"Invalid session step reference: {ref!r}. Use <session>:<step>."
            ) from exc
        if index <= 0:
            raise ValueError(f"Invalid session step reference: {ref!r}. Use <session>:<step>.")
    return session_name, step_token


def _select_step(steps: list[dict], step_token: str) -> dict | None:
    """Return the referenced step from *steps*."""
    if step_token == "last":
        return steps[-1] if steps else None

    wanted = int(step_token)
    for step in steps:
        if step.get("index") == wanted:
            return step
    return None


def active_session_name() -> str | None:
    """Return the session name from ``QDO_SESSION`` or None."""
    name = os.environ.get("QDO_SESSION", "").strip()
    return name or None
