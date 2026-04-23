"""Interactive tutorial runner — walks through qdo lessons sequentially.

The tutorial is framed around qdo's compounding loop —
``discover → understand → capture → answer → hand off`` — not a
command-by-command tour. Each lesson's value is narrative: the next
command's output is sharper *because* of the previous one.
"""

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


def get_lessons(db_path: str, *, report_path: str | None = None) -> list[Lesson]:
    """Return the ordered list of tutorial lessons, parameterized with *db_path*.

    ``report_path`` is the HTML output path used in the hand-off lesson;
    when omitted, a sibling file next to the DB is used.
    """
    db = db_path
    report_out = report_path or str(Path(db_path).with_suffix(".report.html"))
    return [
        Lesson(
            number=1,
            title="Welcome to qdo",
            explanation=(
                "qdo is an agent-first CLI for exploring SQLite, DuckDB,\n"
                "  Snowflake, and Parquet data.\n"
                "\n"
                "  The pitch: each step accumulates understanding that\n"
                "  sharpens the next step. Not a browser — a memory.\n"
                "\n"
                "    discover → understand → capture → answer → hand off\n"
                "    catalog    context      metadata   query     report\n"
                "\n"
                "  This tutorial walks that loop using a National Parks DB:\n"
                "    parks            ~60 US national parks\n"
                "    trails           ~250 hiking trails\n"
                "    wildlife_sightings  1,000 animal sightings\n"
                "    visitor_stats    ~2,800 monthly visitor records\n"
                "\n"
                "  Press Enter at each prompt to run the command."
            ),
            info_only=True,
        ),
        Lesson(
            number=2,
            title="catalog — your map",
            explanation=(
                "Step 1: discover. See every table, its row count, and\n"
                "  its columns. This is where every investigation starts."
            ),
            commands=[f"catalog -c {db}"],
            notice=(
                "Four tables with their types and row counts — now you\n"
                "  know what's on the table before you pick one to dive into."
            ),
        ),
        Lesson(
            number=3,
            title="context — everything about one table in one call",
            explanation=(
                "Step 2: understand. `context` returns schema + stats +\n"
                "  sample values in a single scan. It replaces separate\n"
                "  inspect, preview, and profile calls for most workflows.\n"
                "\n"
                "  This is the anchor command for both humans and agents."
            ),
            commands=[f"context -c {db} -t parks"],
            notice=(
                "Notice: column types, null rates, and actual sample values\n"
                "  all at once. For `region` — a low-cardinality string —\n"
                "  you can see the full vocabulary. That's a hint we'll\n"
                "  use in the next two lessons."
            ),
        ),
        Lesson(
            number=4,
            title="values — a column's full vocabulary",
            explanation=(
                "Before capturing knowledge about a column, look at every\n"
                "  distinct value. `values` is cheap on low-cardinality\n"
                "  columns and perfect for categorical fields."
            ),
            commands=[f"values -c {db} -t parks -C region"],
            notice=(
                "7 NPS regions. This is the kind of information we want\n"
                "  qdo to *remember* so future scans can validate against it."
            ),
        ),
        Lesson(
            number=5,
            title="capture — teach qdo what you just learned",
            explanation=(
                "Step 3: capture. Create a metadata file for `parks`, then\n"
                "  let qdo propose deterministic additions from fresh scans\n"
                "  (temporal columns, valid values for enum-like fields,\n"
                "  high-null flags). `--apply` writes them.\n"
                "\n"
                "  From now on, this table has persistent memory."
            ),
            commands=[
                f"metadata init -c {db} -t parks",
                f"metadata suggest -c {db} -t parks --apply",
                f"metadata show -c {db} -t parks",
            ],
            notice=(
                "The YAML now carries valid_values for `region` (and any\n"
                "  other low-cardinality string columns). The next command\n"
                "  will use that memory — this is the compounding loop."
            ),
        ),
        Lesson(
            number=6,
            title="quality — the loop pays off",
            explanation=(
                "`quality` checks nulls, uniqueness, and — crucially — any\n"
                "  row whose value isn't in the stored `valid_values`.\n"
                "\n"
                "  Because we captured the region vocabulary in lesson 5,\n"
                "  `quality` now flags enum violations automatically."
            ),
            commands=[f"quality -c {db} -t parks --exact"],
            notice=(
                "Each column gets a status (ok / warn / fail) and a list\n"
                "  of issues. Because valid_values are stored for region,\n"
                "  quality also reports invalid_count — zero bad rows here.\n"
                "  That's the compounding loop in action.\n"
                "\n"
                "  (We passed --exact so distinct counts are computed with\n"
                "  COUNT(DISTINCT) rather than an approximate sketch —\n"
                "  cheap on 59 rows, worth remembering for small tables.)"
            ),
        ),
        Lesson(
            number=7,
            title="dist — visualize a distribution",
            explanation=(
                "For a numeric column, `dist` renders a histogram. For a\n"
                "  text column, it's a top-N frequency view. Use it when\n"
                "  shape matters more than summary stats."
            ),
            commands=[f"dist -c {db} -t trails -C distance_miles"],
            notice=(
                "Most trails are short; a few very long ones skew the tail.\n"
                "  Right-skewed distributions are common in travel data."
            ),
        ),
        Lesson(
            number=8,
            title="answer — ad-hoc SQL and quick pivots",
            explanation=(
                "Step 4: answer. Use `query` for real SQL and `pivot` for\n"
                "  GROUP BY aggregations without authoring SQL by hand."
            ),
            commands=[
                f'query -c {db} --sql "select p.name, count(*) as sightings '
                f"from parks p join wildlife_sightings ws "
                f"on p.park_id = ws.park_id "
                f'group by p.name order by sightings desc limit 10"',
                f'pivot -c {db} -t visitor_stats -g trail_conditions -a "avg(visitors)"',
            ],
            notice=(
                "Parks with more visitors tend to have more sightings —\n"
                "  and better trail conditions correlate with higher visits.\n"
                "  Both commands respect the metadata you captured earlier."
            ),
        ),
        Lesson(
            number=9,
            title="hand off — report, bundle, or agent",
            explanation=(
                "Step 5: hand off. `report table` builds a single-file HTML\n"
                "  summary you can share with someone who doesn't have qdo.\n"
                "  `bundle export` packages metadata + workflows for another\n"
                "  teammate. And the whole loop is agent-ready via the skill\n"
                "  file shipped in `integrations/skills/SKILL.md`."
            ),
            commands=[f"report table -c {db} -t parks -o {report_out}"],
            notice=(
                f"Report saved to {report_out}. Open it in a browser —\n"
                "  schema, metadata, quality flags, sample values, all in\n"
                "  one offline-safe HTML file.\n"
                "\n"
                "  Next step for coding-agent workflows: run\n"
                "  `qdo tutorial agent` — it walks through enriching\n"
                "  metadata and feeding it to an LLM for better SQL."
            ),
        ),
        Lesson(
            number=10,
            title="Tutorial complete",
            explanation=(
                "You've run the full compounding loop:\n"
                "\n"
                "    catalog → context → metadata capture → quality →\n"
                "    query → report → hand off\n"
                "\n"
                "  Each step made the next sharper. That's the pitch.\n"
                "\n"
                "  Where to go next:\n"
                "    qdo tutorial agent            Metadata + AI-assisted SQL\n"
                "    qdo --help                    All commands\n"
                "    qdo <command> --help          Options for one command\n"
                "    qdo -f json <cmd>             Machine-readable output\n"
                "    qdo workflow list             Pre-built investigation recipes\n"
                "    qdo bundle export ...         Share metadata with a teammate\n"
                "\n"
                "  Skill file for coding agents:\n"
                "    Claude Code:  integrations/skills/SKILL.md\n"
                "    Continue.dev: integrations/continue/qdo.md\n"
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
    runs lessons sequentially, and cleans up on exit. Metadata writes
    during the tutorial are redirected into the same temp dir via
    ``QDO_METADATA_DIR`` so the user's cwd stays clean.
    """
    import atexit
    import os
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

    # Keep metadata writes + the generated report inside the tutorial scratch
    # dir so re-runs are idempotent and nothing pollutes the user's project.
    scratch = Path(cleanup_dir) if cleanup_dir else db_file.parent
    metadata_dir = scratch / "metadata"
    report_file = scratch / "parks-report.html"

    lessons = get_lessons(str(db_file), report_path=str(report_file))

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

    # Scope metadata writes to the scratch dir for the lifetime of the tutorial.
    prior_metadata_dir = os.environ.get("QDO_METADATA_DIR")
    os.environ["QDO_METADATA_DIR"] = str(metadata_dir)
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
        if prior_metadata_dir is None:
            os.environ.pop("QDO_METADATA_DIR", None)
        else:
            os.environ["QDO_METADATA_DIR"] = prior_metadata_dir
        if cleanup_dir:
            import shutil as _shutil

            _shutil.rmtree(cleanup_dir, ignore_errors=True)
