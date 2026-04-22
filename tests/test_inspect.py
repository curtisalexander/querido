import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_inspect_sqlite(sqlite_path: str):
    result = runner.invoke(app, ["inspect", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "id" in result.output
    assert "name" in result.output
    assert "age" in result.output


def test_inspect_duckdb(duckdb_path: str):
    result = runner.invoke(app, ["inspect", "--connection", duckdb_path, "--table", "users"])
    assert result.exit_code == 0
    assert "id" in result.output
    assert "name" in result.output
    assert "age" in result.output


# -- verbose / comments (F2) --------------------------------------------------


def test_inspect_verbose_duckdb_shows_comments(duckdb_with_comments_path: str):
    result = runner.invoke(
        app,
        ["inspect", "--connection", duckdb_with_comments_path, "--table", "users", "--verbose"],
    )
    assert result.exit_code == 0
    assert "Comment" in result.output
    assert "Full legal name" in result.output
    assert "Age in years" in result.output
    assert "Application user accounts" in result.output


def test_inspect_verbose_sqlite_no_comments(sqlite_path: str):
    """SQLite has no comment support — verbose should still work without errors."""
    result = runner.invoke(
        app, ["inspect", "--connection", sqlite_path, "--table", "users", "--verbose"]
    )
    assert result.exit_code == 0
    assert "Comment" in result.output  # column header still shown


def test_inspect_verbose_json_includes_comments(duckdb_with_comments_path: str):
    import json

    result = runner.invoke(
        app, ["--format", "json", "inspect", "-c", duckdb_with_comments_path, "-t", "users", "-v"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["table_comment"] == "Application user accounts"
    comments = {c["name"]: c["comment"] for c in data["columns"]}
    assert comments["name"] == "Full legal name"
    assert comments["age"] == "Age in years"
    assert comments["id"] is None


def test_inspect_verbose_csv_includes_comment_column(duckdb_with_comments_path: str):
    result = runner.invoke(
        app, ["--format", "csv", "inspect", "-c", duckdb_with_comments_path, "-t", "users", "-v"]
    )
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert "comment" in lines[0]
    assert "Full legal name" in result.output


def test_inspect_verbose_markdown_includes_comments(duckdb_with_comments_path: str):
    result = runner.invoke(
        app,
        ["--format", "markdown", "inspect", "-c", duckdb_with_comments_path, "-t", "users", "-v"],
    )
    assert result.exit_code == 0
    assert "Comment" in result.output
    assert "Application user accounts" in result.output
    assert "Full legal name" in result.output


def test_inspect_empty_table(tmp_path: Path):
    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE empty_t (id INTEGER PRIMARY KEY, name TEXT NOT NULL, score REAL)")
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["inspect", "-c", db_path, "-t", "empty_t"])
    assert result.exit_code == 0
    assert "id" in result.output
    assert "name" in result.output
    assert "score" in result.output
    assert "0" in result.output


def test_print_inspect_rich_summary() -> None:
    """Rich inspect output should summarize schema shape before the detail table."""
    from rich.console import Console

    from querido.output.console import print_inspect

    console = Console(record=True, width=120)
    print_inspect(
        "users",
        [
            {
                "name": "id",
                "type": "INTEGER",
                "nullable": False,
                "default": None,
                "primary_key": True,
            },
            {
                "name": "email",
                "type": "TEXT",
                "nullable": True,
                "default": None,
                "primary_key": False,
            },
        ],
        row_count=2,
        console=console,
    )
    text = console.export_text()
    assert "Inspect Summary" in text
    assert "2 columns" in text
    assert "1 primary keys" in text
    assert "1 nullable" in text
    assert "Column Detail" in text


def test_print_inspect_rich_verbose_comment_note() -> None:
    """Verbose inspect output should surface the table comment in the summary and footer."""
    from rich.console import Console

    from querido.output.console import print_inspect

    console = Console(record=True, width=120)
    print_inspect(
        "users",
        [
            {
                "name": "id",
                "type": "INTEGER",
                "nullable": False,
                "default": None,
                "primary_key": True,
                "comment": None,
            }
        ],
        row_count=2,
        console=console,
        verbose=True,
        table_comment="Application user accounts",
    )
    text = console.export_text()
    assert "table comment" in text.lower()
    assert "Application user accounts" in text
