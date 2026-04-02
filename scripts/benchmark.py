"""Performance benchmarks for qdo operations.

Generates a large DuckDB database and times key CLI operations to verify
that sampling and other optimizations work correctly.

Usage:
    uv run python scripts/benchmark.py
    uv run python scripts/benchmark.py --rows 10000000
    uv run python scripts/benchmark.py --operations preview,profile
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ALL_OPERATIONS = [
    "preview",
    "inspect",
    "profile",
    "profile --sample 100000",
    "dist (numeric)",
    "dist (categorical)",
    "dist --sample 100000",
]


def generate_db(path: str, rows: int) -> None:
    """Generate a DuckDB database with a large mixed-type table."""
    import duckdb

    conn = duckdb.connect(path)
    conn.execute(f"""
        create table benchmark as
        select
            i as id,
            (random() * 1000000)::double as amount,
            (random() * 100)::integer as quantity,
            case (i % 20)
                when 0 then 'Electronics'
                when 1 then 'Clothing'
                when 2 then 'Food'
                when 3 then 'Books'
                when 4 then 'Toys'
                when 5 then 'Sports'
                when 6 then 'Home'
                when 7 then 'Garden'
                when 8 then 'Auto'
                when 9 then 'Health'
                when 10 then 'Beauty'
                when 11 then 'Music'
                when 12 then 'Movies'
                when 13 then 'Games'
                when 14 then 'Tools'
                when 15 then 'Office'
                when 16 then 'Pet'
                when 17 then 'Baby'
                when 18 then 'Grocery'
                else 'Other'
            end as category,
            current_date - (random() * 3650)::integer as created_date,
            case when random() > 0.05 then 'active' else null end as status
        from generate_series(1, {rows}) t(i)
    """)
    conn.close()


def run_qdo(args: list[str], db_path: str) -> tuple[float, bool]:
    """Run a qdo command and return (elapsed_seconds, success)."""
    cmd = ["uv", "run", "qdo", *args, "--connection", db_path]
    t0 = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.monotonic() - t0
    return elapsed, result.returncode == 0


def run_benchmarks(db_path: str, rows: int, operations: list[str]) -> list[dict]:
    """Run benchmarks and return results."""
    results: list[dict] = []

    op_map: dict[str, list[str]] = {
        "preview": ["preview", "-t", "benchmark", "--rows", "100"],
        "inspect": ["inspect", "-t", "benchmark"],
        "profile": ["profile", "-t", "benchmark", "--no-sample"],
        "profile --sample 100000": ["profile", "-t", "benchmark", "--sample", "100000"],
        "dist (numeric)": ["dist", "-t", "benchmark", "-C", "amount", "--no-sample"],
        "dist (categorical)": ["dist", "-t", "benchmark", "-C", "category", "--no-sample"],
        "dist --sample 100000": [
            "dist", "-t", "benchmark", "-C", "amount", "--sample", "100000",
        ],
    }

    for op in operations:
        if op not in op_map:
            print(f"Unknown operation: {op}", file=sys.stderr)
            continue
        args = op_map[op]
        elapsed, ok = run_qdo(args, db_path)
        results.append({"operation": op, "rows": rows, "time": elapsed, "ok": ok})
        status = "ok" if ok else "FAIL"
        print(f"  {op:<28} {elapsed:>8.3f}s  {status}", file=sys.stderr)

    return results


def print_results(results: list[dict]) -> None:
    """Print benchmark results as a Rich table."""
    from rich.console import Console
    from rich.table import Table

    table = Table(title="qdo benchmark results", show_lines=True)
    table.add_column("Operation", style="cyan")
    table.add_column("Rows", justify="right")
    table.add_column("Time (s)", justify="right")
    table.add_column("Status")

    for r in results:
        status = "[green]ok[/green]" if r["ok"] else "[red]FAIL[/red]"
        table.add_row(r["operation"], f"{r['rows']:,}", f"{r['time']:.3f}", status)

    Console().print(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark qdo operations.")
    parser.add_argument(
        "--rows", type=int, default=1_000_000, help="Number of rows (default: 1,000,000)"
    )
    parser.add_argument(
        "--operations",
        type=str,
        default=None,
        help=f"Comma-separated list of operations (default: all). Options: {', '.join(ALL_OPERATIONS)}",
    )
    args = parser.parse_args()

    operations = ALL_OPERATIONS
    if args.operations:
        operations = [op.strip() for op in args.operations.split(",")]

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "benchmark.duckdb")
        print(f"Generating {args.rows:,} rows...", file=sys.stderr)
        t0 = time.monotonic()
        generate_db(db_path, args.rows)
        gen_time = time.monotonic() - t0
        print(f"Generated in {gen_time:.1f}s\n", file=sys.stderr)

        results = run_benchmarks(db_path, args.rows, operations)
        print()
        print_results(results)


if __name__ == "__main__":
    main()
