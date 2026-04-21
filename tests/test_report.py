"""Tests for ``qdo report table``."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_report_table_writes_html(sqlite_path: str, tmp_path: Path):
    out = tmp_path / "report.html"
    result = runner.invoke(
        app,
        ["report", "table", "-c", sqlite_path, "-t", "users", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()

    html = out.read_text(encoding="utf-8")
    # Page shell + title
    assert "<!DOCTYPE html>" in html
    assert "users — qdo report" in html
    # All five sections present
    assert "<h1>users</h1>" in html
    assert ">metadata<" in html
    assert ">schema<" in html
    assert ">quality<" in html
    assert ">related tables<" in html
    assert "Generated with qdo" in html
    # Column details
    assert 'class="mono">id<' in html
    assert 'class="mono">name<' in html
    # PK badge on id
    assert "PK</span>" in html
    # Null-rate bar SVG rendered for each column
    assert html.count("null-bar") >= 3  # css selector + per-column rects


def test_report_table_empty_metadata_panel(sqlite_path: str, tmp_path: Path):
    """Tables without metadata get an explicit empty-state, not a silent omission."""
    out = tmp_path / "report.html"
    result = runner.invoke(
        app,
        ["report", "table", "-c", sqlite_path, "-t", "users", "-o", str(out)],
        env={"QDO_METADATA_DIR": str(tmp_path / "meta")},
    )
    assert result.exit_code == 0, result.output
    html = out.read_text(encoding="utf-8")
    assert "No metadata recorded yet" in html
    assert "qdo metadata init" in html


def test_report_table_with_initialized_metadata(sqlite_path: str, tmp_path: Path):
    """Initialized metadata should render without assuming nested dict shapes."""
    env = {"QDO_METADATA_DIR": str(tmp_path / "meta")}
    init_result = runner.invoke(
        app,
        ["metadata", "init", "-c", sqlite_path, "-t", "users"],
        env=env,
    )
    assert init_result.exit_code == 0, init_result.output

    out = tmp_path / "report.html"
    result = runner.invoke(
        app,
        ["report", "table", "-c", sqlite_path, "-t", "users", "-o", str(out)],
        env=env,
    )
    assert result.exit_code == 0, result.output

    html = out.read_text(encoding="utf-8")
    assert "coverage" in html
    assert "&lt;data_owner&gt;" in html


def test_report_table_no_joins_panel_on_single_table_db(tmp_path: Path):
    """A DB with a single table still renders the joins panel (empty state)."""
    import sqlite3

    db = tmp_path / "solo.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE lonely (id INTEGER PRIMARY KEY, x TEXT)")
    conn.execute("INSERT INTO lonely VALUES (1, 'a'), (2, 'b')")
    conn.commit()
    conn.close()

    out = tmp_path / "report.html"
    result = runner.invoke(app, ["report", "table", "-c", str(db), "-t", "lonely", "-o", str(out)])
    assert result.exit_code == 0, result.output
    html = out.read_text(encoding="utf-8")
    assert ">related tables<" in html
    assert "No candidate join keys" in html


def test_report_table_quality_all_ok_shows_emerald_panel(sqlite_path: str, tmp_path: Path):
    """Clean tables should get the emerald 'all passed' panel."""
    out = tmp_path / "report.html"
    runner.invoke(app, ["report", "table", "-c", sqlite_path, "-t", "users", "-o", str(out)])
    html = out.read_text(encoding="utf-8")
    # users has 2 rows, no nulls — quality should be ok.
    assert "All " in html and "columns passed" in html


def test_report_table_footer_includes_command(sqlite_path: str, tmp_path: Path):
    out = tmp_path / "report.html"
    runner.invoke(app, ["report", "table", "-c", sqlite_path, "-t", "users", "-o", str(out)])
    html = out.read_text(encoding="utf-8")
    # Footer carries the invocation the user ran.
    assert "qdo" in html and "report" in html and "table" in html


def test_report_table_print_friendly_css(sqlite_path: str, tmp_path: Path):
    out = tmp_path / "report.html"
    runner.invoke(app, ["report", "table", "-c", sqlite_path, "-t", "users", "-o", str(out)])
    html = out.read_text(encoding="utf-8")
    assert "@media print" in html
    assert "prefers-color-scheme: dark" in html
