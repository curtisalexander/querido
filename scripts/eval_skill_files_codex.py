"""Self-hosting eval for qdo skill files using Codex.

Runs the same task catalog as ``scripts/eval_skill_files_claude.py`` but executes the
agent with ``codex exec`` instead of ``claude -p``. This keeps the benchmark
questions, pass/fail rules, and artifact logging aligned across both agents.

Usage::

    uv run python scripts/eval_skill_files_codex.py
    uv run python scripts/eval_skill_files_codex.py --models gpt-5.4-mini,gpt-5.4
    uv run python scripts/eval_skill_files_codex.py --tasks A1_list_tables,D3_table_report
"""

from __future__ import annotations

import argparse
import atexit
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
_BASE_SPEC = importlib.util.spec_from_file_location(
    "eval_skill_files_claude", SCRIPT_DIR / "eval_skill_files_claude.py"
)
if _BASE_SPEC is None or _BASE_SPEC.loader is None:
    raise RuntimeError("Could not load scripts/eval_skill_files_claude.py")
base: Any = importlib.util.module_from_spec(_BASE_SPEC)
sys.modules["eval_skill_files_claude"] = base
_BASE_SPEC.loader.exec_module(base)

REPO = base.REPO
FIXTURE_DB = base.FIXTURE_DB
RESULTS_DIR = base.RESULTS_DIR
SKILL_FILES = base.SKILL_FILES

TASK_TIMEOUT_SEC = base.TASK_TIMEOUT_SEC
QDO_TIMEOUT_SEC = base.QDO_TIMEOUT_SEC
DEFAULT_MODELS = ["gpt-5.4-mini"]
ALL_MODELS = ["gpt-5.4-mini", "gpt-5.4"]


def main() -> int:
    args = _parse_args()
    _preflight()

    tasks = base._select_tasks(args.tasks)
    models = _select_models(args.models)

    skill_content = base._concat_skill_files()
    system_prompt = base.SYSTEM_PROMPT_TMPL.format(skill_files_content=skill_content)

    results: list[dict[str, Any]] = []
    for task in tasks:
        for model in models:
            print(f"\n=== {task.id} [{model}] ===")
            result = run_task(task, model, system_prompt, args)
            base._print_task_result(result)
            results.append(result)

            if result.get("failure_category") in {"auth-error", "transport-error"}:
                print(
                    "\nerror: Codex could not complete the run. "
                    "Check `codex login` and network access, then retry."
                )
                break
        else:
            continue
        break

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"results_codex_{stamp}.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    base._print_summary(results, out_path)
    return _exit_code(results)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Self-hosting eval for qdo skill files via Codex.")
    p.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help=(
            "Comma-separated Codex model names. Use 'all' for a small built-in "
            f"set ({', '.join(ALL_MODELS)}). Default: {DEFAULT_MODELS[0]}."
        ),
    )
    p.add_argument(
        "--tasks",
        default=None,
        help=(
            "Comma-separated task IDs to run (e.g. A1_list_tables,D3_table_report). "
            "Default: all tasks."
        ),
    )
    p.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep per-task scratch dirs and raw Codex JSONL logs for inspection.",
    )
    return p.parse_args()


def _preflight() -> None:
    if not shutil.which("codex"):
        sys.exit("error: 'codex' CLI not on PATH. Install Codex and ensure `codex exec` works.")
    if not FIXTURE_DB.is_file():
        sys.exit(
            f"error: fixture DB not found: {FIXTURE_DB}. "
            "Run 'uv run python scripts/init_test_data.py' first."
        )
    for f in SKILL_FILES:
        if not f.is_file():
            sys.exit(f"error: skill file not found: {f}")
    if not shutil.which("qdo"):
        sys.exit("error: 'qdo' not on PATH. Install the package in editable mode (uv sync).")


def _select_models(spec: str) -> list[str]:
    if spec.strip().lower() == "all":
        return list(ALL_MODELS)
    return [s.strip() for s in spec.split(",") if s.strip()]


def run_task(
    task: base.Task,
    model: str,
    system_prompt: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    t_start = time.monotonic()

    scratch = Path(tempfile.mkdtemp(prefix=f"qdo-eval-codex-{task.id}-{model}-"))
    if not args.keep_artifacts:
        atexit.register(lambda p=scratch: shutil.rmtree(p, ignore_errors=True))

    base._run_pre_task(task, cwd=scratch)

    prompt = task.prompt.format(db=str(FIXTURE_DB))
    final_path = scratch / "final.txt"
    print(f"  scratch: {scratch}")
    print(f"  prompt: {prompt}")

    full_prompt = textwrap.dedent(
        f"""
        {system_prompt}

        ## User task

        {prompt}
        """
    ).strip()

    codex_argv = [
        "codex",
        "exec",
        "--json",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--add-dir",
        str(REPO),
        "--cd",
        str(scratch),
        "--output-last-message",
        str(final_path),
        "--model",
        model,
        full_prompt,
    ]

    env = os.environ.copy()
    try:
        proc = subprocess.run(
            codex_argv,
            cwd=scratch,
            capture_output=True,
            text=True,
            timeout=TASK_TIMEOUT_SEC,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stream_text = _coerce_timeout_stream(exc.stdout)
        stderr_text = _coerce_timeout_stream(exc.stderr)
        if stream_text:
            (scratch / "stream.jsonl").write_text(stream_text, encoding="utf-8")
        if stderr_text:
            (scratch / "stderr.txt").write_text(stderr_text, encoding="utf-8")

        final_text = final_path.read_text(encoding="utf-8") if final_path.exists() else ""
        qdo_commands, tool_errors, usage = parse_codex_json(stream_text)

        artifact_result = _artifact_success_result(
            task=task,
            model=model,
            prompt=prompt,
            scratch=scratch,
            qdo_commands=qdo_commands,
            tool_errors=tool_errors,
            usage=usage,
            duration_sec=round(time.monotonic() - t_start, 2),
            keep_artifacts=args.keep_artifacts,
        )
        if artifact_result is not None:
            return artifact_result

        return {
            "task_id": task.id,
            "category": task.category,
            "model": model,
            "status": "fail",
            "failure_category": "timeout",
            "reason": f"codex exec timed out after {TASK_TIMEOUT_SEC}s",
            "duration_sec": round(time.monotonic() - t_start, 2),
            "scratch": str(scratch) if args.keep_artifacts else None,
            "qdo_commands": qdo_commands,
            "tool_errors": tool_errors,
            "final_text_snippet": (final_text or "")[:1000],
            "usage": usage,
        }

    stream_text = proc.stdout
    (scratch / "stream.jsonl").write_text(stream_text, encoding="utf-8")
    if proc.stderr:
        (scratch / "stderr.txt").write_text(proc.stderr, encoding="utf-8")

    final_text = final_path.read_text(encoding="utf-8") if final_path.exists() else ""
    qdo_commands, tool_errors, usage = parse_codex_json(stream_text)

    if final_text:
        (scratch / "final.txt").write_text(final_text, encoding="utf-8")

    failure_category = _transport_or_auth_error(stream_text, proc.stderr, final_text)
    if failure_category is not None:
        return {
            "task_id": task.id,
            "category": task.category,
            "model": model,
            "prompt": prompt,
            "status": "fail",
            "failure_category": failure_category,
            "reason": (
                "codex exec isn't authenticated — run `codex login` first"
                if failure_category == "auth-error"
                else "codex exec could not reach the model backend"
            ),
            "path_ok": False,
            "qdo_commands": qdo_commands,
            "tool_errors": tool_errors,
            "final_text_snippet": (final_text or proc.stderr or stream_text)[:500],
            "usage": usage,
            "duration_sec": round(time.monotonic() - t_start, 2),
            "scratch": str(scratch) if args.keep_artifacts else None,
            "gotcha": task.gotcha,
        }

    check = base.check_pass(task, qdo_commands, tool_errors, final_text)
    return {
        "task_id": task.id,
        "category": task.category,
        "model": model,
        "prompt": prompt,
        **check,
        "qdo_commands": qdo_commands,
        "tool_errors": tool_errors,
        "final_text_snippet": (final_text or "")[:1000],
        "usage": usage,
        "duration_sec": round(time.monotonic() - t_start, 2),
        "scratch": str(scratch) if args.keep_artifacts else None,
        "gotcha": task.gotcha,
    }


def parse_codex_json(text: str) -> tuple[list[str], list[str], dict[str, Any]]:
    """Parse ``codex exec --json`` output.

    Codex's event schema is broader than the Claude stream-json shape, so this
    parser is intentionally tolerant: it recursively looks for ``command`` /
    ``cmd`` string fields that resemble qdo invocations and collects likely
    error snippets from explicit error events or tool output mentioning non-zero
    exits.
    """
    qdo_commands: list[str] = []
    tool_errors: list[str] = []
    usage: dict[str, Any] = {}
    seen_cmds: set[str] = set()

    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        for cmd in _extract_commands(event):
            if cmd not in seen_cmds:
                seen_cmds.add(cmd)
                qdo_commands.append(cmd)

        err = _extract_error_text(event)
        if err:
            tool_errors.append(err[:500])

        if event.get("type") == "usage":
            usage.update(event)

    return qdo_commands, tool_errors, usage


def _extract_commands(obj: Any) -> list[str]:
    cmds: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {"command", "cmd"} and isinstance(value, str):
                normalized = _normalize_qdo_command(value)
                if normalized is not None:
                    cmds.append(normalized)
            cmds.extend(_extract_commands(value))
    elif isinstance(obj, list):
        for item in obj:
            cmds.extend(_extract_commands(item))
    return cmds


def _normalize_qdo_command(text: str) -> str | None:
    candidate = text.strip()
    if base._looks_like_qdo(candidate):
        return candidate

    # codex exec emits shell-wrapped commands like:
    # /bin/zsh -lc 'qdo -f json catalog -c /db'
    shell_match = re.search(r"(qdo(?:\s+|$).+)", candidate)
    if shell_match is None:
        return None

    inner = shell_match.group(1).strip()
    inner = inner.rstrip("'\"")
    if base._looks_like_qdo(inner):
        return inner
    return None


def _extract_error_text(event: dict[str, Any]) -> str | None:
    etype = str(event.get("type") or "")
    if etype == "error":
        msg = event.get("message")
        return str(msg) if msg else None

    snippets = _extract_text_fields(event)
    for snippet in snippets:
        if base._is_click_usage_error(snippet):
            return snippet
        if re.search(r"exit\s*code\s*[1-9]", snippet, re.IGNORECASE):
            return snippet
        if "traceback" in snippet.lower():
            return snippet
    return None


def _extract_text_fields(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for value in obj.values():
            out.extend(_extract_text_fields(value))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_extract_text_fields(item))
    elif isinstance(obj, str):
        out.append(obj)
    return out


_CODEX_AUTH_RE = re.compile(r"unauthorized|not\s+logged\s+in|run\s+codex\s+login", re.IGNORECASE)
_CODEX_TRANSPORT_RE = re.compile(
    r"failed to lookup address information|could not reach the model backend|api\.openai\.com|"
    r"stream disconnected|reconnecting",
    re.IGNORECASE,
)


def _transport_or_auth_error(stdout: str, stderr: str, final_text: str) -> str | None:
    haystack = "\n".join([stdout or "", stderr or "", final_text or ""])
    if _CODEX_AUTH_RE.search(haystack):
        return "auth-error"
    if _CODEX_TRANSPORT_RE.search(haystack):
        return "transport-error"
    return None


def _coerce_timeout_stream(text: str | bytes | None) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return text


def _artifact_success_result(
    *,
    task: base.Task,
    model: str,
    prompt: str,
    scratch: Path,
    qdo_commands: list[str],
    tool_errors: list[str],
    usage: dict[str, Any],
    duration_sec: float,
    keep_artifacts: bool,
) -> dict[str, Any] | None:
    artifact_text = _artifact_success_text(task, scratch)
    if artifact_text is None:
        return None

    inferred_commands = list(qdo_commands)
    if not inferred_commands and task.id == "D2_init_metadata":
        inferred_commands = [f"qdo metadata init -c {FIXTURE_DB} -t orders"]

    check = base.check_pass(task, inferred_commands, tool_errors, artifact_text)
    return {
        "task_id": task.id,
        "category": task.category,
        "model": model,
        "prompt": prompt,
        **check,
        "reason": "expected artifact was created before codex timed out",
        "qdo_commands": inferred_commands,
        "tool_errors": tool_errors,
        "final_text_snippet": artifact_text[:1000],
        "usage": usage,
        "duration_sec": duration_sec,
        "scratch": str(scratch) if keep_artifacts else None,
        "gotcha": task.gotcha,
    }


def _artifact_success_text(task: base.Task, scratch: Path) -> str | None:
    if task.id == "D2_init_metadata":
        matches = sorted(scratch.glob(".qdo/metadata/*/orders.yaml"))
        if matches:
            return f"Metadata YAML was written to {matches[0]}"
    if task.id == "D3_table_report":
        report = scratch / "orders-report.html"
        if report.is_file():
            return f"Created HTML report at {report}"
    if task.id == "D4_bundle_export":
        bundle = scratch / "orders-bundle.zip"
        if bundle.is_file():
            return f"Created bundle at {bundle}"
    return None


def _exit_code(results: list[dict[str, Any]]) -> int:
    """Codex runs are exploratory today: any failure should surface non-zero."""
    return 0 if all(r["status"] == "pass" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
