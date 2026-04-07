"""Tests for qdo export command."""

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_export_csv_to_file(sqlite_path: str, tmp_path: Path):
    out = str(tmp_path / "out.csv")
    result = runner.invoke(
        app,
        ["export", "-c", sqlite_path, "-t", "users", "-o", out],
    )
    assert result.exit_code == 0
    content = Path(out).read_text()
    assert "id,name,age" in content
    assert "Alice" in content
    assert "Bob" in content


def test_export_tsv_to_file(sqlite_path: str, tmp_path: Path):
    out = str(tmp_path / "out.tsv")
    result = runner.invoke(
        app,
        ["export", "-c", sqlite_path, "-t", "users", "-o", out, "-e", "tsv"],
    )
    assert result.exit_code == 0
    content = Path(out).read_text()
    assert "id\tname\tage" in content
    assert "Alice" in content


def test_export_json_to_file(sqlite_path: str, tmp_path: Path):
    out = str(tmp_path / "out.json")
    result = runner.invoke(
        app,
        ["export", "-c", sqlite_path, "-t", "users", "-o", out, "-e", "json"],
    )
    assert result.exit_code == 0
    data = json.loads(Path(out).read_text())
    assert len(data) == 2
    assert data[0].get("name") == "Alice"


def test_export_jsonl_to_file(sqlite_path: str, tmp_path: Path):
    out = str(tmp_path / "out.jsonl")
    result = runner.invoke(
        app,
        [
            "export",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "-o",
            out,
            "-e",
            "jsonl",
        ],
    )
    assert result.exit_code == 0
    lines = Path(out).read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]).get("name") == "Alice"


def test_export_to_stdout(sqlite_path: str):
    """Without --output, should print to stdout."""
    result = runner.invoke(
        app,
        ["export", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code == 0
    assert "Alice" in result.output


def test_export_with_sql(sqlite_path: str, tmp_path: Path):
    out = str(tmp_path / "out.csv")
    result = runner.invoke(
        app,
        [
            "export",
            "-c",
            sqlite_path,
            "--sql",
            "select name from users where age > 26",
            "-o",
            out,
        ],
    )
    assert result.exit_code == 0
    content = Path(out).read_text()
    assert "Alice" in content
    assert "Bob" not in content


def test_export_with_filter(sqlite_path: str, tmp_path: Path):
    out = str(tmp_path / "out.csv")
    result = runner.invoke(
        app,
        [
            "export",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "-o",
            out,
            "--filter",
            "age > 26",
        ],
    )
    assert result.exit_code == 0
    content = Path(out).read_text()
    assert "Alice" in content
    assert "Bob" not in content


def test_export_with_limit(sqlite_path: str, tmp_path: Path):
    out = str(tmp_path / "out.csv")
    result = runner.invoke(
        app,
        [
            "export",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "-o",
            out,
            "--limit",
            "1",
        ],
    )
    assert result.exit_code == 0
    content = Path(out).read_text()
    lines = [ln for ln in content.splitlines() if ln.strip()]
    assert len(lines) == 2  # header + 1 row


def test_export_with_columns(sqlite_path: str, tmp_path: Path):
    out = str(tmp_path / "out.csv")
    result = runner.invoke(
        app,
        [
            "export",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "-o",
            out,
            "--columns",
            "name,age",
        ],
    )
    assert result.exit_code == 0
    content = Path(out).read_text()
    assert "name,age" in content
    assert "id" not in content.split("\n")[0]


def test_export_no_table_or_sql(sqlite_path: str):
    result = runner.invoke(
        app,
        ["export", "-c", sqlite_path, "-o", "out.csv"],
    )
    assert result.exit_code != 0
    assert "Must provide" in result.output


def test_export_invalid_format(sqlite_path: str, tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "export",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "-o",
            str(tmp_path / "x"),
            "-e",
            "badformat",
        ],
    )
    assert result.exit_code != 0


def test_export_clipboard(sqlite_path: str):
    """--clipboard should export TSV and call copy_to_clipboard."""
    with patch("querido.core.export.copy_to_clipboard") as mock_copy:
        result = runner.invoke(
            app,
            ["export", "-c", sqlite_path, "-t", "users", "--clipboard"],
        )
        assert result.exit_code == 0
        mock_copy.assert_called_once()
        content = mock_copy.call_args[0][0]
        assert "id\tname\tage" in content
        assert "Alice" in content


def test_export_duckdb(duckdb_path: str, tmp_path: Path):
    out = str(tmp_path / "out.csv")
    result = runner.invoke(
        app,
        ["export", "-c", duckdb_path, "-t", "users", "-o", out],
    )
    assert result.exit_code == 0
    content = Path(out).read_text()
    assert "Alice" in content


def test_export_reports_size(sqlite_path: str, tmp_path: Path):
    out = str(tmp_path / "out.csv")
    result = runner.invoke(
        app,
        ["export", "-c", sqlite_path, "-t", "users", "-o", out],
    )
    assert result.exit_code == 0
    assert "bytes" in result.output.lower()
