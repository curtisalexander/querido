"""Agent tutorial runner — metadata enrichment and AI-assisted SQL workflow."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from querido.tutorial._helpers import (
    _banner,
    _dim,
    _pause,
    _run_qdo,
)


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
    """Return the ordered list of agent tutorial lessons."""
    db = db_path
    sql = (
        "select p.region, "
        "count(distinct p.park_id) as parks, "
        "count(ws.sighting_id) as sightings, "
        "round(count(ws.sighting_id) * 1.0 / count(distinct p.park_id), 1) as avg_per_park "
        "from parks p "
        "left join wildlife_sightings ws on p.park_id = ws.park_id "
        "where extract(year from p.established_date) < 1950 "
        "group by p.region "
        "order by avg_per_park desc"
    )
    return [
        Lesson(
            number=1,
            title="Welcome: Metadata for AI-Assisted SQL",
            explanation=(
                "This tutorial shows how to turn raw schema into rich metadata,\n"
                "  then use that metadata to get dramatically better SQL from a\n"
                "  coding agent.\n"
                "\n"
                "  Tables: parks, trails, wildlife_sightings, visitor_stats\n"
                "\n"
                "  By the end you will have:\n"
                "    • enriched metadata files under .qdo/metadata/\n"
                "    • a JSON payload ready to paste into any coding agent\n"
                "    • a real query showing what metadata-aware SQL looks like\n"
                "    • a skill file you can add to your coding agent"
            ),
            info_only=True,
        ),
        Lesson(
            number=2,
            title="catalog — survey what we'll document",
            explanation=(
                "Start with the full database catalog. Schema alone gives you\n"
                "  column names and types — but not meanings."
            ),
            commands=[f"catalog -c {db}"],
            notice=(
                "Column names like 'region' or 'time_of_day' hint at categories,\n"
                "  but what are the valid values? What does 'verified' mean?\n"
                "  Schema alone doesn't say — that's what metadata is for."
            ),
        ),
        Lesson(
            number=3,
            title="template — see the metadata scaffold",
            explanation=(
                "The 'template' command generates the full metadata scaffold:\n"
                "  machine-populated stats plus empty human-field placeholders.\n"
                "  This is a preview before we commit anything to disk."
            ),
            commands=[f"template -c {db} -t parks --sample-values 5"],
            notice=(
                "Machine fields (row_count, distinct_count, sample_values,\n"
                "  null_pct) are already filled in from the live database.\n"
                "  Human fields like description and valid_values show\n"
                "  '<description>' — those are yours to fill."
            ),
        ),
        Lesson(
            number=4,
            title="metadata init — create YAML files for two tables",
            explanation=(
                "Run 'metadata init' to write each table's scaffold to a YAML file.\n"
                "  We'll document parks and wildlife_sightings — the two tables\n"
                "  we'll join in our final query."
            ),
            commands=[
                f"metadata init -c {db} -t parks",
                f"metadata init -c {db} -t wildlife_sightings",
            ],
            notice=(
                "Each file lands at .qdo/metadata/<connection>/<table>.yaml.\n"
                "  Machine fields are already populated. Human fields are\n"
                "  placeholders — we'll fill those next."
            ),
        ),
        Lesson(
            number=5,
            title="metadata show — the unfinished state",
            explanation=(
                "Look at the parks metadata before adding any business context.\n"
                "  Notice the 0% completeness — all human fields are placeholders."
            ),
            commands=[f"metadata show -c {db} -t parks"],
            notice=(
                "table_description, data_owner, and every column description\n"
                "  read '<description>'. This is what an agent sees without\n"
                "  enrichment: just schema stats, no business meaning."
            ),
        ),
        Lesson(
            number=6,
            title="What good metadata looks like",
            explanation=(
                "Here is the parks metadata after a human fills it in.\n"
                "  The high-value additions are:\n"
                "\n"
                "  table_description:\n"
                "    'US National Parks managed by NPS. Primary reference table —\n"
                "    trails, wildlife_sightings, and visitor_stats join here\n"
                "    via park_id.'\n"
                "\n"
                "  region → valid_values:\n"
                "    [Alaska, Intermountain, Midwest, National Capital,\n"
                "     Northeast, Pacific West, Southeast]\n"
                "\n"
                "  established_date → description:\n"
                "    'Use EXTRACT(YEAR FROM established_date) to filter by year.'\n"
                "\n"
                "  observer → pii: true\n"
                "\n"
                "  wildlife_sightings.trail_id → description:\n"
                "    'NULL for ~30% of records. Always use LEFT JOIN to trails.'\n"
                "\n"
                "  These additions prevent the most common agent SQL mistakes:\n"
                "  invented enum values, wrong date comparisons, missing LEFT JOIN,\n"
                "  and unintentional exposure of PII columns."
            ),
            info_only=True,
        ),
        Lesson(
            number=7,
            title="metadata show — after enrichment",
            explanation=(
                "The same command, now with human fields filled in.\n"
                "  Notice the completeness score and the new valid_values."
            ),
            commands=[f"metadata show -c {db} -t parks"],
            notice=(
                "'region' now has valid_values listing all 7 NPS regions.\n"
                "  'observer' is flagged pii: true.\n"
                "  'established_date' explains the EXTRACT pattern.\n"
                "  These details prevent the most common agent SQL mistakes."
            ),
        ),
        Lesson(
            number=8,
            title="metadata list — completeness at a glance",
            explanation=(
                "See the completeness score for every documented table.\n"
                "  parks and wildlife_sightings are enriched; the others remind\n"
                "  you what still needs documentation."
            ),
            commands=[f"metadata list -c {db}"],
            notice=(
                "The completeness score is your metadata health check.\n"
                "  A score below 50% means the agent is mostly guessing."
            ),
        ),
        Lesson(
            number=9,
            title="Export metadata as JSON — your agent's context",
            explanation=(
                "This JSON output is exactly what you paste into a coding\n"
                "  agent's context window before asking it to write SQL."
            ),
            commands=[
                f"metadata show -c {db} -t parks -f json",
                f"metadata show -c {db} -t wildlife_sightings -f json",
            ],
            notice=(
                "The JSON captures everything: types, null rates, sample values,\n"
                "  valid enum values, and your business descriptions — in a\n"
                "  single paste. Copy both blocks for a multi-table query."
            ),
        ),
        Lesson(
            number=10,
            title="The Agent Prompt Pattern",
            explanation=(
                "Combine the JSON output with your question in a prompt like this:\n"
                "\n"
                "  You are a SQL expert. I'm working with a DuckDB database.\n"
                "\n"
                "  Table metadata:\n"
                "  [paste: qdo metadata show -c <db> -t parks -f json]\n"
                "  [paste: qdo metadata show -c <db> -t wildlife_sightings -f json]\n"
                "\n"
                "  Question: Which NPS region had the highest average number of\n"
                "  wildlife sightings per park, for parks established before 1950?\n"
                "\n"
                "  Use lowercase SQL keywords. Handle nulls per null_pct fields.\n"
                "  Use only valid enum values from valid_values fields.\n"
                "\n"
                "  The metadata unlocks three things for the agent:\n"
                "    • region has 7 documented valid values — no invented filters\n"
                "    • established_date is a DATE — agent uses EXTRACT for year\n"
                "    • wildlife_sightings.trail_id is nullable — agent uses LEFT JOIN"
            ),
            info_only=True,
        ),
        Lesson(
            number=11,
            title="query — the metadata-aware join",
            explanation=(
                "Here is the SQL a well-prompted agent generates for that question.\n"
                "  Three metadata clues shaped it:\n"
                "    • established_date needs EXTRACT(YEAR FROM ...)\n"
                "    • wildlife_sightings.trail_id is nullable → LEFT JOIN\n"
                "    • grouping by region uses a metadata-documented field"
            ),
            commands=[f'query -c {db} --sql "{sql}"'],
            notice=(
                "Intermountain and Pacific West dominate — large parks with dense\n"
                "  wildlife corridors. The LEFT JOIN ensured parks with zero\n"
                "  sightings still appear in the results."
            ),
        ),
        Lesson(
            number=12,
            title="metadata refresh — keep machine fields in sync",
            explanation=(
                "When data changes — new rows loaded, schema altered — run refresh.\n"
                "  It re-profiles the table and updates machine fields while\n"
                "  preserving all your human descriptions."
            ),
            commands=[f"metadata refresh -c {db} -t parks"],
            notice=(
                "Only machine fields changed (row_count, null_pct, sample_values).\n"
                "  Your descriptions, valid_values, and pii flags are untouched.\n"
                "  Run this after each data load to keep stats current."
            ),
        ),
        Lesson(
            number=13,
            title="Tutorial Complete!",
            explanation=(
                "You've learned the qdo metadata → agent workflow:\n"
                "\n"
                "  Document:  template → metadata init → metadata edit\n"
                "  Inspect:   metadata show → metadata list\n"
                "  Use:       metadata show -f json → paste into agent prompt\n"
                "  Maintain:  metadata refresh\n"
                "\n"
                "  What to explore next:\n"
                "\n"
                "  context — one command for everything an agent needs\n"
                "    qdo context -c <db> -t <table>             Schema + stats + sample values\n"
                "    qdo context -c <db> -t <table> -f json     Machine-readable output\n"
                "    Combines schema, null rates, distinct counts, min/max, and\n"
                "    top sample values in a single table scan (DuckDB/Snowflake).\n"
                "    If you've run metadata init, descriptions and valid_values are\n"
                "    merged in automatically.\n"
                "\n"
                "  Other commands:\n"
                "    qdo metadata init -c <yourdb> -t <table>   Document your data\n"
                "    qdo metadata edit -c <yourdb> -t <table>   Open in $EDITOR\n"
                "    qdo metadata list -c <yourdb>              Check completeness\n"
                "    qdo --help                                  See all commands\n"
                "\n"
                "  Skill file for coding agents — load the one matching your harness:\n"
                "    Claude Code:  integrations/skills/SKILL.md\n"
                "    Continue.dev: integrations/continue/qdo.md\n"
                "\n"
                "    Either gives your agent the full qdo workflow, this metadata\n"
                "    enrichment pattern, and the recommended prompt structure."
            ),
            info_only=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Metadata enrichment
# ---------------------------------------------------------------------------


def _enrich_metadata(yaml_path: Path, human_data: dict) -> None:
    """Merge human fields into a machine-populated metadata YAML file."""
    import yaml

    if not yaml_path.exists():
        return

    with open(yaml_path, encoding="utf-8") as f:
        meta = yaml.safe_load(f) or {}

    for key in ("table_description", "data_owner", "update_frequency", "notes"):
        if key in human_data:
            meta[key] = human_data[key]

    col_enrichments = human_data.get("columns", {})
    for col in meta.get("columns", []):
        name = col.get("name", "")
        if name in col_enrichments:
            for field_name in ("description", "pii", "valid_values"):
                if field_name in col_enrichments[name]:
                    col[field_name] = col_enrichments[name][field_name]

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(meta, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Tutorial runner
# ---------------------------------------------------------------------------


def run_agent_tutorial(
    *,
    start_lesson: int = 1,
    list_only: bool = False,
    db_path: str | None = None,
) -> None:
    """Run the agent-mode tutorial (metadata enrichment + AI-assisted SQL).

    Creates a temp database and metadata directory, walks through lessons
    showing the full metadata → agent → SQL workflow.
    """
    import atexit
    import shutil
    import tempfile

    from querido.tutorial.data import create_tutorial_db
    from querido.tutorial.metadata_fixtures import PARKS_HUMAN, WILDLIFE_SIGHTINGS_HUMAN

    cleanup_dir: str | None = None
    if db_path is None:
        tmp_dir = tempfile.mkdtemp(prefix="qdo_tutorial_agent_")
        cleanup_dir = tmp_dir
        db_file = Path(tmp_dir) / "national_parks.duckdb"
    else:
        db_file = Path(db_path)
        tmp_dir = str(db_file.parent)

    # Metadata lives in the temp dir — not the user's CWD
    meta_dir = Path(tmp_dir) / ".qdo" / "metadata"
    db_stem = db_file.stem  # "national_parks"

    lessons = get_lessons(str(db_file))

    if list_only:
        print(f"\n  {'#':>3}  {'Title'}")
        print(f"  {'─' * 3}  {'─' * 45}")
        for lesson in lessons:
            tag = "(info)" if lesson.info_only else ""
            print(f"  {lesson.number:>3}  {lesson.title} {_dim(tag)}")
        print()
        return

    # Require duckdb
    try:
        import duckdb as _duckdb  # noqa: F401
    except ImportError:
        import sys

        print(
            "Error: duckdb is required for the tutorial.\n"
            "Install it with: uv pip install 'querido[duckdb]'",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    if cleanup_dir:

        def _cleanup() -> None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)

        atexit.register(_cleanup)

    print(_dim("  Generating National Parks database..."), end=" ", flush=True)
    create_tutorial_db(db_file)
    print(_dim("done.\n"))

    # Subprocess env — point metadata commands at the temp dir
    meta_env = os.environ.copy()
    meta_env["QDO_METADATA_DIR"] = str(meta_dir)

    try:
        for lesson in lessons:
            if lesson.number < start_lesson:
                continue

            # After lesson 5 (empty metadata show), enrich both tables
            if lesson.number == 6:
                parks_yaml = meta_dir / db_stem / "parks.yaml"
                ws_yaml = meta_dir / db_stem / "wildlife_sightings.yaml"
                _enrich_metadata(parks_yaml, PARKS_HUMAN)
                _enrich_metadata(ws_yaml, WILDLIFE_SIGHTINGS_HUMAN)

            _banner(f"Lesson {lesson.number}/{len(lessons)}: {lesson.title}")
            print(f"  {lesson.explanation}")
            print()

            if lesson.info_only:
                _pause()
                continue

            for cmd in lesson.commands:
                _pause()
                _run_qdo(cmd, env=meta_env)

            if lesson.notice:
                print(f"  {_dim(lesson.notice)}")
                print()

    except SystemExit:
        pass
    finally:
        if cleanup_dir:
            shutil.rmtree(cleanup_dir, ignore_errors=True)
