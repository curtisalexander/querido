"""Measure token counts for -f json vs -f agent across representative commands.

Uses the existing test SQLite database (``data/test.db``). Prints a table
with byte counts, tiktoken counts (cl100k_base, used by GPT-4/4o — a
reasonable stand-in since Anthropic's tokenizer isn't publicly distributed),
and the agent-vs-json delta per command.

Usage:
    uv run python scripts/benchmark_agent_format.py
    uv run python scripts/benchmark_agent_format.py --db /path/to/other.db
    uv run python scripts/benchmark_agent_format.py --no-tokens   # bytes only
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "test.db"

# Each entry: (label, argv without -f and -c).
# Picked to span shapes: tabular rows, tabular + nested (context), catalog
# (deeply nested → YAML fallback), values (tabular), query, quality, diff,
# profile, inspect.
COMMANDS: list[tuple[str, list[str]]] = [
    ("preview customers", ["preview", "-t", "customers", "--rows", "25"]),
    ("preview customers (rows=100)", ["preview", "-t", "customers", "--rows", "100"]),
    ("catalog", ["catalog"]),
    ("values customers.country", ["values", "-t", "customers", "-C", "country"]),
    ("inspect customers", ["inspect", "-t", "customers"]),
    ("context customers", ["context", "-t", "customers"]),
    ("profile customers (quick)", ["profile", "-t", "customers", "--quick"]),
    ("query select *", ["query", "--sql", "select * from customers limit 50"]),
    ("quality customers", ["quality", "-t", "customers"]),
]


def _run(db: Path, fmt: str, argv: list[str]) -> str:
    cmd = ["qdo", "-f", fmt, *argv, "-c", str(db)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"qdo failed (exit={proc.returncode}): {' '.join(cmd)}\n{proc.stderr}")
    return proc.stdout


def _token_counter(disable: bool):
    if disable:
        return None
    try:
        import tiktoken  # ty: ignore[unresolved-import]
    except ImportError:
        print(
            "note: tiktoken not installed, showing bytes only. "
            "Install with: uv pip install tiktoken",
            file=sys.stderr,
        )
        return None
    enc = tiktoken.get_encoding("cl100k_base")
    return lambda s: len(enc.encode(s))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--no-tokens", action="store_true")
    args = p.parse_args()

    if not args.db.exists():
        print(f"error: db not found: {args.db}", file=sys.stderr)
        return 2

    count_tokens = _token_counter(args.no_tokens)

    if count_tokens is None:
        fmt = "{:<40} {:>10} {:>10} {:>8}"
        print(fmt.format("command", "json B", "agent B", "Δ%"))
        print("-" * 70)
    else:
        fmt = "{:<40} {:>10} {:>10} {:>8} {:>12} {:>12} {:>8}"
        print(fmt.format("command", "json B", "agent B", "ΔB%", "json tok", "agent tok", "Δtok%"))
        print("-" * 102)

    for label, argv in COMMANDS:
        try:
            json_out = _run(args.db, "json", argv)
            agent_out = _run(args.db, "agent", argv)
        except RuntimeError as e:
            print(f"{label}: {e}", file=sys.stderr)
            continue

        jb, ab = len(json_out), len(agent_out)
        byte_delta = (ab - jb) / jb * 100 if jb else 0.0

        if count_tokens is None:
            print(fmt.format(label, jb, ab, f"{byte_delta:+.1f}"))
        else:
            jt, at = count_tokens(json_out), count_tokens(agent_out)
            tok_delta = (at - jt) / jt * 100 if jt else 0.0
            print(
                fmt.format(
                    label,
                    jb,
                    ab,
                    f"{byte_delta:+.1f}",
                    jt,
                    at,
                    f"{tok_delta:+.1f}",
                )
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
