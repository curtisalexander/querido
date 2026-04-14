"""Self-hosting eval for qdo workflow-authoring docs.

Feeds ``WORKFLOW_AUTHORING.md`` + ``qdo workflow spec`` + bundled examples
to ``claude -p`` as context and asks the model to produce three target
workflows it has not seen.  Pass criterion per task: ``qdo workflow lint``
exits 0, ``qdo workflow run`` exits 0, and a lightweight shape assertion
on the output envelope succeeds.

Why this exists: without an objective signal, "our docs are good enough"
is a gut call.  The PLAN target is >=2 of 3 tasks pass on a frontier
model; failures drive a docs revision, not a model change.

Usage::

    unset ANTHROPIC_API_KEY            # avoid silent API billing
    uv run python scripts/eval_workflow_authoring.py

    # Pass --task N to run just one task.
    uv run python scripts/eval_workflow_authoring.py --task 1

CI note (2026-04-14): we deliberately do *not* wire this into GitHub
Actions right now.  ``claude -p`` requires a Max subscription, and the
eval is not cheap to run on every PR.  Intended cadence: run locally
after any revision to ``WORKFLOW_AUTHORING.md`` or the workflow
implementation.  If we later want to automate it, add a
``workflow_dispatch``-only GitHub Action that calls this script.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
AUTHORING_DOC = REPO / "integrations" / "skills" / "WORKFLOW_AUTHORING.md"
FIXTURE_DB = REPO / "data" / "test.duckdb"

MODEL = "claude-opus-4-6"
TASK_TIMEOUT_SEC = 120  # bound each claude -p call
RUN_TIMEOUT_SEC = 60  # bound each workflow run

SYSTEM_PROMPT = textwrap.dedent(
    """
    You are authoring a qdo workflow — a YAML file that composes qdo commands
    into a parameterized, repeatable investigation.

    Rules:
    - Your reply MUST be exactly one YAML document — no prose, no backticks,
      no ```yaml``` fence. Just the YAML body starting at the ``name:`` field.
    - The workflow must pass ``qdo workflow lint`` with zero issues.
    - Follow the spec and patterns in the authoring guide below. Do not invent
      fields. Do not use shell pipelines. Do not embed code.
    - Only emit qdo invocations in step ``run`` lines.
    """
).strip()


@dataclass
class Task:
    """One eval task — prompt, inputs to bind, and a shape assertion."""

    id: str
    prompt: str
    inputs: dict[str, str]
    assertion: str  # human-readable name for logs

    def check_outputs(self, envelope: dict[str, Any]) -> tuple[bool, str]:
        """Return (ok, reason) for a shape assertion on the run envelope.

        *envelope* is the parsed JSON output of ``qdo workflow run``. Its
        ``data.outputs`` and ``data.steps`` fields are what we inspect.
        """
        data = envelope.get("data") or {}
        outputs = data.get("outputs") or {}
        steps = data.get("steps") or []
        step_ids = [s.get("id") for s in steps if isinstance(s, dict)]

        if self.id == "t1_basic_composition":
            # Must expose at least row_count and one column-shaped output.
            if "row_count" not in outputs:
                return False, "missing output 'row_count'"
            has_cols_output = any(
                k for k in outputs if "column" in k.lower() or "null" in k.lower()
            )
            if not has_cols_output:
                return False, "no column/null-shaped output key"
            return True, "row_count + column/null output present"

        if self.id == "t2_conditional_followup":
            # Must have a quality-style step and a conditional step that
            # either ran or was skipped (both are valid — the conditional
            # behaved according to quality's result).
            if not any("quality" in (sid or "") for sid in step_ids):
                return False, "no quality-style step id found"
            if len(steps) < 2:
                return False, "expected at least two steps"
            # The second+ steps must carry a 'skipped' field (required of
            # every step record) — this indirectly confirms the workflow ran.
            if any("skipped" not in (s or {}) for s in steps):
                return False, "step record missing 'skipped' field"
            return True, f"quality-first with {len(steps)} steps"

        if self.id == "t3_diff_then_joins":
            # Must have a diff step and a joins step (joins may be skipped).
            has_diff = any("diff" in (sid or "") for sid in step_ids)
            has_joins = any("join" in (sid or "") for sid in step_ids)
            if not (has_diff and has_joins):
                return False, f"steps {step_ids} missing diff or joins"
            # Outputs should expose something about the diff.
            if not outputs:
                return False, "outputs is empty"
            return True, f"diff+joins present; outputs: {sorted(outputs)}"

        return False, f"unknown task id {self.id!r}"


TASKS: list[Task] = [
    Task(
        id="t1_basic_composition",
        prompt=textwrap.dedent(
            """
            Write a qdo workflow called ``row-and-null-report`` that takes a
            connection and a table as inputs and produces:

            - a ``row_count`` output (integer row count from the table),
            - a ``columns`` output (the full list of column metadata from
              inspect),
            - a ``null_percentages`` output (profile's per-column stats, from
              which null rates can be read).

            Use ``qdo inspect`` and ``qdo profile --quick``. Both steps should
            capture their JSON output.
            """
        ).strip(),
        inputs={"connection": str(FIXTURE_DB), "table": "customers"},
        assertion="row_count + column/null outputs present",
    ),
    Task(
        id="t2_conditional_followup",
        prompt=textwrap.dedent(
            """
            Write a qdo workflow called ``quality-then-context`` that takes a
            connection and a table as inputs. It should:

            1. Run ``qdo quality`` on the table (capture as ``quality``).
            2. Only if the quality result's ``data.columns`` list is non-empty,
               also run ``qdo context`` (capture as ``context``). Use a
               ``when:`` expression referring to ``${quality.data.columns}``.

            Expose ``quality_columns`` (from quality) and ``context_columns``
            (from context) as outputs.
            """
        ).strip(),
        inputs={"connection": str(FIXTURE_DB), "table": "customers"},
        assertion="quality step + conditional second step with 'skipped' field",
    ),
    Task(
        id="t3_diff_then_joins",
        prompt=textwrap.dedent(
            """
            Write a qdo workflow called ``diff-then-joins`` that takes three
            inputs: a ``connection``, a ``left`` table, and a ``right`` table.

            Steps:

            1. Run ``qdo diff -c ${connection} -t ${left} --target ${right}``
               and capture as ``diff``.
            2. Only when the diff reports any schema change (added, removed,
               or changed columns are non-empty), run ``qdo joins -c
               ${connection} -t ${left} --target ${right}`` and capture as
               ``joins``.

            Outputs must include ``added_columns``, ``removed_columns``,
            ``changed_columns`` (from the diff) and ``candidate_join_keys``
            (from joins, referencing ``${joins.data.candidates}``).
            """
        ).strip(),
        inputs={"connection": str(FIXTURE_DB), "left": "customers", "right": "products"},
        assertion="diff + joins steps, diff outputs exposed",
    ),
]


def main() -> int:
    args = _parse_args()
    _preflight()

    authoring_doc = AUTHORING_DOC.read_text(encoding="utf-8")
    spec_json = _run_qdo(["workflow", "spec"])
    examples_yaml = _run_qdo(["workflow", "spec", "--examples"])

    tasks = TASKS if args.task is None else [TASKS[args.task - 1]]
    results: list[tuple[Task, bool, str]] = []

    for task in tasks:
        print(f"\n=== Task {task.id} ===")
        ok, reason = _run_task(task, authoring_doc, spec_json, examples_yaml, args)
        print(f"  -> {'PASS' if ok else 'FAIL'}: {reason}")
        results.append((task, ok, reason))

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\nResult: {passed}/{total} tasks passed (target: >= 2/3).")

    # Per PLAN: "≥2 of 3 tasks pass on frontier model".
    return 0 if passed >= max(2, total - 1) else 1


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Self-hosting eval for qdo workflow-authoring docs.")
    p.add_argument(
        "--task", type=int, choices=[1, 2, 3], help="Run only task N (default: all three)."
    )
    p.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep the per-task scratch dirs so you can inspect the generated YAML.",
    )
    return p.parse_args()


def _preflight() -> None:
    """Fail fast with actionable errors before spending model tokens."""
    if not shutil.which("claude"):
        sys.exit(
            "error: 'claude' CLI not on PATH. Install Claude Code "
            "(https://claude.com/claude-code) and ensure `claude -p` works."
        )
    if os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "error: ANTHROPIC_API_KEY is set. Unset it before running this eval "
            "('unset ANTHROPIC_API_KEY') — otherwise `claude -p` will silently "
            "bill the API instead of using your Max subscription."
        )
    if not AUTHORING_DOC.is_file():
        sys.exit(f"error: authoring doc not found: {AUTHORING_DOC}")
    if not FIXTURE_DB.is_file():
        sys.exit(
            f"error: fixture DB not found: {FIXTURE_DB}. "
            "Run 'uv run python scripts/init_test_data.py' first."
        )
    if not shutil.which("qdo"):
        sys.exit("error: 'qdo' not on PATH. Install the package in editable mode (uv sync).")


def _run_qdo(args: list[str]) -> str:
    """Run ``qdo <args>`` and return stdout; die on non-zero exit."""
    proc = subprocess.run(["qdo", *args], capture_output=True, text=True, check=False, timeout=30)
    if proc.returncode != 0:
        sys.exit(f"error: 'qdo {' '.join(args)}' exited {proc.returncode}:\n{proc.stderr}")
    return proc.stdout


def _run_task(
    task: Task,
    authoring_doc: str,
    spec_json: str,
    examples_yaml: str,
    args: argparse.Namespace,
) -> tuple[bool, str]:
    user_prompt = _build_prompt(task, authoring_doc, spec_json, examples_yaml)
    scratch = Path(tempfile.mkdtemp(prefix=f"qdo-eval-{task.id}-", dir=tempfile.gettempdir()))
    if not args.keep_artifacts:
        # Scheduled cleanup so we don't pile up tmpdirs on failure.
        import atexit

        atexit.register(lambda: shutil.rmtree(scratch, ignore_errors=True))

    prompt_path = scratch / "prompt.txt"
    prompt_path.write_text(user_prompt, encoding="utf-8")

    wf_dir = scratch / ".qdo" / "workflows"
    wf_dir.mkdir(parents=True)

    print(f"  scratch: {scratch}")
    print("  calling claude -p ...")
    try:
        claude = subprocess.run(
            ["claude", "-p", "--model", MODEL, "--append-system-prompt", SYSTEM_PROMPT],
            input=user_prompt,
            capture_output=True,
            text=True,
            timeout=TASK_TIMEOUT_SEC,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"claude -p timed out after {TASK_TIMEOUT_SEC}s"
    if claude.returncode != 0:
        return False, f"claude -p exited {claude.returncode}: {claude.stderr.strip()[:200]}"

    yaml_text = _extract_yaml(claude.stdout)
    (scratch / "raw.txt").write_text(claude.stdout, encoding="utf-8")

    # Read the workflow's declared name so we can write the file under that
    # name — the loader searches by internal ``name:``, not filename, but
    # keeping them aligned is the convention and makes 'workflow list' tidy.
    try:
        import yaml as pyyaml

        doc = pyyaml.safe_load(yaml_text)
        wf_name = doc.get("name") if isinstance(doc, dict) else None
    except Exception as exc:
        return False, f"yaml parse failed: {exc}"
    if not wf_name:
        return False, "workflow yaml has no 'name' field"

    yaml_path = wf_dir / f"{wf_name}.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    # 1. Lint.
    lint = subprocess.run(
        ["qdo", "-f", "json", "workflow", "lint", str(yaml_path)],
        capture_output=True,
        text=True,
        cwd=scratch,
        check=False,
    )
    if lint.returncode != 0:
        try:
            issues = json.loads(lint.stdout).get("data", {}).get("issues", [])
        except json.JSONDecodeError:
            issues = []
        return False, f"lint failed: {[i.get('code') for i in issues] or lint.stdout[:200]}"

    # 2. Run, binding inputs.
    run_argv = [
        "qdo",
        "-f",
        "json",
        "workflow",
        "run",
        wf_name,
        *(f"{k}={v}" for k, v in task.inputs.items()),
    ]
    try:
        run = subprocess.run(
            run_argv,
            capture_output=True,
            text=True,
            cwd=scratch,
            check=False,
            timeout=RUN_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return False, f"workflow run timed out after {RUN_TIMEOUT_SEC}s"
    if run.returncode != 0:
        return False, f"workflow run failed ({run.returncode}): {run.stderr.strip()[:300]}"

    # 3. Shape assertion on the envelope.
    try:
        envelope = json.loads(run.stdout)
    except json.JSONDecodeError as exc:
        return False, f"workflow run stdout not JSON: {exc}"
    ok, reason = task.check_outputs(envelope)
    return ok, reason


def _build_prompt(task: Task, authoring_doc: str, spec_json: str, examples_yaml: str) -> str:
    return textwrap.dedent(
        f"""
        You are writing a qdo workflow.

        ## Task

        {task.prompt}

        ## Authoring guide (WORKFLOW_AUTHORING.md)

        {authoring_doc}

        ## Authoritative JSON Schema (output of `qdo workflow spec`)

        {spec_json}

        ## Bundled example workflows (output of `qdo workflow spec --examples`)

        {examples_yaml}

        ## Reminder

        Reply with exactly one YAML document — no prose, no fences. The YAML
        must pass `qdo workflow lint`. Use the inputs named exactly:
        {", ".join(task.inputs)}.
        """
    ).strip()


_FENCE_RE = re.compile(r"^```(?:ya?ml)?\s*\n(.*?)\n```", re.DOTALL | re.MULTILINE)


def _extract_yaml(text: str) -> str:
    """Pull a YAML body out of the model's reply, tolerating markdown fences."""
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip() + "\n"
    # No fence — hope the reply is bare YAML. Trim any leading prose before
    # the first ``name:`` line if the model slipped and included preamble.
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("name:"):
            return "\n".join(lines[i:]).strip() + "\n"
    return text.strip() + "\n"


if __name__ == "__main__":
    sys.exit(main())
