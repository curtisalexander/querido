import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_preview_sqlite(sqlite_path: str):
    result = runner.invoke(app, ["preview", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_preview_duckdb(duckdb_path: str):
    result = runner.invoke(app, ["preview", "--connection", duckdb_path, "--table", "users"])
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_preview_respects_rows_flag(sqlite_path: str):
    result = runner.invoke(
        app, ["preview", "--connection", sqlite_path, "--table", "users", "--rows", "1"]
    )
    assert result.exit_code == 0
    assert "1 row(s)" in result.output


def test_preview_default_limit_shown(sqlite_path: str):
    result = runner.invoke(app, ["preview", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "limit 20" in result.output


def test_preview_duckdb_with_rows_flag(duckdb_path: str):
    result = runner.invoke(
        app, ["preview", "--connection", duckdb_path, "--table", "users", "--rows", "1"]
    )
    assert result.exit_code == 0
    assert "1 row(s)" in result.output


def test_preview_empty_table(tmp_path: Path):
    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE empty_t (id INTEGER PRIMARY KEY, name TEXT NOT NULL, score REAL)")
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["preview", "-c", db_path, "-t", "empty_t"])
    assert result.exit_code == 0
    assert "No rows found" in result.output


def test_print_preview_rich_summary() -> None:
    """Rich preview output should summarize shown rows and limit before the table."""
    from rich.console import Console

    from querido.output.console import print_preview

    console = Console(record=True, width=120)
    print_preview(
        "users",
        [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        limit=20,
        console=console,
    )
    text = console.export_text()
    assert "Preview Summary" in text
    assert "2 shown" in text
    assert "limit 20" in text
    assert "2 columns" in text
    assert "Preview Rows" in text
