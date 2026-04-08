"""Interactive tutorial runner — walks through qdo lessons sequentially."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from querido.tutorial._helpers import _banner, _dim, _pause, _run_qdo


@dataclass
class Lesson:
    """A single tutorial lesson."""

    number: int
    title: str
    explanation: str
    commands: list[str] = field(default_factory=list)
    notice: str = ""
    info_only: bool = False


def get_lessons(db_path: str) -> list[Lesson]:
    """Return the ordered list of tutorial lessons, parameterized with *db_path*."""
    db = db_path
    return [
        Lesson(
            number=1,
            title="Welcome to qdo!",
            explanation=(
                "qdo is a CLI toolkit for exploring and analyzing data in\n"
                "  SQLite, DuckDB, Snowflake, and Parquet files.\n"
                "\n"
                "  This tutorial uses a National Parks database with 4 tables:\n"
                "    parks            ~60 US national parks\n"
                "    trails           ~250 hiking trails\n"
                "    wildlife_sightings  1,000 animal sightings\n"
                "    visitor_stats    ~2,800 monthly visitor records\n"
                "\n"
                "  We'll walk through qdo's commands step by step.\n"
                "  Press Enter at each prompt to run the command."
            ),
            info_only=True,
        ),
        Lesson(
            number=2,
            title="catalog — see all tables at a glance",
            explanation=(
                "Start by seeing what tables exist, how many rows they have,\n"
                "  and what columns are in each one."
            ),
            commands=[f"catalog -c {db}"],
            notice=(
                "Notice the 4 tables with their row counts and column types.\n"
                "  This is your map of the database."
            ),
        ),
        Lesson(
            number=3,
            title="inspect — drill into a table's structure",
            explanation=(
                "Pick a table and see its columns in detail: types,\n  nullability, and row count."
            ),
            commands=[f"inspect -c {db} -t parks"],
            notice=(
                "Notice the mix of types: varchar, double, integer, boolean, date.\n"
                "  The description column is nullable — some parks have no description."
            ),
        ),
        Lesson(
            number=4,
            title="preview — see actual data",
            explanation="Look at real rows to understand what the data contains.",
            commands=[f"preview -c {db} -t trails -r 10"],
            notice=(
                "Notice the trail names, distances, and difficulties.\n"
                "  Some estimated_hours values are NULL."
            ),
        ),
        Lesson(
            number=5,
            title="profile — statistical summary",
            explanation=(
                "Get min/max, mean, null counts, and distinct values\n"
                "  for every column in a table."
            ),
            commands=[f"profile -c {db} -t wildlife_sightings"],
            notice=(
                "Look at null counts — notes is ~60% null, trail_id is ~30% null.\n"
                "  The count column has a skewed distribution (min 1, but max much higher)."
            ),
        ),
        Lesson(
            number=6,
            title="profile --top — frequent values",
            explanation=(
                "Use --top to see the most common values for specific columns.\n"
                "  Great for understanding categorical data."
            ),
            commands=[
                f"profile -c {db} -t wildlife_sightings --columns species,category --top 5",
            ],
            notice=(
                "Elk and Mule Deer are the most commonly sighted species.\n"
                "  Mammals dominate, followed by birds."
            ),
        ),
        Lesson(
            number=7,
            title="dist — numeric distribution (histogram)",
            explanation=(
                "Visualize how a numeric column is distributed.\n"
                "  qdo creates a histogram with configurable buckets."
            ),
            commands=[f"dist -c {db} -t trails -C distance_miles"],
            notice=(
                "Most trails are shorter (under 10 miles).\n"
                "  The distribution is right-skewed — a few trails are very long."
            ),
        ),
        Lesson(
            number=8,
            title="dist — categorical distribution",
            explanation=(
                "For text columns, dist shows the top values by frequency.\n"
                "  See how wildlife sightings break down by category."
            ),
            commands=[f"dist -c {db} -t wildlife_sightings -C category --top 10"],
            notice=(
                "Mammals make up over half of all sightings.\n"
                "  Birds are second. Fish, reptiles, and amphibians are rarer."
            ),
        ),
        Lesson(
            number=9,
            title="values — distinct values for a column",
            explanation=(
                "See every unique value in a column with its count.\n"
                "  Useful for understanding enums and categories."
            ),
            commands=[f"values -c {db} -t parks -C region"],
            notice=(
                "There are 7 NPS regions. Intermountain has the most parks,\n"
                "  followed by Pacific West and Alaska."
            ),
        ),
        Lesson(
            number=10,
            title="quality — find data issues",
            explanation=(
                "Get a quality report: null rates, uniqueness, and\n  potential data problems."
            ),
            commands=[f"quality -c {db} -t wildlife_sightings"],
            notice=(
                "notes and trail_id have significant null rates.\n"
                "  sighting_id has 100% unique values (as expected for a primary key)."
            ),
        ),
        Lesson(
            number=11,
            title="query — run ad-hoc SQL",
            explanation=(
                "Write your own SQL to answer specific questions.\n"
                "  Which parks have the most wildlife sightings?"
            ),
            commands=[
                f'query -c {db} --sql "select p.name, count(*) as sightings '
                f"from parks p join wildlife_sightings ws "
                f"on p.park_id = ws.park_id "
                f'group by p.name order by sightings desc limit 10"',
            ],
            notice=(
                "The most visited parks tend to have more sightings —\n"
                "  more visitors means more eyes on the wildlife."
            ),
        ),
        Lesson(
            number=12,
            title="pivot — aggregate with GROUP BY",
            explanation=(
                "Quick aggregation without writing SQL.\n"
                "  What's the average visitor count by trail condition?"
            ),
            commands=[
                f'pivot -c {db} -t visitor_stats -g trail_conditions -a "avg(visitors)"',
            ],
            notice=(
                "Parks with excellent trail conditions get more visitors.\n"
                "  Closed trails correlate with the lowest visitor counts."
            ),
        ),
        Lesson(
            number=13,
            title="sql — generate SQL from schema",
            explanation=(
                "Generate SQL statements from table metadata.\n"
                "  Useful as a starting point for custom queries."
            ),
            commands=[
                f"sql select -c {db} -t parks",
                f"sql ddl -c {db} -t trails",
            ],
            notice=(
                "The SELECT includes all column names — ready to customize.\n"
                "  The DDL gives you a CREATE TABLE you can use in another database."
            ),
        ),
        Lesson(
            number=14,
            title="export — get data out",
            explanation=(
                "Export query results to CSV, TSV, JSON, or JSONL.\n"
                "  Pipe to other tools or save to files."
            ),
            commands=[f"--format csv preview -c {db} -t parks -r 5"],
            notice="CSV output goes to stdout — pipe it to a file or another tool.",
        ),
        Lesson(
            number=15,
            title="Tutorial Complete!",
            explanation=(
                "You've learned the core qdo workflow:\n"
                "\n"
                "  Explore:   catalog → inspect → preview → profile → dist → values\n"
                "  Query:     query → pivot → export\n"
                "  Generate:  sql select/ddl\n"
                "\n"
                "  Tips:\n"
                "    qdo --help                  See all commands\n"
                "    qdo <command> --help         See options for a command\n"
                "    qdo --format json <cmd>      Machine-readable output\n"
                "    export QDO_FORMAT=json        Set format for all commands\n"
                "    qdo --show-sql <cmd>          See the SQL being executed\n"
                "\n"
                "  Happy exploring!"
            ),
            info_only=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Tutorial runner
# ---------------------------------------------------------------------------


def run_tutorial(
    *,
    start_lesson: int = 1,
    list_only: bool = False,
    db_path: str | None = None,
) -> None:
    """Run the interactive tutorial.

    Generates a tutorial DB in a temp dir (unless *db_path* is provided),
    runs lessons sequentially, and cleans up on exit.
    """
    import atexit
    import tempfile

    from querido.tutorial.data import create_tutorial_db

    # Create or use existing DB
    cleanup_dir: str | None = None
    if db_path is None:
        tmp_dir = tempfile.mkdtemp(prefix="qdo_tutorial_")
        cleanup_dir = tmp_dir
        db_file = Path(tmp_dir) / "national_parks.duckdb"
    else:
        db_file = Path(db_path)

    lessons = get_lessons(str(db_file))

    if list_only:
        print(f"\n  {'#':>3}  {'Title'}")
        print(f"  {'─' * 3}  {'─' * 45}")
        for lesson in lessons:
            tag = "(info)" if lesson.info_only else ""
            print(f"  {lesson.number:>3}  {lesson.title} {_dim(tag)}")
        print()
        return

    # Generate DB (after --list check so --list doesn't need duckdb)
    if db_path is None:
        # Register cleanup as safety net
        def _cleanup() -> None:
            import shutil as _shutil

            if cleanup_dir:
                _shutil.rmtree(cleanup_dir, ignore_errors=True)

        atexit.register(_cleanup)

        print(_dim("  Generating National Parks database..."), end=" ", flush=True)
        create_tutorial_db(db_file)
        print(_dim("done.\n"))

    try:
        for lesson in lessons:
            if lesson.number < start_lesson:
                continue

            _banner(f"Lesson {lesson.number}/{len(lessons)}: {lesson.title}")
            print(f"  {lesson.explanation}")
            print()

            if lesson.info_only:
                _pause()
                continue

            for cmd in lesson.commands:
                _pause()
                _run_qdo(cmd)

            if lesson.notice:
                print(f"  {_dim(lesson.notice)}")
                print()

    except SystemExit:
        pass
    finally:
        if cleanup_dir:
            import shutil as _shutil

            _shutil.rmtree(cleanup_dir, ignore_errors=True)
