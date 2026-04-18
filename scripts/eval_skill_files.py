"""Self-hosting eval for qdo skill files — EV.Build from PLAN.md.

Feeds ``SKILL.md`` + ``WORKFLOW_EXAMPLES.md`` + ``AGENTS.md`` as context to
``claude -p`` and asks the model to answer realistic data-exploration
questions using only the qdo CLI against ``data/test.duckdb``. Each task
has:

- A natural-language prompt (the model must pick qdo commands itself)
- A set of required ``qdo <subcommand>`` prefixes (at least one must be used)
- A content regex (must match somewhere in the model's final answer)
- A set of preferred commands (logged as ``path_ok`` — bonus, not a gate)

Failures are categorized so a docs gap can be told apart from a qdo bug
(see PLAN.md → "Eval-design proposal findings (EV.x)" → EV.4).

Usage::

    unset ANTHROPIC_API_KEY            # avoid silent API billing
    uv run python scripts/eval_skill_files.py                       # haiku only
    uv run python scripts/eval_skill_files.py --models all          # haiku+sonnet+opus
    uv run python scripts/eval_skill_files.py --tasks A1_list_tables,B1_enumerate_enum
    uv run python scripts/eval_skill_files.py --budget 5.00

Local-only by default. Requires Claude Code Max (``claude -p`` uses the
subscription, not ANTHROPIC_API_KEY). Refuses to run if the API key is set
so billing can't go silently through.

CI note: deliberately not wired into GitHub Actions. If you want to
automate, use ``workflow_dispatch``-only with explicit budget gates.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
SKILL_FILES = [
    REPO / "integrations" / "skills" / "SKILL.md",
    REPO / "integrations" / "skills" / "WORKFLOW_EXAMPLES.md",
    REPO / "AGENTS.md",
]
FIXTURE_DB = REPO / "data" / "test.duckdb"
RESULTS_DIR = REPO / "scripts" / "eval_results"

# ``claude -p --model`` accepts aliases. Longer names also work.
MODEL_ALIASES = ["haiku", "sonnet", "opus"]

TASK_TIMEOUT_SEC = 240  # generous — multi-step tasks with several qdo calls
QDO_TIMEOUT_SEC = 30  # any one qdo subprocess

# Rough public pricing as of 2026-04 (USD per 1M tokens, input / output).
# Used for the preflight cost estimate only; real billing tracks the
# subscription usage reported by claude -p itself (see ``cost_usd`` in the
# result event).
PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "haiku": (1.00, 5.00),
    "sonnet": (3.00, 15.00),
    "opus": (15.00, 75.00),
}

# Rough per-task usage in tokens (prompt + output). Skill files dominate
# the prompt; calibrated from the Phase 4.6 eval's actual usage.
ESTIMATED_TOKENS_PER_TASK = {"prompt": 15_000, "output": 1_500}


SYSTEM_PROMPT_TMPL = textwrap.dedent(
    """
    You are pairing with a data analyst who uses the qdo CLI to explore a
    local database. Answer the user's question by running qdo commands and
    synthesizing their output. Use the reference docs below to pick the
    right commands.

    Ground rules:
    - Use qdo commands — do not write custom SQL unless the user explicitly
      asks for it, and do not install extra tools.
    - Run commands with ``-f json`` when you need structured output.
    - Be concise in your final answer. The user cares about the data, not
      a running commentary.
    - The database you are exploring is at the exact path the user gives
      you — pass it verbatim as ``-c <path>``.

    ## Reference: qdo skill files

    {skill_files_content}
    """
).strip()


# ---------------------------------------------------------------------------
# Task definitions
# ---------------------------------------------------------------------------


@dataclass
class Task:
    """One eval task.

    ``required_commands`` is a list of qdo subcommand prefixes
    (e.g. ``"qdo joins"``); at least one must appear in the model's Bash
    tool-call stream.

    ``content_regex`` is a list of patterns; at least one must match
    somewhere in the model's final answer text.

    ``preferred_commands`` is used for the ``path_ok`` metric — if any
    matches, the path was "clean"; if not, the task still passes but we
    log the preferred-vs-actual gap for docs tightening.

    ``pre_task`` is a list of qdo argvs to run before the model sees the
    prompt — for tasks like D1 (show stored metadata) that need a
    ``metadata init`` first.
    """

    id: str
    category: str
    prompt: str
    required_commands: list[str]
    content_regex: list[str]
    preferred_commands: list[str] = field(default_factory=list)
    max_commands: int = 12
    pre_task: list[list[str]] = field(default_factory=list)
    # Short note on the Wave 1 gotcha this task exercises (for the report).
    gotcha: str = ""


TASKS: list[Task] = [
    # ---- Category A: Database discovery ----
    Task(
        id="A1_list_tables",
        category="A",
        prompt=(
            "I have a new DuckDB database at {db}. Show me every table in it "
            "and its row count. One-sentence summary is fine."
        ),
        required_commands=["qdo catalog"],
        content_regex=[r"(?i)customers", r"(?i)products", r"(?i)orders"],
        preferred_commands=["qdo catalog"],
        gotcha="CS.1 — fixture must have orders for this to pass.",
    ),
    Task(
        id="A2_join_keys",
        category="A",
        prompt=(
            "In {db}, what are the likely join keys between the orders table "
            "and the other tables? Give me the column pairs."
        ),
        required_commands=["qdo joins"],
        content_regex=[r"customer_id", r"product_id"],
        preferred_commands=["qdo joins"],
        gotcha="CS.7 — joins was missing from SKILL.md quick workflow pre-Wave-1.",
    ),
    Task(
        id="A3_summarize_table",
        category="A",
        prompt=(
            "In {db}, give me a full summary of the orders table — schema, "
            "basic stats, and any obvious data-quality issues."
        ),
        required_commands=[
            "qdo workflow run",
            "qdo context",
            "qdo inspect",
            "qdo profile",
            "qdo quality",
        ],
        content_regex=[r"(?i)orders", r"(?i)(status|amount|region|order_date)"],
        preferred_commands=["qdo workflow run table-summary", "qdo context"],
        gotcha="Discovers whether agent finds table-summary bundled workflow or hand-composes.",
    ),
    # ---- Category B: Column-level exploration ----
    Task(
        id="B1_enumerate_enum",
        category="B",
        prompt=(
            "In {db}, what are the distinct values in the orders.status "
            "column? Include counts if available."
        ),
        required_commands=["qdo values"],
        content_regex=[r"shipped", r"delivered"],
        preferred_commands=["qdo values"],
        gotcha="CS.6 — values was undiscovered in the main SKILL.md flow pre-Wave-1.",
    ),
    Task(
        id="B2_profile_numeric",
        category="B",
        prompt=(
            "In {db}, describe the distribution of orders.amount. I want "
            "min, max, mean, and null count at minimum."
        ),
        required_commands=["qdo profile", "qdo dist", "qdo context"],
        content_regex=[r"(?i)(min|max|mean|average)"],
        preferred_commands=["qdo profile", "qdo dist"],
        gotcha="Model might reach for qdo query with custom SQL instead.",
    ),
    Task(
        id="B3_null_rates",
        category="B",
        prompt=(
            "In {db}, which columns in the customers table have the highest "
            "null rates? Name the top three."
        ),
        required_commands=["qdo profile", "qdo quality", "qdo context"],
        content_regex=[r"(?i)(phone2|company|website)"],
        preferred_commands=["qdo profile", "qdo quality"],
        gotcha="CS.10 — quality vs profile roles weren't disambiguated pre-Wave-1.",
    ),
    # ---- Category C: Data quality & invariants ----
    Task(
        id="C1_quality_issues",
        category="C",
        prompt=(
            "In {db}, are there any data-quality issues in the orders "
            "table? Flag anything unusual — null rates, malformed values, "
            "uniqueness problems."
        ),
        required_commands=["qdo quality"],
        content_regex=[r"(?i)(status|amount|null|quality|issue)"],
        preferred_commands=["qdo quality"],
        gotcha="Fixture has ~0.8% bad status + 1.5% negative amount — quality should flag.",
    ),
    Task(
        id="C2_schema_drift",
        category="C",
        prompt=(
            "In {db}, compare the schemas of the customers and products "
            "tables. Which columns are different?"
        ),
        required_commands=["qdo diff"],
        content_regex=[r"(?i)(added|removed|changed|differ|only in)"],
        preferred_commands=["qdo diff"],
        gotcha="CA.4 — diff -f json was absent pre-Wave-1 (verified wired, false positive).",
    ),
    Task(
        id="C3_assert_row_count",
        category="C",
        prompt=(
            "In {db}, assert that the orders table has at least 1000 rows. "
            "Tell me whether the assertion passed or failed."
        ),
        required_commands=["qdo assert"],
        content_regex=[r"(?i)(pass|ok|true|5000|satisfied)"],
        preferred_commands=["qdo assert"],
        gotcha="CA.3 — assert was invisible to SKILL.md pre-Wave-2.",
    ),
    # ---- Category D: Metadata & SQL generation ----
    Task(
        id="D1_stored_metadata",
        category="D",
        prompt=(
            "In {db}, show me the stored metadata for the orders table — "
            "the description, the owner, and the per-column details."
        ),
        required_commands=["qdo metadata show"],
        content_regex=[r"(?i)(description|owner|columns|table)"],
        preferred_commands=["qdo metadata show"],
        pre_task=[
            ["qdo", "metadata", "init", "-c", str(FIXTURE_DB), "-t", "orders", "--force"],
        ],
        gotcha="CS.3 — metadata show envelope wired in Wave 1.",
    ),
    Task(
        id="D2_sql_scaffold",
        category="D",
        prompt=(
            "In {db}, generate a SELECT statement for the orders table that includes every column."
        ),
        required_commands=["qdo sql select"],
        content_regex=[r"(?is)select.+from.+orders"],
        preferred_commands=["qdo sql select"],
        gotcha="CA.1 — qdo sql group doesn't surface -c; discoverability test.",
    ),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    args = _parse_args()
    _preflight(args)

    tasks = _select_tasks(args.tasks)
    models = _select_models(args.models)

    _preflight_cost(len(tasks), models, args.budget, args.confirm_spend)

    skill_content = _concat_skill_files()
    system_prompt = SYSTEM_PROMPT_TMPL.format(skill_files_content=skill_content)

    results: list[dict[str, Any]] = []
    for task in tasks:
        _run_pre_task(task)
        for model in models:
            print(f"\n=== {task.id} [{model}] ===")
            result = run_task(task, model, system_prompt, args)
            _print_task_result(result)
            results.append(result)
            # Auth failures repeat for every task; stop early so the operator
            # can fix it without burning through the whole suite first.
            if result.get("failure_category") == "auth-error":
                print(
                    "\nerror: `claude -p` is not authenticated. "
                    "Run `claude /login` and re-run this eval."
                )
                break
        else:
            continue
        break

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"results_{stamp}.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    _print_summary(results, out_path)

    # Exit non-zero only if every model below its target gate failed — this
    # is the signal used by future CI runs. Per-model gates come from EV.3:
    # haiku >=70%, sonnet >=85%, opus >=95%.
    return _exit_code(results)


# ---------------------------------------------------------------------------
# Argument parsing, preflight, selection
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Self-hosting eval for qdo skill files.")
    p.add_argument(
        "--models",
        default="haiku",
        help=(
            "Comma-separated model aliases to run (haiku,sonnet,opus). "
            "Use 'all' for every model. Default: haiku."
        ),
    )
    p.add_argument(
        "--tasks",
        default=None,
        help=(
            "Comma-separated task IDs to run (e.g. A1_list_tables,B1_enumerate_enum). "
            "Default: all tasks."
        ),
    )
    p.add_argument(
        "--budget",
        type=float,
        default=5.00,
        help=(
            "Max projected dollar spend across the run. Preflight aborts if exceeded. Default: $5."
        ),
    )
    p.add_argument(
        "--confirm-spend",
        action="store_true",
        help="Skip the interactive 'OK to spend $X?' prompt.",
    )
    p.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep per-task scratch dirs and raw stream-json logs for inspection.",
    )
    return p.parse_args()


def _preflight(args: argparse.Namespace) -> None:
    if not shutil.which("claude"):
        sys.exit(
            "error: 'claude' CLI not on PATH. Install Claude Code "
            "(https://claude.com/claude-code) and ensure `claude -p` works."
        )
    if os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "error: ANTHROPIC_API_KEY is set. Unset it before running this eval "
            "('unset ANTHROPIC_API_KEY') — otherwise `claude -p` will silently "
            "bill the API instead of using your Claude Code Max subscription."
        )
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


def _select_tasks(spec: str | None) -> list[Task]:
    if spec is None:
        return TASKS
    wanted = {s.strip() for s in spec.split(",") if s.strip()}
    selected = [t for t in TASKS if t.id in wanted]
    missing = wanted - {t.id for t in selected}
    if missing:
        sys.exit(f"error: unknown task ids: {sorted(missing)}. Known: {[t.id for t in TASKS]}")
    return selected


def _select_models(spec: str) -> list[str]:
    if spec.strip().lower() == "all":
        return list(MODEL_ALIASES)
    wanted = [s.strip() for s in spec.split(",") if s.strip()]
    for m in wanted:
        if m not in MODEL_ALIASES:
            sys.exit(f"error: unknown model alias: {m}. Known: {MODEL_ALIASES}")
    return wanted


def _preflight_cost(n_tasks: int, models: list[str], budget: float, confirm: bool) -> None:
    """Estimate and show projected spend; abort or prompt if over budget."""
    tokens_in = ESTIMATED_TOKENS_PER_TASK["prompt"]
    tokens_out = ESTIMATED_TOKENS_PER_TASK["output"]

    est_total = 0.0
    rows: list[tuple[str, float]] = []
    for m in models:
        in_price, out_price = PRICING_USD_PER_MTOK[m]
        per_task = (tokens_in * in_price + tokens_out * out_price) / 1_000_000
        cost = per_task * n_tasks
        rows.append((m, cost))
        est_total += cost

    print("\n=== Cost Estimation ===")
    print(f"{n_tasks} tasks x {len(models)} model(s) = {n_tasks * len(models)} run(s)")
    print(f"Estimated per-task tokens: {tokens_in} prompt + {tokens_out} output")
    for m, cost in rows:
        print(f"  {m}: ~${cost:.2f}")
    print(f"Total projected: ~${est_total:.2f}")
    print(f"Budget: ${budget:.2f}")

    if est_total > budget:
        sys.exit(
            f"error: projected spend ${est_total:.2f} > budget ${budget:.2f}. "
            "Raise --budget or narrow the task/model set."
        )

    if not confirm:
        try:
            reply = input("OK to proceed? (y/N) ").strip().lower()
        except EOFError:
            reply = ""
        if reply != "y":
            sys.exit("aborted by user.")


def _concat_skill_files() -> str:
    parts: list[str] = []
    for p in SKILL_FILES:
        rel = p.relative_to(REPO)
        parts.append(f"# {rel}\n\n{p.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(parts)


def _run_pre_task(task: Task) -> None:
    """Run a task's pre_task setup commands (e.g. metadata init) before the model gets it."""
    for argv in task.pre_task:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=QDO_TIMEOUT_SEC)
        if proc.returncode != 0:
            sys.exit(
                f"error: pre-task setup failed for {task.id}: "
                f"{' '.join(argv)} exited {proc.returncode}\n{proc.stderr}"
            )


# ---------------------------------------------------------------------------
# Per-task runner
# ---------------------------------------------------------------------------


def run_task(
    task: Task,
    model: str,
    system_prompt: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Run one (task, model) pair and return a structured result."""
    t_start = time.monotonic()

    scratch = Path(tempfile.mkdtemp(prefix=f"qdo-eval-{task.id}-{model}-"))
    if not args.keep_artifacts:
        atexit.register(lambda p=scratch: shutil.rmtree(p, ignore_errors=True))

    # Fixture path is absolute so the agent doesn't need to guess CWD.
    prompt = task.prompt.format(db=str(FIXTURE_DB))
    print(f"  scratch: {scratch}")
    print(f"  prompt: {prompt}")

    claude_argv = [
        "claude",
        "-p",
        prompt,
        "--model",
        model,
        "--append-system-prompt",
        system_prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "bypassPermissions",
        "--tools",
        "Bash",
        "--add-dir",
        str(REPO),
        "--bare",
        "--no-session-persistence",
        "--max-budget-usd",
        str(args.budget),
    ]

    try:
        proc = subprocess.run(
            claude_argv,
            cwd=scratch,
            capture_output=True,
            text=True,
            timeout=TASK_TIMEOUT_SEC,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "task_id": task.id,
            "category": task.category,
            "model": model,
            "status": "fail",
            "failure_category": "timeout",
            "reason": f"claude -p timed out after {TASK_TIMEOUT_SEC}s",
            "duration_sec": round(time.monotonic() - t_start, 2),
            "scratch": str(scratch) if args.keep_artifacts else None,
        }

    # Persist the raw stream for later inspection.
    (scratch / "stream.jsonl").write_text(proc.stdout, encoding="utf-8")
    if proc.stderr:
        (scratch / "stderr.txt").write_text(proc.stderr, encoding="utf-8")

    qdo_commands, tool_errors, final_text, usage = parse_stream_json(proc.stdout)

    if final_text:
        (scratch / "final.txt").write_text(final_text, encoding="utf-8")

    # Auth failures look like "no commands run + terse 'not logged in' text".
    # Detecting them explicitly saves an operator from seeing 11 model-mistake
    # fails in a row and wondering what happened.
    if _is_auth_error(final_text, proc.stderr):
        return {
            "task_id": task.id,
            "category": task.category,
            "model": model,
            "prompt": prompt,
            "status": "fail",
            "failure_category": "auth-error",
            "reason": "claude -p isn't authenticated — run `claude /login` first",
            "path_ok": False,
            "qdo_commands": [],
            "tool_errors": [],
            "final_text_snippet": (final_text or proc.stderr or "")[:500],
            "usage": usage,
            "duration_sec": round(time.monotonic() - t_start, 2),
            "scratch": str(scratch) if args.keep_artifacts else None,
            "gotcha": task.gotcha,
        }

    check = check_pass(task, qdo_commands, tool_errors, final_text)
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


# ---------------------------------------------------------------------------
# Stream-json parser
# ---------------------------------------------------------------------------


def parse_stream_json(text: str) -> tuple[list[str], list[str], str, dict[str, Any]]:
    """Parse ``claude -p --output-format stream-json`` output.

    Returns ``(qdo_commands, tool_errors, final_text, usage)``.

    ``qdo_commands`` — every Bash tool call whose command starts with
    ``qdo`` (or whitespace-then-``qdo``; occasionally models wrap in
    subshells). Each entry is the raw command string.

    ``tool_errors`` — Bash tool results flagged ``is_error: true`` or
    carrying a non-zero exit signal in their text content. Used by the
    checker to distinguish ``qdo-bug`` from ``model-mistake``.

    ``final_text`` — the assistant's final answer (``result`` event).

    ``usage`` — usage + cost metadata from the ``result`` event.
    """
    qdo_commands: list[str] = []
    tool_errors: list[str] = []
    final_text = ""
    usage: dict[str, Any] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")
        if etype == "assistant":
            msg = event.get("message") or {}
            for block in msg.get("content") or []:
                if block.get("type") == "tool_use" and block.get("name") == "Bash":
                    cmd = (block.get("input") or {}).get("command") or ""
                    cmd = cmd.strip()
                    if _looks_like_qdo(cmd):
                        qdo_commands.append(cmd)
        elif etype == "user":
            msg = event.get("message") or {}
            for block in msg.get("content") or []:
                if block.get("type") != "tool_result":
                    continue
                if block.get("is_error"):
                    snippet = _extract_text(block.get("content"))
                    tool_errors.append(snippet[:500])
                    continue
                # Even without is_error, some tools embed "exit code 1" in text.
                snippet = _extract_text(block.get("content"))
                if re.search(r"exit\s*code\s*[1-9]", snippet, re.IGNORECASE):
                    tool_errors.append(snippet[:500])
        elif etype == "result":
            final_text = event.get("result") or ""
            if "usage" in event:
                usage["tokens"] = event["usage"]
            for k in ("cost_usd", "total_cost_usd", "duration_ms", "num_turns"):
                if k in event:
                    usage[k] = event[k]

    return qdo_commands, tool_errors, final_text, usage


def _looks_like_qdo(cmd: str) -> bool:
    """True if *cmd* is a qdo invocation (including env-prefixed)."""
    if not cmd:
        return False
    # Strip common prefixes: env var setters, uv wrappers.
    stripped = re.sub(r"^(?:[A-Z_][A-Z0-9_]*=\S+\s+)+", "", cmd)
    stripped = re.sub(r"^uv\s+run\s+", "", stripped)
    return stripped.startswith("qdo ") or stripped == "qdo"


def _extract_text(content: Any) -> str:
    """Flatten a tool_result content field (str or list of text blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text") or "")
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts)
    return ""


# ---------------------------------------------------------------------------
# Pass/fail checker
# ---------------------------------------------------------------------------


def check_pass(
    task: Task, qdo_commands: list[str], tool_errors: list[str], final_text: str
) -> dict[str, Any]:
    """Return ``status``, ``failure_category``, ``reason``, ``path_ok``."""

    # Treat any tool_use that crashed as a qdo-bug signal first — a failing
    # qdo command shouldn't be counted against the model.
    if tool_errors:
        return {
            "status": "fail",
            "failure_category": "qdo-bug",
            "reason": f"{len(tool_errors)} qdo subprocess(es) exited with error",
            "path_ok": False,
        }

    # Required-command check.
    required_hit = _any_prefix_match(task.required_commands, qdo_commands)
    if not required_hit:
        expected = ", ".join(task.required_commands)
        actual = ", ".join(_cmd_prefix(c, 3) for c in qdo_commands) or "(none)"
        return {
            "status": "fail",
            "failure_category": "model-mistake",
            "reason": f"no required command used (expected any of: {expected}; got: {actual})",
            "path_ok": False,
        }

    # Content check against the final answer.
    content_hit = any(re.search(pat, final_text) for pat in task.content_regex)
    if not content_hit:
        return {
            "status": "fail",
            "failure_category": "envelope-mismatch",
            "reason": (
                "final answer didn't match any content regex "
                f"({task.content_regex}); command path was fine"
            ),
            "path_ok": _any_prefix_match(task.preferred_commands, qdo_commands)
            if task.preferred_commands
            else True,
        }

    # Sanity: too many commands suggests the model wandered.
    if len(qdo_commands) > task.max_commands:
        return {
            "status": "fail",
            "failure_category": "model-mistake",
            "reason": f"used {len(qdo_commands)} commands (limit {task.max_commands})",
            "path_ok": False,
        }

    path_ok = (
        _any_prefix_match(task.preferred_commands, qdo_commands)
        if task.preferred_commands
        else True
    )
    return {
        "status": "pass",
        "failure_category": None,
        "reason": f"required+content+<= {task.max_commands} commands",
        "path_ok": path_ok,
    }


_AUTH_ERROR_RE = re.compile(
    r"not\s*logged\s*in|please\s*run\s*/?login|unauthorized", re.IGNORECASE
)


def _is_auth_error(final_text: str, stderr: str) -> bool:
    """Detect the claude-not-authenticated case so operators don't see a
    wall of spurious model-mistake failures."""
    haystack = f"{final_text or ''}\n{stderr or ''}"
    return bool(_AUTH_ERROR_RE.search(haystack))


def _any_prefix_match(prefixes: list[str], cmds: list[str]) -> bool:
    """True when any *cmds* entry starts with any prefix (env/uv wrappers allowed)."""
    for cmd in cmds:
        stripped = re.sub(r"^(?:[A-Z_][A-Z0-9_]*=\S+\s+)+", "", cmd)
        stripped = re.sub(r"^uv\s+run\s+", "", stripped)
        for pfx in prefixes:
            if stripped.startswith(pfx):
                return True
    return False


def _cmd_prefix(cmd: str, words: int) -> str:
    """First N whitespace-delimited tokens of *cmd*."""
    return " ".join(cmd.split()[:words])


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_task_result(r: dict[str, Any]) -> None:
    status = r["status"]
    marker = "✓" if status == "pass" else "✗"
    path = "" if r.get("path_ok", True) else " (path not preferred)"
    print(f"  [{marker} {status}]{path} {r['reason']}")
    if status != "pass":
        cat = r.get("failure_category") or "?"
        print(f"    category: {cat}")


def _print_summary(results: list[dict[str, Any]], out_path: Path) -> None:
    print("\n=== Summary ===")
    by_model: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_model.setdefault(r["model"], []).append(r)

    gates = {"haiku": 0.70, "sonnet": 0.85, "opus": 0.95}
    for model, rows in by_model.items():
        passed = sum(1 for r in rows if r["status"] == "pass")
        total = len(rows)
        pct = passed / total if total else 0.0
        gate = gates.get(model, 0.0)
        marker = "✓" if pct >= gate else "✗"
        print(f"  {marker} {model}: {passed}/{total} ({pct:.0%}) — target {gate:.0%}")

    # Group failures by category for visibility.
    cats: dict[str, int] = {}
    for r in results:
        if r["status"] != "pass":
            cats[r.get("failure_category") or "unknown"] = (
                cats.get(r.get("failure_category") or "unknown", 0) + 1
            )
    if cats:
        print("\n  Failure breakdown:")
        for cat, n in sorted(cats.items(), key=lambda kv: -kv[1]):
            print(f"    {cat}: {n}")

    print(f"\nPer-task JSON log: {out_path}")


def _exit_code(results: list[dict[str, Any]]) -> int:
    """Exit 0 when every model meets its target pass-rate gate."""
    by_model: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_model.setdefault(r["model"], []).append(r)
    gates = {"haiku": 0.70, "sonnet": 0.85, "opus": 0.95}
    for model, rows in by_model.items():
        passed = sum(1 for r in rows if r["status"] == "pass")
        total = len(rows) or 1
        if passed / total < gates.get(model, 0.0):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
