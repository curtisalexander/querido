#!/usr/bin/env python3
"""Interactive feature demo for qdo.

Walks through qdo's features against a real database, showing each command
before running it and pausing for the user to examine the output.

Generates a temporary database with sample data — no setup required.

Usage:
    uv run python scripts/demo.py              # run all demos
    uv run python scripts/demo.py inspect      # run a specific demo
    uv run python scripts/demo.py --list       # list available demos
    uv run python scripts/demo.py --db FILE    # use your own database
"""

from __future__ import annotations

import argparse
import collections.abc
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------


def _term_width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def _color(code: str, text: str) -> str:
    """Wrap text in ANSI color if stdout is a tty."""
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def cyan(text: str) -> str:
    return _color("36", text)


def bold(text: str) -> str:
    return _color("1", text)


def dim(text: str) -> str:
    return _color("2", text)


def green(text: str) -> str:
    return _color("32", text)


def yellow(text: str) -> str:
    return _color("33", text)


def banner(title: str) -> None:
    w = _term_width()
    line = "─" * w
    print(f"\n{cyan(line)}")
    print(f"  {bold(title)}")
    print(f"{cyan(line)}\n")


def pause() -> None:
    """Wait for user to press Enter."""
    try:
        input(dim("  Press Enter to continue (Ctrl-C to quit)... "))
    except (KeyboardInterrupt, EOFError):
        print("\n")
        sys.exit(0)


def show_command(cmd: str) -> None:
    """Display the command that's about to run."""
    print(f"  {dim('$')} {green(f'qdo {cmd}')}")
    print()


def run_qdo(cmd: str) -> None:
    """Run a qdo command, streaming output to the terminal."""
    args = ["uv", "run", "qdo", *cmd.split()]
    subprocess.run(args, cwd=PROJECT_ROOT)
    print()


def step(title: str, cmd: str, note: str = "") -> None:
    """Show a title, optional note, the command, run it, then pause."""
    print(f"  {bold(title)}")
    if note:
        for line in note.strip().splitlines():
            print(f"  {dim(line)}")
    print()
    show_command(cmd)
    run_qdo(cmd)
    pause()


# ---------------------------------------------------------------------------
# Test database creation
# ---------------------------------------------------------------------------


def create_demo_db(path: str) -> str:
    """Create a SQLite database with varied sample data for demos."""
    conn = sqlite3.connect(path)

    # Customers table — strings, dates, nulls
    conn.execute("""
        create table customers (
            customer_id integer primary key,
            first_name text not null,
            last_name text not null,
            email text,
            city text,
            country text,
            signup_date text,
            lifetime_value real
        )
    """)

    customers = [
        (1, "Alice", "Chen", "alice@example.com", "Portland", "US", "2023-01-15", 1250.00),
        (2, "Bob", "Smith", None, "London", "UK", "2023-02-20", 890.50),
        (3, "Carlos", "Garcia", "carlos@test.com", "Madrid", "ES", "2023-03-01", 2100.00),
        (4, "Diana", "Johnson", "diana@example.com", "Portland", "US", "2023-04-10", None),
        (5, "Eve", "Williams", "eve@test.com", "London", "UK", "2023-05-22", 450.25),
        (6, "Frank", "Brown", "frank@example.com", "Berlin", "DE", "2023-06-15", 1800.00),
        (7, "Grace", "Lee", None, "Seoul", "KR", "2023-07-01", 3200.00),
        (8, "Hank", "Taylor", "hank@test.com", "Portland", "US", "2023-08-12", 670.00),
        (9, "Iris", "Wilson", "iris@example.com", "London", "UK", "2023-09-30", None),
        (10, "Jack", "Anderson", "jack@test.com", "Tokyo", "JP", "2023-10-05", 1950.75),
        (11, "Karen", "Thomas", "karen@example.com", "Portland", "US", "2024-01-10", 520.00),
        (12, "Leo", "Martinez", None, "Madrid", "ES", "2024-02-14", 780.50),
        (13, "Maya", "Davis", "maya@test.com", "Berlin", "DE", "2024-03-20", 1100.00),
        (14, "Nick", "Clark", "nick@example.com", "Seoul", "KR", "2024-04-01", 2400.00),
        (15, "Olivia", "Hall", "olivia@test.com", "Tokyo", "JP", "2024-05-15", None),
    ]
    conn.executemany("insert into customers values (?, ?, ?, ?, ?, ?, ?, ?)", customers)

    # Products table — numeric-heavy, good for distribution demos
    conn.execute("""
        create table products (
            product_id integer primary key,
            name text not null,
            category text not null,
            price real not null,
            stock integer not null,
            rating real,
            weight_kg real
        )
    """)

    products = [
        (1, "Widget A", "Electronics", 29.99, 150, 4.5, 0.3),
        (2, "Widget B", "Electronics", 49.99, 80, 4.2, 0.5),
        (3, "Gadget Pro", "Electronics", 199.99, 25, 4.8, 1.2),
        (4, "Basic Tee", "Clothing", 19.99, 500, 4.0, 0.2),
        (5, "Premium Jacket", "Clothing", 149.99, 45, 4.7, 0.8),
        (6, "Running Shoes", "Clothing", 89.99, 120, 4.3, 0.6),
        (7, "Coffee Maker", "Home", 79.99, 60, 4.6, 2.5),
        (8, "Blender", "Home", 59.99, 90, 3.9, 3.0),
        (9, "Desk Lamp", "Home", 34.99, 200, 4.1, 1.0),
        (10, "Novel: The Code", "Books", 14.99, 300, 4.4, 0.4),
        (11, "Cookbook", "Books", 24.99, 180, 4.0, 0.7),
        (12, "Travel Guide", "Books", 19.99, 100, 3.8, 0.5),
        (13, "Yoga Mat", "Sports", 39.99, 250, 4.6, 1.5),
        (14, "Dumbbell Set", "Sports", 69.99, 70, 4.3, 10.0),
        (15, "Tennis Racket", "Sports", 129.99, 35, 4.5, 0.3),
        (16, "Headphones", "Electronics", 79.99, 110, 4.4, 0.2),
        (17, "Tablet Stand", "Electronics", 24.99, 320, 3.7, 0.4),
        (18, "Winter Coat", "Clothing", 199.99, 30, 4.9, 1.1),
        (19, "Throw Pillow", "Home", 29.99, 400, 4.2, 0.8),
        (20, "Water Bottle", "Sports", 14.99, 600, 4.1, 0.3),
    ]
    conn.executemany("insert into products values (?, ?, ?, ?, ?, ?, ?)", products)

    # Orders table — for joins/lineage demos
    conn.execute("""
        create table orders (
            order_id integer primary key,
            customer_id integer not null,
            product_id integer not null,
            quantity integer not null,
            total real not null,
            order_date text not null
        )
    """)

    orders = [
        (1, 1, 3, 1, 199.99, "2024-01-15"),
        (2, 2, 4, 3, 59.97, "2024-01-20"),
        (3, 1, 7, 1, 79.99, "2024-02-10"),
        (4, 3, 1, 2, 59.98, "2024-02-14"),
        (5, 5, 10, 1, 14.99, "2024-03-01"),
        (6, 4, 6, 1, 89.99, "2024-03-05"),
        (7, 6, 13, 2, 79.98, "2024-03-20"),
        (8, 7, 3, 1, 199.99, "2024-04-01"),
        (9, 8, 16, 1, 79.99, "2024-04-15"),
        (10, 10, 15, 1, 129.99, "2024-05-01"),
    ]
    conn.executemany("insert into orders values (?, ?, ?, ?, ?, ?)", orders)

    # View for lineage demo
    conn.execute("""
        create view high_value_customers as
        select c.customer_id, c.first_name, c.last_name, c.email,
               sum(o.total) as total_spent
        from customers c
        join orders o on c.customer_id = o.customer_id
        group by c.customer_id, c.first_name, c.last_name, c.email
        having sum(o.total) > 100
    """)

    conn.commit()
    conn.close()
    return path


# ---------------------------------------------------------------------------
# Demo modules
# ---------------------------------------------------------------------------


def demo_inspect(db: str) -> None:
    """Inspect table structure and metadata."""
    banner("inspect — Table Structure")
    print("  See columns, types, nullability, defaults, and row count.\n")

    step(
        "Basic inspect",
        f"inspect -c {db} -t customers",
        "Shows column metadata and row count for the customers table.",
    )

    step(
        "Inspect another table",
        f"inspect -c {db} -t products",
        "Products has numeric columns (price, stock, rating) — good\n"
        "for profile and distribution demos later.",
    )


def demo_preview(db: str) -> None:
    """Preview rows from tables."""
    banner("preview — Quick Row Preview")
    print("  See actual data from a table. Default is 20 rows.\n")

    step(
        "Preview customers",
        f"preview -c {db} -t customers",
        "Notice some NULL values in email and lifetime_value —\nprofile will quantify this.",
    )

    step(
        "Preview with row limit",
        f"preview -c {db} -t orders -r 5",
        "Use -r to limit rows. Useful for large tables.",
    )


def demo_profile(db: str) -> None:
    """Profile column statistics."""
    banner("profile — Data Profiling")
    print("  Statistical summaries: min, max, mean, median, null count, distinct.\n")

    step(
        "Profile all columns",
        f"profile -c {db} -t products",
        "Numeric columns show min/max/mean/median/stddev.\nString columns show min/max length.",
    )

    step(
        "Profile specific columns",
        f"profile -c {db} -t products --columns price,rating",
        "Focus on the columns you care about.",
    )

    step(
        "Top frequent values",
        f"profile -c {db} -t products --columns category --top 5",
        "See the most common values for categorical columns.",
    )


def demo_search(db: str) -> None:
    """Search table and column metadata."""
    banner("search — Metadata Search")
    print("  Find tables and columns by name pattern.\n")

    step(
        "Search for 'price'",
        f"search -p price -c {db}",
        "Case-insensitive substring match across all tables.",
    )

    step(
        "Search tables only",
        f"search -p cust -c {db} --type table",
        "Use --type to narrow: table, column, or all (default).",
    )

    step(
        "Search columns only",
        f"search -p id -c {db} --type column",
        "Find all columns containing 'id' across all tables.",
    )


def demo_dist(db: str) -> None:
    """Column distribution visualization."""
    banner("dist — Column Distributions")
    print("  Histograms for numeric columns, frequency tables for categorical.\n")

    step(
        "Numeric distribution",
        f"dist -c {db} -t products -C price",
        "Histogram with default 20 buckets showing how prices\nare distributed across the range.",
    )

    step(
        "Numeric with fewer buckets",
        f"dist -c {db} -t products -C price -b 5",
        "Fewer buckets give a coarser view.",
    )

    step(
        "Categorical distribution",
        f"dist -c {db} -t products -C category",
        "String columns show top values by frequency with\ncounts and percentages.",
    )

    step(
        "Distribution with nulls",
        f"dist -c {db} -t customers -C lifetime_value -b 5",
        "Notice the null count — some customers have no lifetime value.",
    )


def demo_sql(db: str) -> None:
    """SQL statement generation."""
    banner("sql — Generate SQL Statements")
    print("  Generate ready-to-use SQL from table metadata.\n")

    step(
        "SELECT statement",
        f"sql select -c {db} -t customers",
        "All columns listed explicitly — better than SELECT *.",
    )

    step(
        "INSERT template",
        f"sql insert -c {db} -t orders",
        "Named placeholders ready for parameterized queries.",
    )

    step(
        "CREATE TABLE DDL",
        f"sql ddl -c {db} -t products",
        "Recreate the table schema in another database.",
    )

    step(
        "Scratch table with sample data",
        f"sql scratch -c {db} -t products -r 3",
        "Temp table + INSERT statements with real data.\nGreat for building test fixtures.",
    )


def demo_template(db: str) -> None:
    """Documentation template generation."""
    banner("template — Documentation Templates")
    print("  Auto-generate column documentation with real metadata.\n")

    step(
        "Generate template",
        f"template -c {db} -t customers --sample-values 3",
        "Columns with: name, type, nullable, distinct count, min/max,\n"
        "sample values, and placeholder fields for business definitions.",
    )


def demo_lineage(db: str) -> None:
    """View definition and lineage."""
    banner("lineage — View Definitions")
    print("  Retrieve the SQL definition of database views.\n")

    step(
        "View definition",
        f"lineage -c {db} --view high_value_customers",
        "Shows the SQL that defines the view, with syntax highlighting.",
    )


def demo_formats(db: str) -> None:
    """Output format options."""
    banner("formats — Machine-Readable Output")
    print("  All commands support multiple output formats.\n")

    step(
        "JSON output",
        f"--format json inspect -c {db} -t products",
        "Pipe to jq, feed to scripts, or send to an LLM.",
    )

    step(
        "Markdown output",
        f"--format markdown profile -c {db} -t products --columns price,stock",
        "Paste directly into documentation or PRs.",
    )

    step(
        "CSV output",
        f"--format csv inspect -c {db} -t customers",
        "Open in a spreadsheet or process with awk/pandas.",
    )


def demo_showsql(db: str) -> None:
    """Show the SQL being executed."""
    banner("--show-sql — See What's Running")
    print("  Print the rendered SQL to stderr before executing.\n")

    step(
        "Show SQL for preview",
        f"--show-sql preview -c {db} -t customers -r 3",
        "The SQL appears on stderr (above the output) with\n"
        "syntax highlighting. Useful for learning and debugging.",
    )

    step(
        "Show SQL for profile",
        f"--show-sql profile -c {db} -t products --columns price",
        "Profile queries are more complex — see what qdo generates.",
    )


def demo_cache(db: str) -> None:
    """Metadata cache management."""
    banner("cache — Local Metadata Cache")
    print("  Cache table/column metadata locally for faster search.\n")

    step(
        "Sync metadata",
        f"cache sync -c {db}",
        "Fetches all table and column metadata into a local SQLite cache.",
    )

    step(
        "Check cache status",
        "cache status",
        "Shows what's cached: connection name, table count, age.",
    )

    step(
        "Search uses cache automatically",
        f"search -p price -c {db}",
        "Search checks the cache first, falls back to live query.",
    )

    step(
        "Clear cache",
        f"cache clear -c {db}",
        "Remove cached metadata for this connection.",
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DEMOS: dict[str, tuple[collections.abc.Callable, str]] = {
    "inspect": (demo_inspect, "Table structure and metadata"),
    "preview": (demo_preview, "Quick row preview"),
    "profile": (demo_profile, "Column statistics and frequency"),
    "search": (demo_search, "Search tables and columns"),
    "dist": (demo_dist, "Column distribution visualization"),
    "sql": (demo_sql, "SQL statement generation"),
    "template": (demo_template, "Documentation template generation"),
    "lineage": (demo_lineage, "View definitions"),
    "formats": (demo_formats, "JSON, Markdown, CSV output"),
    "showsql": (demo_showsql, "See rendered SQL"),
    "cache": (demo_cache, "Metadata cache management"),
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive qdo feature demo.",
        epilog="Run with no arguments to walk through all features.",
    )
    parser.add_argument(
        "demos",
        nargs="*",
        metavar="DEMO",
        help="Specific demo(s) to run (default: all).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available demos and exit.",
    )
    parser.add_argument(
        "--db",
        metavar="FILE",
        help="Use an existing database instead of creating a demo database.",
    )
    args = parser.parse_args()

    if args.list:
        print("\nAvailable demos:\n")
        for name, (_, desc) in DEMOS.items():
            print(f"  {name:<12} {desc}")
        print(f"\nRun all:  uv run python {Path(__file__).name}")
        print(f"Run one:  uv run python {Path(__file__).name} inspect")
        print(f"Run some: uv run python {Path(__file__).name} inspect preview profile\n")
        return

    # Validate requested demos
    selected = args.demos or list(DEMOS.keys())
    for name in selected:
        if name not in DEMOS:
            print(f"Unknown demo: {name!r}")
            print(f"Available: {', '.join(DEMOS.keys())}")
            sys.exit(1)

    # Set up database
    if args.db:
        db_path = args.db
        if not Path(db_path).exists():
            print(f"Database not found: {db_path}")
            sys.exit(1)
        cleanup = False
    else:
        tmp_dir = tempfile.mkdtemp(prefix="qdo_demo_")
        db_path = os.path.join(tmp_dir, "demo.db")
        create_demo_db(db_path)
        cleanup = True

    try:
        banner("qdo Feature Demo")
        print(f"  Database: {db_path}")
        if not args.db:
            print("  (auto-generated demo database with customers, products, orders)")
        print(f"  Demos:    {', '.join(selected)}")
        print()
        pause()

        for name in selected:
            fn, _ = DEMOS[name]
            fn(db_path)

        banner("Demo Complete!")
        print("  Try these next:")
        print(f"    qdo explore -c {db_path} -t products    # interactive TUI")
        print(f"    qdo serve -c {db_path}                  # web UI")
        print("    qdo --help                                # full command reference")
        print()
    finally:
        if cleanup:
            import shutil as sh

            sh.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
