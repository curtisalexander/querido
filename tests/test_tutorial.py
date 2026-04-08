"""Tests for the tutorial command and data generation."""

from __future__ import annotations

from pathlib import Path

import duckdb
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------


class TestDataGeneration:
    """Test that the tutorial database is generated correctly."""

    def test_creates_all_tables(self, tmp_path: Path) -> None:
        from querido.tutorial.data import create_tutorial_db

        db_path = tmp_path / "tutorial.duckdb"
        create_tutorial_db(db_path)

        conn = duckdb.connect(str(db_path), read_only=True)
        tables = {r[0] for r in conn.execute("show tables").fetchall()}
        conn.close()
        assert tables == {"parks", "trails", "wildlife_sightings", "visitor_stats"}

    def test_row_counts(self, tmp_path: Path) -> None:
        from querido.tutorial.data import create_tutorial_db

        db_path = tmp_path / "tutorial.duckdb"
        create_tutorial_db(db_path)

        conn = duckdb.connect(str(db_path), read_only=True)
        parks = conn.execute("select count(*) from parks").fetchone()[0]
        trails = conn.execute("select count(*) from trails").fetchone()[0]
        sightings = conn.execute("select count(*) from wildlife_sightings").fetchone()[0]
        stats = conn.execute("select count(*) from visitor_stats").fetchone()[0]
        conn.close()

        assert 55 <= parks <= 65
        assert 150 <= trails <= 300
        assert sightings == 1000
        assert 2000 <= stats <= 3500

    def test_deterministic(self, tmp_path: Path) -> None:
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

    def test_foreign_keys_valid(self, tmp_path: Path) -> None:
        from querido.tutorial.data import create_tutorial_db

        db_path = tmp_path / "tutorial.duckdb"
        create_tutorial_db(db_path)

        conn = duckdb.connect(str(db_path), read_only=True)

        # All trails reference valid parks
        orphan_trails = conn.execute(
            "select count(*) from trails t "
            "where not exists (select 1 from parks p where p.park_id = t.park_id)"
        ).fetchone()[0]
        assert orphan_trails == 0

        # All sightings reference valid parks
        orphan_sightings = conn.execute(
            "select count(*) from wildlife_sightings ws "
            "where not exists (select 1 from parks p where p.park_id = ws.park_id)"
        ).fetchone()[0]
        assert orphan_sightings == 0

        # Non-null trail_ids in sightings reference valid trails
        orphan_trail_refs = conn.execute(
            "select count(*) from wildlife_sightings ws "
            "where ws.trail_id is not null "
            "and not exists (select 1 from trails t where t.trail_id = ws.trail_id)"
        ).fetchone()[0]
        assert orphan_trail_refs == 0

        # Visitor stats reference valid parks
        orphan_stats = conn.execute(
            "select count(*) from visitor_stats vs "
            "where not exists (select 1 from parks p where p.park_id = vs.park_id)"
        ).fetchone()[0]
        assert orphan_stats == 0

        conn.close()

    def test_null_rates(self, tmp_path: Path) -> None:
        from querido.tutorial.data import create_tutorial_db

        db_path = tmp_path / "tutorial.duckdb"
        create_tutorial_db(db_path)

        conn = duckdb.connect(str(db_path), read_only=True)

        # Parks description: ~20% null
        desc_null = conn.execute(
            "select 100.0 * count(*) filter (where description is null) / count(*) from parks"
        ).fetchone()[0]
        assert 10 <= desc_null <= 35

        # Sighting notes: ~60% null
        notes_null = conn.execute(
            "select 100.0 * count(*) filter (where notes is null) / count(*) "
            "from wildlife_sightings"
        ).fetchone()[0]
        assert 45 <= notes_null <= 75

        # Sighting trail_id: ~30% null
        trail_null = conn.execute(
            "select 100.0 * count(*) filter (where trail_id is null) / count(*) "
            "from wildlife_sightings"
        ).fetchone()[0]
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
    def test_help(self) -> None:
        result = runner.invoke(app, ["tutorial", "--help"])
        assert result.exit_code == 0
        assert "National Parks" in result.output

    def test_list(self) -> None:
        result = runner.invoke(app, ["tutorial", "--list"])
        assert result.exit_code == 0
        assert "Welcome" in result.output
        assert "catalog" in result.output
        assert "Tutorial Complete" in result.output

    def test_shows_in_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "tutorial" in result.output
        assert "Learn" in result.output
