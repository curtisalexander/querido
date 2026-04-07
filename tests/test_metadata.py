"""Tests for qdo metadata command."""

from pathlib import Path

import yaml
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_metadata_init(sqlite_path: str, tmp_path: Path, monkeypatch):
    """Init creates a YAML file with correct structure."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["metadata", "init", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code == 0, result.output

    # File should exist — connection name is sanitized (stem of path)
    meta_file = tmp_path / ".qdo" / "metadata" / "test" / "users.yaml"
    assert meta_file.exists()

    meta = yaml.safe_load(meta_file.read_text())
    assert meta.get("table") == "users"
    assert meta.get("row_count") == 2
    assert len(meta.get("columns", [])) == 3

    # Check placeholder human fields
    assert meta.get("table_description") == "<description>"
    assert meta.get("data_owner") == "<data_owner>"


def test_metadata_init_force(sqlite_path: str, tmp_path: Path, monkeypatch):
    """Init with --force overwrites existing file."""
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])
    result = runner.invoke(
        app,
        ["metadata", "init", "-c", sqlite_path, "-t", "users", "--force"],
    )
    assert result.exit_code == 0


def test_metadata_init_no_force_errors(sqlite_path: str, tmp_path: Path, monkeypatch):
    """Init without --force errors if file exists."""
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])
    result = runner.invoke(
        app,
        ["metadata", "init", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code == 1


def test_metadata_show(sqlite_path: str, tmp_path: Path, monkeypatch):
    """Show reads back stored metadata."""
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "show", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload.get("table") == "users"
    assert payload.get("row_count") == 2


def test_metadata_show_not_found(sqlite_path: str, tmp_path: Path, monkeypatch):
    """Show errors when metadata doesn't exist."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["metadata", "show", "-c", sqlite_path, "-t", "nonexistent"],
    )
    assert result.exit_code != 0


def test_metadata_list(sqlite_path: str, tmp_path: Path, monkeypatch):
    """List shows all metadata files for a connection."""
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "list", "-c", sqlite_path],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    tables = payload.get("tables", [])
    assert len(tables) == 1
    assert tables[0].get("table") == "users"
    assert "completeness" in tables[0]


def test_metadata_list_empty(tmp_path: Path, monkeypatch):
    """List returns empty when no metadata exists."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "list", "-c", "no-such-conn"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload.get("tables") == []


def test_metadata_refresh(sqlite_path: str, tmp_path: Path, monkeypatch):
    """Refresh updates machine fields but preserves human fields."""
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    # Simulate filling in human fields
    meta_file = tmp_path / ".qdo" / "metadata" / "test" / "users.yaml"
    meta = yaml.safe_load(meta_file.read_text())
    meta["table_description"] = "My user table"
    meta["data_owner"] = "Team A"
    meta["columns"][0]["description"] = "Primary key"
    with open(meta_file, "w") as f:
        yaml.dump(meta, f)

    # Refresh
    result = runner.invoke(
        app,
        ["metadata", "refresh", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code == 0

    # Human fields preserved
    refreshed = yaml.safe_load(meta_file.read_text())
    assert refreshed.get("table_description") == "My user table"
    assert refreshed.get("data_owner") == "Team A"
    assert refreshed.get("columns", [{}])[0].get("description") == "Primary key"
    # Machine fields updated
    assert refreshed.get("row_count") == 2


def test_metadata_refresh_not_found(sqlite_path: str, tmp_path: Path, monkeypatch):
    """Refresh errors when no metadata exists."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["metadata", "refresh", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code == 1


def test_metadata_completeness(sqlite_path: str, tmp_path: Path, monkeypatch):
    """Completeness reflects filled human fields."""
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    # Initially 0% — all placeholders
    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "list", "-c", sqlite_path],
    )
    import json

    payload = json.loads(result.output)
    assert payload.get("tables", [{}])[0].get("completeness") == 0.0

    # Fill in some fields
    meta_file = tmp_path / ".qdo" / "metadata" / "test" / "users.yaml"
    meta = yaml.safe_load(meta_file.read_text())
    meta["table_description"] = "Filled in"
    meta["data_owner"] = "Filled in"
    with open(meta_file, "w") as f:
        yaml.dump(meta, f)

    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "list", "-c", sqlite_path],
    )
    payload = json.loads(result.output)
    completeness = payload.get("tables", [{}])[0].get("completeness", 0)
    assert completeness > 0


def test_metadata_show_format_csv(sqlite_path: str, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    result = runner.invoke(
        app,
        ["-f", "csv", "metadata", "show", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code == 0
    assert "name" in result.output


def test_metadata_show_format_markdown(
    sqlite_path: str, tmp_path: Path, monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    result = runner.invoke(
        app,
        [
            "-f", "markdown", "metadata", "show",
            "-c", sqlite_path, "-t", "users",
        ],
    )
    assert result.exit_code == 0
    assert "## users" in result.output


def test_metadata_env_override(sqlite_path: str, tmp_path: Path, monkeypatch):
    """QDO_METADATA_DIR env var overrides default location."""
    custom_dir = str(tmp_path / "custom_meta")
    monkeypatch.setenv("QDO_METADATA_DIR", custom_dir)
    result = runner.invoke(
        app,
        ["metadata", "init", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code == 0
    # Connection path is sanitized to stem: /path/to/test.db → "test"
    assert (Path(custom_dir) / "test" / "users.yaml").exists()
