"""Tests for the tutorial command and data generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def _scalar(conn: Any, sql: str) -> Any:
    """Run a single-column, single-row query and return the scalar.

    Centralizes the ``fetchone() is not None`` assertion so individual
    tests don't each carry a type-ignore for the subscript.
    """
    row = conn.execute(sql).fetchone()
    assert row is not None, f"query returned no rows: {sql}"
    return row[0]


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tutorial_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate the tutorial DB once per test module (~2s) and share it."""
    from querido.tutorial.data import create_tutorial_db

    db_path = tmp_path_factory.mktemp("tutorial_db") / "tutorial.duckdb"
    create_tutorial_db(db_path)
    return db_path


class TestDataGeneration:
    """Assertions on the shape and distribution of the generated tutorial DB.

    All tests share the ``tutorial_db`` module-scoped fixture so the DB is
    only built once.  ``test_deterministic`` is the exception — by
    definition it must build two DBs to compare.
    """

    def test_creates_all_tables(self, tutorial_db: Path) -> None:
        conn = duckdb.connect(str(tutorial_db), read_only=True)
        tables = {r[0] for r in conn.execute("show tables").fetchall()}
        conn.close()
        assert tables == {"parks", "trails", "wildlife_sightings", "visitor_stats"}

    def test_row_counts(self, tutorial_db: Path) -> None:
        conn = duckdb.connect(str(tutorial_db), read_only=True)
        parks = _scalar(conn, "select count(*) from parks")
        trails = _scalar(conn, "select count(*) from trails")
        sightings = _scalar(conn, "select count(*) from wildlife_sightings")
        stats = _scalar(conn, "select count(*) from visitor_stats")
        conn.close()

        assert 55 <= parks <= 65
        assert 150 <= trails <= 300
        assert sightings == 1000
        assert 2000 <= stats <= 3500

    def test_deterministic(self, tmp_path: Path) -> None:
        """Uses its own pair of DBs; cannot share the module fixture."""
        from querido.tutorial.data import create_tutorial_db

        db1 = tmp_path / "a.duckdb"
        db2 = tmp_path / "b.duckdb"
        create_tutorial_db(db1)
        create_tutorial_db(db2)

        c1 = duckdb.connect(str(db1), read_only=True)
        c2 = duckdb.connect(str(db2), read_only=True)
        for table in ["parks", "trails", "wildlife_sightings", "visitor_stats"]:
            r1 = c1.execute(f"select * from {table}").fetchall()
            r2 = c2.execute(f"select * from {table}").fetchall()
            assert r1 == r2, f"Non-deterministic data in {table}"
        c1.close()
        c2.close()

    def test_foreign_keys_valid(self, tutorial_db: Path) -> None:
        conn = duckdb.connect(str(tutorial_db), read_only=True)

        # All trails reference valid parks
        orphan_trails = _scalar(
            conn,
            "select count(*) from trails t "
            "where not exists (select 1 from parks p where p.park_id = t.park_id)",
        )
        assert orphan_trails == 0

        # All sightings reference valid parks
        orphan_sightings = _scalar(
            conn,
            "select count(*) from wildlife_sightings ws "
            "where not exists (select 1 from parks p where p.park_id = ws.park_id)",
        )
        assert orphan_sightings == 0

        # Non-null trail_ids in sightings reference valid trails
        orphan_trail_refs = _scalar(
            conn,
            "select count(*) from wildlife_sightings ws "
            "where ws.trail_id is not null "
            "and not exists (select 1 from trails t where t.trail_id = ws.trail_id)",
        )
        assert orphan_trail_refs == 0

        # Visitor stats reference valid parks
        orphan_stats = _scalar(
            conn,
            "select count(*) from visitor_stats vs "
            "where not exists (select 1 from parks p where p.park_id = vs.park_id)",
        )
        assert orphan_stats == 0

        conn.close()

    def test_null_rates(self, tutorial_db: Path) -> None:
        conn = duckdb.connect(str(tutorial_db), read_only=True)

        # Parks description: ~20% null
        desc_null = _scalar(
            conn,
            "select 100.0 * count(*) filter (where description is null) / count(*) from parks",
        )
        assert 10 <= desc_null <= 35

        # Sighting notes: ~60% null
        notes_null = _scalar(
            conn,
            "select 100.0 * count(*) filter (where notes is null) / count(*) "
            "from wildlife_sightings",
        )
        assert 45 <= notes_null <= 75

        # Sighting trail_id: ~30% null
        trail_null = _scalar(
            conn,
            "select 100.0 * count(*) filter (where trail_id is null) / count(*) "
            "from wildlife_sightings",
        )
        assert 20 <= trail_null <= 45

        conn.close()


# ---------------------------------------------------------------------------
# Lesson definitions
# ---------------------------------------------------------------------------


class TestLessons:
    def test_lesson_count(self) -> None:
        from querido.tutorial.runner import get_lessons

        lessons = get_lessons("/tmp/fake.duckdb")
        assert len(lessons) == 15

    def test_lessons_reference_db_path(self) -> None:
        from querido.tutorial.runner import get_lessons

        db = "/tmp/test_abc.duckdb"
        lessons = get_lessons(db)
        for lesson in lessons:
            if not lesson.info_only:
                for cmd in lesson.commands:
                    assert db in cmd, f"Lesson {lesson.number} missing db path in: {cmd}"

    def test_first_and_last_are_info_only(self) -> None:
        from querido.tutorial.runner import get_lessons

        lessons = get_lessons("/tmp/fake.duckdb")
        assert lessons[0].info_only
        assert lessons[-1].info_only


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


class TestTutorialCLI:
    # test_help and test_shows_in_help dropped (2026-04-17): both asserted
    # on Typer-rendered help text; they tested the framework's docstring
    # rendering rather than our code.

    def test_list(self) -> None:
        result = runner.invoke(app, ["tutorial", "explore", "--list"])
        assert result.exit_code == 0
        assert "Welcome" in result.output
        assert "catalog" in result.output
