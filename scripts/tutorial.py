"""Interactive qdo tutorial.

Walk through qdo's features step by step with real databases.
Requires test data: uv run python scripts/init_test_data.py

Usage:
    uv run python scripts/tutorial.py
"""

import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
SQLITE_DB = DATA_DIR / "test.db"
DUCKDB_DB = DATA_DIR / "test.duckdb"


def run_qdo(args: str) -> str:
    """Run a qdo command and return its output."""
    result = subprocess.run(
        ["uv", "run", "qdo", *args.split()],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    return result.stdout + result.stderr


def banner(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def step(title: str, command: str, explanation: str) -> None:
    print(f"\n--- {title} ---")
    print(f"\n  {explanation}\n")
    print(f"  $ qdo {command}")
    wait()
    output = run_qdo(command)
    print(output)


def wait() -> None:
    input("  [Press Enter to run] ")


def main() -> None:
    # Check prerequisites
    if not SQLITE_DB.exists() or not DUCKDB_DB.exists():
        print("Test databases not found!")
        print("Run this first:  uv run python scripts/init_test_data.py")
        sys.exit(1)

    banner("Welcome to the qdo tutorial!")

    print("  qdo (querido) is a CLI data analysis toolkit for")
    print("  SQLite, DuckDB, Snowflake, and Parquet files.")
    print()
    print("  This tutorial uses two sample databases with 1,000 rows each:")
    print(f"    SQLite:  {SQLITE_DB}")
    print(f"    DuckDB:  {DUCKDB_DB}")
    print()
    print("  Each database has two tables: customers and products.")
    print()
    print("  We'll walk through each command interactively.")
    print("  Press Enter at each prompt to run the command.")
    wait()

    # --- Help ---
    banner("1. Getting Help")

    step(
        "See all available commands",
        "--help",
        "The --help flag shows available commands and options.",
    )

    step(
        "Check the version",
        "--version",
        "Verify which version of qdo is installed.",
    )

    # --- Inspect ---
    banner("2. Inspecting Tables")

    step(
        "Inspect a SQLite table",
        f"inspect --connection {SQLITE_DB} --table customers",
        "See column names, types, nullability, and row count.\n"
        "  This tells you the shape of your data before querying it.",
    )

    step(
        "Inspect a DuckDB table",
        f"inspect -c {DUCKDB_DB} -t products",
        "Same command works with DuckDB. Note the different type names\n"
        "  (VARCHAR vs TEXT, BIGINT vs INTEGER) — qdo handles both.",
    )

    # --- Preview ---
    banner("3. Previewing Data")

    step(
        "Preview customers (default 20 rows)",
        f"preview --connection {SQLITE_DB} --table customers",
        "Quickly see what your data looks like. Default limit is 20 rows.",
    )

    step(
        "Preview with a custom row limit",
        f"preview -c {DUCKDB_DB} -t products -r 3",
        "Use -r to control how many rows you see.\n"
        "  Short flags: -c (connection), -t (table), -r (rows).",
    )

    # --- Profile ---
    banner("4. Profiling Data")

    step(
        "Profile all columns",
        f"profile --connection {SQLITE_DB} --table products",
        "Get statistical summaries: min/max, mean, median, stddev for\n"
        "  numeric columns; min/max length and distinct count for strings.",
    )

    step(
        "Profile specific columns",
        f"profile -c {DUCKDB_DB} -t products --columns price,stock",
        "Use --columns to focus on specific columns.\n  Comma-separated, no spaces.",
    )

    step(
        "Top frequent values",
        f"profile -c {SQLITE_DB} -t customers --columns company --top 5",
        "Use --top N to see the most frequent values per column.\n"
        "  Shows count and percentage of total rows.",
    )

    # --- Search ---
    banner("5. Searching Metadata")

    step(
        "Search for tables and columns",
        f"search -p email -c {SQLITE_DB}",
        "Find tables and columns matching a pattern.\n"
        "  Case-insensitive substring match. Returns table names,\n"
        "  column names, and types.",
    )

    step(
        "Search only column names",
        f"search -p price -c {DUCKDB_DB} --type column",
        "Use --type to narrow search: table, column, or all (default).",
    )

    # --- Distribution ---
    banner("6. Column Distributions")

    step(
        "Numeric distribution (histogram)",
        f"dist -c {SQLITE_DB} -t products -col price",
        "Visualize how values are distributed. Numeric columns get a\n"
        "  histogram with bucket counts. Default is 20 buckets.",
    )

    step(
        "Categorical distribution (frequency table)",
        f"dist -c {DUCKDB_DB} -t customers -col country --top 10",
        "String/categorical columns show the top values by frequency\n"
        "  with counts and percentages. Use --top to control how many.",
    )

    # --- SQL Generation ---
    banner("7. SQL Generation")

    step(
        "Generate a SELECT statement",
        f"sql select -c {SQLITE_DB} -t customers",
        "Generates a SELECT with all column names from the table.\n"
        "  Copy-paste ready SQL, output to stdout.",
    )

    step(
        "Generate a DDL statement",
        f"sql ddl -c {DUCKDB_DB} -t products",
        "Generates a CREATE TABLE statement matching the table schema.\n"
        "  Useful for recreating tables in another database.",
    )

    step(
        "Generate an INSERT template",
        f"sql insert -c {SQLITE_DB} -t customers",
        "Generates an INSERT statement with named placeholders.\n"
        "  Ready to fill in or use with parameterized queries.",
    )

    step(
        "Generate a scratch table",
        f"sql scratch -c {DUCKDB_DB} -t products --rows 3",
        "Creates a CREATE TEMP TABLE + INSERT statements with real\n"
        "  sample data. Great for building test fixtures.",
    )

    print("\n  Additional SQL subcommands (Snowflake only):")
    print("    qdo sql task -c <sf-conn> -t <table>       Snowflake task template")
    print("    qdo sql udf -c <conn> -t <table>           UDF template from columns")
    print("    qdo sql procedure -c <sf-conn> -t <table>  Stored procedure template")
    wait()

    # --- Template ---
    banner("8. Documentation Templates")

    step(
        "Generate a doc template",
        f"template -c {SQLITE_DB} -t customers",
        "Auto-generates a documentation template with column metadata:\n"
        "  name, type, nullable, distinct count, min/max, and sample values.\n"
        "  Leaves placeholders for business definitions and data owner.",
    )

    step(
        "Template with fewer sample values",
        f"template -c {DUCKDB_DB} -t products --sample-values 1",
        "Use --sample-values to control how many example values per column\n"
        "  (0 to skip samples entirely, max 10).",
    )

    # --- Lineage ---
    banner("9. View Lineage")

    print("  Retrieve the SQL definition of a view:")
    print("    qdo lineage -c <db> --view <view_name>")
    print()
    print("  (Requires a view in your database — skipping live demo.)")
    wait()

    # --- Cache ---
    banner("10. Metadata Cache")

    step(
        "Check cache status",
        "cache status",
        "The metadata cache stores table/column info locally for\n"
        "  faster search. Check what's currently cached.",
    )

    step(
        "Sync metadata to cache",
        f"cache sync -c {SQLITE_DB}",
        "Fetch all table and column metadata and store it locally.\n"
        "  Makes 'qdo search' faster on large databases.",
    )

    step(
        "Check cache after sync",
        "cache status",
        "Now you can see the cached metadata summary.",
    )

    print("\n  Other cache commands:")
    print("    qdo cache clear                  Clear all cached metadata")
    print("    qdo cache clear -c <connection>  Clear cache for one connection")
    wait()

    # --- Config ---
    banner("11. Managing Connections")

    print("  qdo stores named connections in connections.toml so you don't")
    print("  have to type file paths every time.")
    print()
    print("  Add a connection:")
    print("    $ qdo config add --name mydb --type sqlite --path ./data.db")
    print()
    print("  List connections:")
    print("    $ qdo config list")
    print()
    print("  Then use by name:")
    print("    $ qdo inspect -c mydb -t users")
    wait()

    # --- Explore ---
    banner("12. Interactive Exploration (TUI)")

    print("  Launch an interactive terminal UI for exploring table data:")
    print("    qdo explore -c <db> -t <table>")
    print()
    print("  Features: sorting, filtering, column inspection.")
    print("  Requires the TUI extra: pip install 'querido[tui]'")
    print()
    print("  (Skipping live demo — try it yourself!)")
    wait()

    # --- Snowflake ---
    banner("13. Snowflake-Specific Commands")

    print("  These commands require a Snowflake connection:")
    print()
    print("  Generate a Cortex Analyst semantic model YAML:")
    print("    qdo snowflake semantic -c <sf-conn> -t <table>")
    print("    qdo snowflake semantic -c <sf-conn> -t <table> -o model.yaml")
    print()
    print("  Trace upstream/downstream lineage via GET_LINEAGE:")
    print("    qdo snowflake lineage -c <sf-conn> --object DB.SCHEMA.TABLE")
    print("    qdo snowflake lineage ... --direction upstream --depth 3")
    wait()

    # --- Output Formats ---
    banner("14. Output Formats")

    step(
        "JSON output for piping",
        f"--format json inspect -c {SQLITE_DB} -t customers",
        "Use --format (or -f) to get machine-readable output.\n"
        "  Options: rich (default), markdown, json, csv, html.",
    )

    # --- Show SQL ---
    banner("15. Debugging with --show-sql")

    step(
        "See the SQL being executed",
        f"--show-sql preview -c {SQLITE_DB} -t customers -r 3",
        "The --show-sql global flag prints the rendered SQL to stderr\n"
        "  with syntax highlighting, before executing the query.\n"
        "  Useful for debugging or learning what qdo does under the hood.",
    )

    # --- Wrap up ---
    banner("16. Tutorial Complete!")

    print("  You've learned all of qdo's commands:")
    print()
    print("    qdo inspect -c <db> -t <table>          See table structure")
    print("    qdo preview -c <db> -t <table>          Preview rows")
    print("    qdo profile -c <db> -t <table>          Statistical profiling")
    print("    qdo profile ... --top N                 Top frequent values")
    print("    qdo search -p <pattern> -c <db>         Search metadata")
    print("    qdo dist -c <db> -t <tbl> -col <col>   Column distribution")
    print("    qdo sql select/insert/ddl/scratch ...   Generate SQL")
    print("    qdo sql task/udf/procedure ...          Snowflake SQL templates")
    print("    qdo template -c <db> -t <table>         Doc template generation")
    print("    qdo lineage -c <db> --view <view>       View SQL definition")
    print("    qdo cache sync/status/clear             Metadata cache")
    print("    qdo explore -c <db> -t <table>          Interactive TUI")
    print("    qdo snowflake semantic/lineage ...       Snowflake-specific")
    print("    qdo config add/list                     Manage connections")
    print("    qdo --show-sql <command>                See rendered SQL")
    print("    qdo --format json <command>             Machine-readable output")
    print()
    print("  Tips:")
    print("    - Pass a file path directly as --connection")
    print("    - .duckdb/.ddb extensions auto-detect DuckDB")
    print("    - .parquet files are queried via DuckDB (table = filename)")
    print("    - Use --db-type to override detection")
    print("    - Profile auto-samples tables over 1M rows")
    print("    - Use --no-sample to force a full table scan")
    print()
    print("  For more: qdo --help")
    print()


if __name__ == "__main__":
    main()
