"""Self-hosting eval for qdo skill files — EV.Build from PLAN.md.

Feeds ``SKILL.md`` + ``WORKFLOW_EXAMPLES.md`` + ``AGENTS.md`` as context to
``claude -p`` and asks the model to answer realistic data-exploration
questions using only the qdo CLI against ``data/test.duckdb``. The task set
leans on qdo's promoted workflow:

``catalog -> context -> metadata -> query/assert -> report/bundle``

Each task has:

- A natural-language prompt (the model must pick qdo commands itself)
- A set of required ``qdo <subcommand>`` prefixes (at least one must be used)
- A content regex (must match somewhere in the model's final answer)
- A set of preferred commands (logged as ``path_ok`` — bonus, not a gate)

Failures are categorized so a docs gap can be told apart from a qdo bug
(see PLAN.md → "Eval-design proposal findings (EV.x)" → EV.4).

Usage::

    unset ANTHROPIC_API_KEY            # avoid silent API billing
    uv run python scripts/eval_skill_files_claude.py                       # haiku only
    uv run python scripts/eval_skill_files_claude.py --models all          # haiku+sonnet+opus
    uv run python scripts/eval_skill_files_claude.py --tasks A1_list_tables,B1_enumerate_enum
    uv run python scripts/eval_skill_files_claude.py --budget 5.00

Local-only by default. Requires Claude Code Max (``claude -p`` uses the
subscription, not ANTHROPIC_API_KEY). Refuses to run if the API key is set
so billing can't go silently through.

CI note: deliberately not wired into GitHub Actions. If you want to
automate, use ``workflow_dispatch``-only with explicit budget gates.
"""

from __future__ import annotations

import argparse
import atexit
import io
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

# Per-run default budgets. Tunable via CLI flags - see `_parse_args`.
# Historical: a full 45-task run completes in 5-10 min on a warm cache.
# An outlier run (Anthropic API backpressure) took ~53 min; we cap the
# whole run at 20 min by default so a degraded API can't silently burn
# an hour before an operator notices.
DEFAULT_TASK_TIMEOUT_SEC = 240  # one claude -p invocation
DEFAULT_QDO_TIMEOUT_SEC = 30  # one qdo subprocess inside a task
DEFAULT_WALL_CLOCK_SEC = 20 * 60  # entire eval run across all (task, model) pairs

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
- Follow qdo's opinionated workflow when it fits the task:
  ``catalog -> context -> metadata -> query/assert -> report/bundle``.
- Prefer `qdo context` over stitching together multiple lower-level
  commands when the goal is to understand one table.
- Use qdo commands — do not install extra tools.
- Use `qdo query` only when the task requires answering a concrete
  question that the higher-level commands do not already answer.
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

    ``required_any_of`` is a list of qdo subcommand prefixes (e.g.
    ``"qdo joins"``); **at least one** must appear in the model's Bash
    tool-call stream for the task to pass the gate. Listing multiple
    prefixes here is the "any of these paths is acceptable" primitive —
    e.g. ``["qdo profile", "qdo query"]`` accepts either a profile scan
    or an ad-hoc SQL answer. `preferred_commands` still captures the
    "clean path" signal when the first path is materially better.

    ``required_all_of`` is stricter: **every** listed prefix must appear
    in the tool-call stream. This rewards the promoted multi-step
    workflow when a single-command path wouldn't satisfy the prompt.

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
    required_any_of: list[str]
    content_regex: list[str]
    preferred_commands: list[str] = field(default_factory=list)
    required_all_of: list[str] = field(default_factory=list)
    max_commands: int = 12
    pre_task: list[list[str]] = field(default_factory=list)
    # Short note on the Wave 1 gotcha this task exercises (for the report).
    gotcha: str = ""


TASKS: list[Task] = [
    # ---- Category A: Discovery and first-pass understanding ----
    Task(
        id="A1_list_tables",
        category="A",
        prompt=(
            "I have a new DuckDB database at {db}. Show me every table in it "
            "and its row count. One-sentence summary is fine."
        ),
        required_any_of=["qdo catalog"],
        content_regex=[r"(?i)customers", r"(?i)products", r"(?i)orders"],
        preferred_commands=["qdo catalog"],
        gotcha="CS.1 — fixture must have orders for this to pass.",
    ),
    Task(
        id="A2_pick_table_then_context",
        category="A",
        prompt=(
            "I'm new to {db}. If my end goal is understanding customer orders, "
            "which table should I start with, and give me a concise summary of it."
        ),
        required_any_of=["qdo catalog", "qdo context"],
        required_all_of=["qdo catalog", "qdo context"],
        content_regex=[r"(?i)orders", r"(?i)(status|amount|region|order_date)"],
        preferred_commands=["qdo catalog", "qdo context"],
        gotcha="Rewards the promoted discover -> understand path instead of ad-hoc probing.",
    ),
    Task(
        id="A3_join_keys",
        category="A",
        prompt=(
            "In {db}, what are the likely join keys between the orders table "
            "and the other tables? Give me the column pairs."
        ),
        required_any_of=["qdo joins"],
        content_regex=[r"customer_id", r"product_id"],
        preferred_commands=["qdo joins"],
        gotcha="Secondary discovery skill — useful, but not the primary workflow anchor.",
    ),
    Task(
        id="A4_summarize_orders",
        category="A",
        prompt=(
            "In {db}, give me a full summary of the orders table and call out "
            "any obvious quality issues."
        ),
        required_any_of=["qdo context", "qdo quality"],
        required_all_of=["qdo context", "qdo quality"],
        content_regex=[r"(?i)(status|amount|null|negative|quality|issue)"],
        preferred_commands=["qdo context", "qdo quality"],
        gotcha="Ensures summary tasks lean on context first, then a quality pass.",
    ),
    # ---- Category B: Column-level exploration ----
    Task(
        id="B1_enumerate_enum",
        category="B",
        prompt=(
            "In {db}, what are the distinct values in the orders.status "
            "column? Include counts if available."
        ),
        # `values` is the promoted path; `dist -C status` is the categorical
        # distribution variant; `query --sql "select status, count(*) from
        # orders group by status"` is equally valid ad-hoc SQL. Grade the
        # answer on content, not on which of three good paths the model took.
        required_any_of=["qdo values", "qdo dist", "qdo query"],
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
        # `context` is the anchor; `profile` is the specialist. But a
        # `query --sql "select min(amount), max(amount), avg(amount),
        # count(*) - count(amount) ..."` also answers exactly what the
        # user asked. Accept all three; `preferred_commands` still
        # captures whether the model took the clean path.
        required_any_of=["qdo context", "qdo profile", "qdo query"],
        content_regex=[r"(?i)(min|max|mean|average)"],
        preferred_commands=["qdo context", "qdo profile"],
        gotcha=(
            "The promoted workflow should allow context to answer "
            "minimum numeric summaries cleanly."
        ),
    ),
    Task(
        id="B4_profile_deep_numeric",
        category="B",
        prompt=(
            "In {db}, give me a deeper numeric profile of orders.amount. "
            "Include at least the median and standard deviation, not just min/max."
        ),
        # `profile` is the promoted path (it computes quantiles and stddev
        # for free). But `query --sql "select approx_quantile(amount, 0.5),
        # stddev(amount) ..."` answers the prompt too. Accept both; keep
        # `profile` as the preferred signal.
        required_any_of=["qdo profile", "qdo query"],
        content_regex=[r"(?i)(median|stddev|standard deviation)"],
        preferred_commands=["qdo profile"],
        gotcha=(
            "This is the column-level case where profile should beat "
            "context because deeper stats are required."
        ),
    ),
    Task(
        id="B3_null_rates",
        category="B",
        prompt=(
            "In {db}, which columns in the customers table have the highest "
            "null rates? Name the top three."
        ),
        required_any_of=["qdo profile", "qdo quality", "qdo context"],
        content_regex=[r"(?i)(phone2|company|website)"],
        preferred_commands=["qdo context", "qdo quality"],
        gotcha="CS.10 — quality vs profile roles weren't disambiguated pre-Wave-1.",
    ),
    # ---- Category C: Answering and verification ----
    Task(
        id="C1_quality_issues",
        category="C",
        prompt=(
            "In {db}, are there any data-quality issues in the orders "
            "table? Flag anything unusual — null rates, malformed values, "
            "uniqueness problems."
        ),
        required_any_of=["qdo quality"],
        content_regex=[r"(?i)(status|amount|null|quality|issue)"],
        preferred_commands=["qdo quality"],
        gotcha="Fixture has ~0.8% bad status + 1.5% negative amount — quality should flag.",
    ),
    Task(
        id="C2_query_total_by_region",
        category="C",
        prompt=(
            "In {db}, what is the total order amount by region, and which "
            "region has the highest total?"
        ),
        required_any_of=["qdo context", "qdo query", "qdo catalog"],
        content_regex=[r"(?i)(north|south|east|west|region)"],
        preferred_commands=["qdo context", "qdo query"],
        gotcha=(
            "Simple aggregation questions may reasonably go straight to query "
            "after light orientation."
        ),
    ),
    Task(
        id="C3_assert_row_count",
        category="C",
        prompt=(
            "In {db}, assert that the orders table has at least 1000 rows. "
            "Tell me whether the assertion passed or failed."
        ),
        required_any_of=["qdo assert"],
        content_regex=[r"(?i)(pass|ok|true|5000|satisfied)"],
        preferred_commands=["qdo assert"],
        gotcha="CA.3 — assert was invisible to SKILL.md pre-Wave-2.",
    ),
    # ---- Category D: Metadata capture and hand-off artifacts ----
    Task(
        id="D1_stored_metadata",
        category="D",
        prompt=(
            "In {db}, show me the stored metadata for the orders table — "
            "the description, the owner, and the per-column details."
        ),
        required_any_of=["qdo metadata show"],
        content_regex=[r"(?i)(description|owner|columns|table)"],
        preferred_commands=["qdo metadata show"],
        pre_task=[
            ["qdo", "metadata", "init", "-c", str(FIXTURE_DB), "-t", "orders", "--force"],
        ],
        gotcha="CS.3 — metadata show envelope wired in Wave 1.",
    ),
    Task(
        id="D2_init_metadata",
        category="D",
        prompt=(
            "In {db}, initialize metadata for the orders table and tell me "
            "where the YAML file was written."
        ),
        required_any_of=["qdo metadata init"],
        content_regex=[r"(?i)(\.qdo/metadata|orders\.yaml|created)"],
        preferred_commands=["qdo metadata init"],
        gotcha="Tests the capture step directly instead of treating metadata as an afterthought.",
    ),
    Task(
        id="D3_table_report",
        category="D",
        prompt=(
            "In {db}, create a hand-off HTML report for the orders table at "
            "./orders-report.html and tell me what you created."
        ),
        required_any_of=["qdo report table"],
        content_regex=[r"(?i)(orders-report\.html|html report)"],
        preferred_commands=["qdo report table"],
        pre_task=[
            ["qdo", "metadata", "init", "-c", str(FIXTURE_DB), "-t", "orders", "--force"],
        ],
        gotcha="Validates the hand-off step of the promoted workflow.",
    ),
    Task(
        id="D4_bundle_export",
        category="D",
        prompt=(
            "In {db}, export a knowledge bundle for the orders table to "
            "./orders-bundle.zip, inspect it, and tell me what it contains."
        ),
        required_any_of=["qdo bundle export", "qdo bundle inspect"],
        required_all_of=["qdo bundle export", "qdo bundle inspect"],
        content_regex=[r"(?i)(orders-bundle\.zip|bundle|orders)"],
        preferred_commands=["qdo bundle export", "qdo bundle inspect"],
        pre_task=[
            ["qdo", "metadata", "init", "-c", str(FIXTURE_DB), "-t", "orders", "--force"],
        ],
        gotcha="Tests the portable hand-off artifact, not just local exploration.",
    ),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    args = _parse_args()
    _preflight(args)

    # Force line buffering so tail -f and background-task log readers see
    # per-task progress mid-run instead of one dump at the end.
    import contextlib

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        with contextlib.suppress(AttributeError, io.UnsupportedOperation):
            reconfigure(line_buffering=True)

    tasks = _select_tasks(args.tasks)
    models = _select_models(args.models)

    _preflight_cost(len(tasks), models, args.budget, args.confirm_spend)

    skill_content = _concat_skill_files()
    system_prompt = SYSTEM_PROMPT_TMPL.format(skill_files_content=skill_content)

    total_pairs = len(tasks) * len(models)
    print(
        f"\n=== Run plan === {total_pairs} (task, model) pairs, "
        f"per-task timeout {args.task_timeout_sec}s, wall-clock cap "
        f"{args.max_wall_clock_minutes:.0f} min."
    )
    run_start = time.monotonic()
    budget_exceeded = False

    results: list[dict[str, Any]] = []
    for task in tasks:
        for model in models:
            elapsed_min = (time.monotonic() - run_start) / 60
            if elapsed_min >= args.max_wall_clock_minutes:
                print(
                    f"\nwall-clock budget exceeded "
                    f"({elapsed_min:.1f} / {args.max_wall_clock_minutes:.0f} min) — "
                    "stopping before launching more tasks."
                )
                budget_exceeded = True
                break
            print(
                f"\n=== {task.id} [{model}] "
                f"(elapsed {elapsed_min:.1f} min, pair "
                f"{len(results) + 1}/{total_pairs}) ==="
            )
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

    if budget_exceeded:
        # Explicit non-zero signal so CI or background runners don't swallow it.
        return 2

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
    p.add_argument(
        "--task-timeout-sec",
        type=int,
        default=DEFAULT_TASK_TIMEOUT_SEC,
        help=(
            "Max seconds for a single `claude -p` invocation. "
            f"Default: {DEFAULT_TASK_TIMEOUT_SEC}s."
        ),
    )
    p.add_argument(
        "--qdo-timeout-sec",
        type=int,
        default=DEFAULT_QDO_TIMEOUT_SEC,
        help=(
            "Max seconds for a single qdo subprocess invoked during pre-task setup. "
            f"Default: {DEFAULT_QDO_TIMEOUT_SEC}s."
        ),
    )
    p.add_argument(
        "--max-wall-clock-minutes",
        type=float,
        default=DEFAULT_WALL_CLOCK_SEC / 60,
        help=(
            "Max total wall-clock minutes across the whole run. If exceeded, the "
            "harness stops launching new tasks, writes partial results, and exits "
            "non-zero. Prevents a degraded Anthropic API from burning hours "
            f"silently. Default: {DEFAULT_WALL_CLOCK_SEC / 60:.0f} minutes."
        ),
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


def _run_pre_task(
    task: Task, *, cwd: Path | None = None, qdo_timeout_sec: int = DEFAULT_QDO_TIMEOUT_SEC
) -> None:
    """Run a task's pre_task setup commands (e.g. metadata init) before the model gets it.

    *cwd* should match the directory ``claude -p`` will run from, so any files
    qdo writes during setup (e.g. ``.qdo/metadata/<conn>/<table>.yaml``) are
    visible to the agent's own qdo calls.
    """
    for argv in task.pre_task:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=qdo_timeout_sec,
        )
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

    # Pre-task runs here (not in main) so its cwd matches claude -p's cwd.
    # Stuff qdo writes — e.g. metadata YAML in ``.qdo/metadata/`` — lands in
    # scratch, where the model's qdo subprocess will find it.
    _run_pre_task(task, cwd=scratch, qdo_timeout_sec=args.qdo_timeout_sec)

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
        "--no-session-persistence",
        "--max-budget-usd",
        str(args.budget),
    ]

    # Pin metadata root into the scratch dir so tasks can't observe or
    # mutate state from prior eval runs — even when the model `cd`s into
    # the repo before invoking qdo (haiku does this). Without this,
    # D2_init_metadata spuriously fails because .qdo/metadata/test/ from
    # an earlier dev session already lives in the repo.
    child_env = {
        **os.environ,
        "QDO_METADATA_DIR": str(scratch / ".qdo" / "metadata"),
    }

    try:
        proc = subprocess.run(
            claude_argv,
            cwd=scratch,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=args.task_timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "task_id": task.id,
            "category": task.category,
            "model": model,
            "status": "fail",
            "failure_category": "timeout",
            "reason": f"claude -p timed out after {args.task_timeout_sec}s",
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

    # Track tool_use_id -> command so we can distinguish tool errors from qdo
    # invocations (which are qdo-bugs if non-trivial) vs tool errors from other
    # shell commands the model ran (like `unzip` or `python -c`) that failing
    # should not count against qdo's score.
    tool_use_commands: dict[str, str] = {}

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
                    use_id = block.get("id") or ""
                    cmd = (block.get("input") or {}).get("command") or ""
                    cmd = cmd.strip()
                    if use_id:
                        tool_use_commands[use_id] = cmd
                    if _looks_like_qdo(cmd):
                        qdo_commands.append(cmd)
        elif etype == "user":
            msg = event.get("message") or {}
            for block in msg.get("content") or []:
                if block.get("type") != "tool_result":
                    continue
                # Only count errors from qdo invocations as qdo tool_errors.
                # Failures in other shell commands the model ran (unzip,
                # python -c, etc.) are not qdo's responsibility.
                source_cmd = tool_use_commands.get(block.get("tool_use_id") or "", "")
                if not _looks_like_qdo(source_cmd):
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


def _strip_shell_prefix(cmd: str) -> str:
    """Strip shell prefixes agents commonly wrap ``qdo`` in so downstream
    detection can treat the command as a plain ``qdo ...`` invocation.

    Handles (repeatedly, until stable):
    - env-var setters: ``FOO=bar BAZ=qux qdo ...``
    - ``uv run qdo ...``
    - ``cd <path> && qdo ...`` / ``cd <path> ; qdo ...``

    Haiku in particular likes ``cd <repo> && qdo ...`` even though the eval
    already sets ``cwd`` to a scratch dir and qdo takes an absolute path for
    ``-c``. We accept the noise rather than fight it.
    """
    prev = None
    stripped = cmd
    while stripped != prev:
        prev = stripped
        stripped = re.sub(r"^(?:[A-Z_][A-Z0-9_]*=\S+\s+)+", "", stripped)
        stripped = re.sub(r"^uv\s+run\s+", "", stripped)
        stripped = re.sub(r"^cd\s+\S+\s*(?:&&|;)\s*", "", stripped)
        stripped = re.sub(r"^export\s+[A-Z_][A-Z0-9_]*=\S+\s*(?:&&|;)\s*", "", stripped)
    return stripped


def _looks_like_qdo(cmd: str) -> bool:
    """True if *cmd* is a qdo invocation (including wrapped in common shell prefixes)."""
    if not cmd:
        return False
    stripped = _strip_shell_prefix(cmd)
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

    # Tool errors split into two kinds:
    #  - Click usage errors ("No such option", "Missing option", etc.) mean
    #    the model called qdo with wrong argv — that's a model-mistake.
    #  - Anything else (tracebacks, runtime errors) is a real qdo-bug.
    if tool_errors:
        usage_errs = [e for e in tool_errors if _is_click_usage_error(e)]
        if len(usage_errs) == len(tool_errors):
            return {
                "status": "fail",
                "failure_category": "model-mistake",
                "reason": f"{len(tool_errors)} qdo invocation(s) had bad argv (click usage error)",
                "path_ok": False,
            }
        lock_errs = [e for e in tool_errors if _is_database_lock_error(e)]
        if lock_errs:
            return {
                "status": "fail",
                "failure_category": "database-lock",
                "reason": f"{len(lock_errs)} qdo invocation(s) hit a database lock",
                "path_ok": False,
            }
        return {
            "status": "fail",
            "failure_category": "qdo-bug",
            "reason": f"{len(tool_errors)} qdo subprocess(es) exited with error",
            "path_ok": False,
        }

    # Required-command check.
    required_hit = _any_prefix_match(task.required_any_of, qdo_commands)
    if not required_hit:
        expected = ", ".join(task.required_any_of)
        actual = ", ".join(_cmd_prefix(c, 3) for c in qdo_commands) or "(none)"
        return {
            "status": "fail",
            "failure_category": "model-mistake",
            "reason": f"no required command used (expected any of: {expected}; got: {actual})",
            "path_ok": False,
        }

    if task.required_all_of:
        missing = [
            prefix
            for prefix in task.required_all_of
            if not _any_prefix_match([prefix], qdo_commands)
        ]
        if missing:
            return {
                "status": "fail",
                "failure_category": "model-mistake",
                "reason": f"missing required workflow step(s): {', '.join(missing)}",
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

# Click usage errors have a two-line shape: a `Usage: ...` preamble plus an
# `Error: <phrase>` line naming one of a closed set of argv-shape problems.
# These are model-mistakes (wrong flag, missing required option, extra
# positional, bad choice value), not qdo bugs — the eval categorizes them
# separately and leaves qdo-bug for real runtime failures / tracebacks.
_USAGE_PREAMBLE_RE = re.compile(r"^\s*Usage:\s", re.MULTILINE)
_USAGE_ERROR_PHRASE_RE = re.compile(
    r"Error:\s(?:"
    r"No\s+such\s+option"
    r"|Missing\s+option"
    r"|Missing\s+argument"
    r"|Got\s+unexpected\s+extra"
    r"|Invalid\s+value\s+for"
    r"|No\s+such\s+command"
    r"|Did\s+you\s+mean"
    r")",
    re.IGNORECASE,
)


def _is_click_usage_error(text: str) -> bool:
    """True when *text* (a tool-error snippet) looks like a click usage error.

    Requires both the ``Usage:`` preamble **and** an ``Error: <usage phrase>``
    line — a traceback that mentions ``Usage:`` in source code wouldn't match
    because it lacks the error-phrase tail.
    """
    if not text:
        return False
    return bool(_USAGE_PREAMBLE_RE.search(text)) and bool(_USAGE_ERROR_PHRASE_RE.search(text))


def _is_database_lock_error(text: str) -> bool:
    if not text:
        return False
    return "Could not set lock on file" in text or "DATABASE_LOCKED" in text


def _is_auth_error(final_text: str, stderr: str) -> bool:
    """Detect the claude-not-authenticated case so operators don't see a
    wall of spurious model-mistake failures."""
    haystack = f"{final_text or ''}\n{stderr or ''}"
    return bool(_AUTH_ERROR_RE.search(haystack))


def _normalize_for_prefix(cmd: str) -> str:
    """Return *cmd* shell-stripped and with ``-f``/``--format`` pairs removed.

    Strips shell wrappers (``cd X && ...``, env-var setters, ``uv run ...``)
    and the format flag so the result starts with ``qdo <subcommand> ...``,
    which is what :func:`_any_prefix_match` compares against.

    Without this, ``cd /repo && qdo -f json catalog ...`` wouldn't match the
    prefix ``qdo catalog`` because ``-f json`` sits between ``qdo`` and the
    subcommand. The qdo CLI itself hoists ``-f`` on invocation, but that
    doesn't help the eval's string-level inspection of the Bash tool call.
    """
    stripped = _strip_shell_prefix(cmd)
    stripped = re.sub(r"\s+--format=\S*", " ", stripped)
    stripped = re.sub(r"\s+(?:-f|--format)(?:\s+\S+)?", " ", stripped)
    return re.sub(r"\s+", " ", stripped).strip()


def _any_prefix_match(prefixes: list[str], cmds: list[str]) -> bool:
    """True when any *cmds* entry starts with any prefix (after normalization)."""
    for cmd in cmds:
        normalized = _normalize_for_prefix(cmd)
        for pfx in prefixes:
            if normalized.startswith(pfx):
                return True
    return False


def _cmd_prefix(cmd: str, words: int) -> str:
    """First N whitespace-delimited tokens of *cmd* (after normalization, so
    error messages show ``qdo catalog`` rather than ``cd /repo &&``)."""
    return " ".join(_normalize_for_prefix(cmd).split()[:words])


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
