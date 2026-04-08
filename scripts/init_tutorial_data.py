"""Generate the National Parks tutorial database.

Usage:
    uv run python scripts/init_tutorial_data.py [--output PATH]
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate tutorial database.")
    parser.add_argument(
        "--output",
        "-o",
        default="data/tutorial.duckdb",
        help="Output path (default: data/tutorial.duckdb)",
    )
    args = parser.parse_args()

    from querido.tutorial.data import create_tutorial_db

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating tutorial database at {output}...")
    create_tutorial_db(output)

    import duckdb

    conn = duckdb.connect(str(output), read_only=True)
    for table in ["parks", "trails", "wildlife_sightings", "visitor_stats"]:
        count = conn.execute(f"select count(*) from {table}").fetchone()[0]
        print(f"  {table}: {count:,} rows")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
