"""Workflow runner — executes a workflow YAML end-to-end.

Design choices:

- Each step is run as a **subprocess** (``qdo <args>``), not in-process.
  This matches the session-recording model (every invocation appends one
  JSONL step) and guarantees the workflow step and an ad-hoc shell
  invocation are observationally identical.
- Captures are parsed as JSON — the author is responsible for passing
  ``-f json`` in the step's ``run`` line.  If no format flag is present
  and the step has a ``capture``, ``-f json`` is injected automatically.
- Steps run in document order.  On non-zero exit, the runner raises
  :class:`StepFailed` pointing at the step id (no retries, no
  ``continue_on_error``).
- A session is set up for the whole run.  If the caller has
  ``QDO_SESSION`` set, we inherit it; otherwise a fresh session named
  ``workflow-<slug>-<unix_ts>`` is created so every step is recorded.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from querido.core.workflow.expr import (
    ExpressionError,
    UnresolvedReference,
    evaluate_when,
    interpolate,
    resolve_output,
)


class WorkflowError(RuntimeError):
    """Base class for runner errors."""


class InputError(WorkflowError):
    """Raised when caller-supplied inputs don't match the workflow spec."""


class StepFailed(WorkflowError):
    """Raised when a subprocess step exits non-zero."""

    def __init__(self, step_id: str, exit_code: int, stderr: str, cmd: str) -> None:
        super().__init__(
            f"Step {step_id!r} failed with exit code {exit_code}: {stderr.strip() or cmd}"
        )
        self.step_id = step_id
        self.exit_code = exit_code
        self.stderr = stderr
        self.cmd = cmd


@dataclass
class StepRecord:
    """One executed (or skipped) step, for the caller to inspect or render."""

    id: str
    run: str
    skipped: bool = False
    exit_code: int = 0
    duration: float = 0.0
    stdout: str = ""
    stderr: str = ""
    capture: str | None = None


@dataclass
class RunResult:
    """The outcome of running a workflow."""

    outputs: dict[str, Any] = field(default_factory=dict)
    steps: list[StepRecord] = field(default_factory=list)
    session: str = ""


def bind_inputs(doc: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Validate and coerce caller-supplied *inputs* against the workflow's spec."""
    declared = doc.get("inputs") or {}
    bound: dict[str, Any] = {}

    unknown = set(inputs) - set(declared)
    if unknown:
        raise InputError(
            f"unknown input(s): {', '.join(sorted(unknown))}. "
            f"declared: {', '.join(sorted(declared)) or '(none)'}"
        )

    for name, spec in declared.items():
        if not isinstance(spec, dict):
            raise InputError(f"input spec for {name!r} is malformed")
        if name in inputs:
            bound[name] = _coerce_input(name, inputs[name], spec.get("type", "string"))
        elif "default" in spec:
            bound[name] = spec["default"]
        elif spec.get("required", False):
            raise InputError(f"required input missing: {name!r}")
        else:
            bound[name] = None
    return bound


def _coerce_input(name: str, value: Any, type_: str) -> Any:
    if isinstance(value, str):
        if type_ == "integer":
            try:
                return int(value)
            except ValueError as exc:
                raise InputError(f"input {name!r} must be an integer, got {value!r}") from exc
        if type_ == "number":
            try:
                return float(value)
            except ValueError as exc:
                raise InputError(f"input {name!r} must be a number, got {value!r}") from exc
        if type_ == "boolean":
            lowered = value.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                return True
            if lowered in ("false", "0", "no", "off"):
                return False
            raise InputError(f"input {name!r} must be a boolean, got {value!r}")
    return value


def _qdo_argv() -> list[str]:
    """Return the argv prefix that invokes qdo as a subprocess."""
    binary = shutil.which("qdo")
    if binary:
        return [binary]
    return [sys.executable, "-m", "querido"]


def _hoist_format_flag(tokens: list[str], has_capture: bool) -> list[str]:
    """Return *tokens* with any ``-f``/``--format`` extracted and placed right
    after the leading ``qdo`` so the flag is parsed by the root callback.

    If *has_capture* is true and no format flag is present, ``-f json`` is
    injected — capture requires JSON output.
    """
    if not tokens or tokens[0] != "qdo":
        return tokens

    fmt_value: str | None = None
    cleaned: list[str] = []
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok == "-f" or tok == "--format":
            if i + 1 < len(tokens):
                fmt_value = tokens[i + 1]
                i += 2
                continue
            i += 1
            continue
        if tok.startswith("--format="):
            fmt_value = tok.split("=", 1)[1]
            i += 1
            continue
        cleaned.append(tok)
        i += 1

    if fmt_value is None and has_capture:
        fmt_value = "json"
    if fmt_value is None:
        return tokens

    return [tokens[0], "-f", fmt_value, *cleaned]


def _session_env(workflow_name: str) -> tuple[dict[str, str], str]:
    env = os.environ.copy()
    existing = env.get("QDO_SESSION", "").strip()
    if existing:
        return env, existing
    session = f"workflow-{workflow_name}-{int(time.time())}"
    env["QDO_SESSION"] = session
    return env, session


def run_workflow(
    doc: dict[str, Any],
    inputs: dict[str, Any] | None = None,
    *,
    cwd: Path | None = None,
    verbose: bool = False,
    stderr: Any = None,
) -> RunResult:
    """Execute *doc*. See module docstring for semantics."""
    name = doc.get("name") or "workflow"
    bound = bind_inputs(doc, inputs or {})
    context: dict[str, Any] = dict(bound)

    env, session_name = _session_env(str(name))
    qdo = _qdo_argv()
    out_stderr = stderr if stderr is not None else sys.stderr
    result = RunResult(session=session_name)

    for step in doc.get("steps") or []:
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("id") or "")

        when_expr = step.get("when")
        if isinstance(when_expr, str) and when_expr.strip():
            try:
                keep = evaluate_when(when_expr, context)
            except (UnresolvedReference, ExpressionError) as exc:
                raise WorkflowError(f"step {step_id!r}: when-expression failed: {exc}") from exc
            if not keep:
                result.steps.append(StepRecord(id=step_id, run="", skipped=True))
                if verbose:
                    print(f"[{step_id}] skipped (when={when_expr!r})", file=out_stderr)
                continue

        raw_run = str(step.get("run") or "")
        capture = step.get("capture")
        has_capture = isinstance(capture, str) and bool(capture)
        try:
            rendered = interpolate(raw_run, context)
        except UnresolvedReference as exc:
            raise WorkflowError(f"step {step_id!r}: {exc}") from exc
        tokens = shlex.split(rendered)
        if not tokens or tokens[0] != "qdo":
            raise WorkflowError(f"step {step_id!r}: run must begin with 'qdo' (got {rendered!r})")
        tokens = _hoist_format_flag(tokens, has_capture)
        rendered = " ".join(shlex.quote(t) if any(c.isspace() for c in t) else t for t in tokens)
        argv = qdo + tokens[1:]

        if verbose:
            print(f"[{step_id}] $ {rendered}", file=out_stderr)

        start = time.monotonic()
        proc = subprocess.run(
            argv,
            env=env,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
        )
        duration = round(time.monotonic() - start, 4)

        record = StepRecord(
            id=step_id,
            run=rendered,
            exit_code=proc.returncode,
            duration=duration,
            stdout=proc.stdout,
            stderr=proc.stderr,
            capture=capture if has_capture else None,
        )
        result.steps.append(record)

        if proc.returncode != 0:
            raise StepFailed(
                step_id=step_id, exit_code=proc.returncode, stderr=proc.stderr, cmd=rendered
            )

        if verbose and proc.stdout:
            print(proc.stdout, file=out_stderr)

        if has_capture:
            try:
                parsed = json.loads(proc.stdout)
            except json.JSONDecodeError as exc:
                raise WorkflowError(
                    f"step {step_id!r}: capture requires JSON output but parse failed: {exc}. "
                    "Ensure the step's run line passes '-f json'."
                ) from exc
            context[str(capture)] = parsed

    outputs_spec = doc.get("outputs") or {}
    if isinstance(outputs_spec, dict):
        for key, expr in outputs_spec.items():
            # Outputs are lenient: a ref that can't resolve (typically because
            # the step producing its capture was skipped via ``when``) yields
            # null rather than aborting the whole workflow. Lint catches
            # genuinely-undefined refs at author time.
            try:
                result.outputs[key] = resolve_output(str(expr), context)
            except UnresolvedReference:
                result.outputs[key] = None

    return result


__all__ = [
    "InputError",
    "RunResult",
    "StepFailed",
    "StepRecord",
    "WorkflowError",
    "bind_inputs",
    "run_workflow",
]
