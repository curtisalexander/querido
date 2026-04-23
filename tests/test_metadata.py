"""Tests for qdo metadata command."""

from pathlib import Path

import pytest
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
    # CS.3 — metadata show now wraps output in the standard envelope.
    data = payload["data"]
    assert data.get("table") == "users"
    assert data.get("row_count") == 2


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
    """``metadata list`` reports the same composite score as ``metadata score``.

    Regression: this used to be a separate human-fields-only calculation, so
    ``suggest --apply`` could write ``valid_values`` without moving the number.
    """
    import json

    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    # Just written → no column descriptions / valid_values, full freshness
    # credit. Composite = 0 * 0.5 + 0 * 0.3 + 1.0 * 0.2 = 20%.
    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "list", "-c", sqlite_path],
    )
    fresh = json.loads(result.output).get("tables", [{}])[0].get("completeness", 0)
    assert fresh == pytest.approx(20.0, abs=0.5)

    # Adding column descriptions should move the score well above the
    # freshness-only baseline — the completeness field is no longer frozen.
    meta_file = tmp_path / ".qdo" / "metadata" / "test" / "users.yaml"
    meta = yaml.safe_load(meta_file.read_text())
    for col in meta.get("columns", []):
        col["description"] = f"Description for {col.get('name')}"
    with open(meta_file, "w") as f:
        yaml.dump(meta, f)

    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "list", "-c", sqlite_path],
    )
    filled = json.loads(result.output).get("tables", [{}])[0].get("completeness", 0)
    assert filled > fresh + 30  # 50-pt jump from descriptions alone


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
    sqlite_path: str,
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    result = runner.invoke(
        app,
        [
            "-f",
            "markdown",
            "metadata",
            "show",
            "-c",
            sqlite_path,
            "-t",
            "users",
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


def test_metadata_search_prefers_matching_column(sqlite_path: str, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    meta_file = tmp_path / ".qdo" / "metadata" / "test" / "users.yaml"
    meta = yaml.safe_load(meta_file.read_text())
    meta["table_description"] = "Application users and account owners"
    meta["data_owner"] = "Identity team"
    meta["columns"][1]["description"] = "Customer email address for login and notifications"
    meta["columns"][1]["pii"] = True
    with open(meta_file, "w") as f:
        yaml.dump(meta, f)

    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "search", "-c", sqlite_path, "customer email pii"],
    )
    assert result.exit_code == 0, result.output

    import json

    payload = json.loads(result.output)
    assert payload["command"] == "metadata search"
    data = payload["data"]
    assert data["results"]
    top = data["results"][0]
    assert top["kind"] == "column"
    assert top["table"] == "users"
    assert top["column"] == "name"
    assert "email" in top["matched_terms"]
    assert payload["next_steps"][0]["cmd"] == f"qdo metadata show -c '{sqlite_path}' -t users"


def test_metadata_search_empty_index_emits_envelope(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "search", "-c", "missing-conn", "customer email"],
    )
    assert result.exit_code == 0, result.output

    import json

    payload = json.loads(result.output)
    assert set(payload) == {"command", "data", "next_steps", "meta"}
    assert payload["command"] == "metadata search"
    assert payload["data"]["metadata_file_count"] == 0
    assert payload["data"]["results"] == []
    assert payload["next_steps"][0]["cmd"] == "qdo metadata list -c missing-conn"


def test_metadata_search_rich_output(sqlite_path: str, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    meta_file = tmp_path / ".qdo" / "metadata" / "test" / "users.yaml"
    meta = yaml.safe_load(meta_file.read_text())
    meta["columns"][1]["description"] = "Customer email address"
    with open(meta_file, "w") as f:
        yaml.dump(meta, f)

    result = runner.invoke(app, ["metadata", "search", "-c", sqlite_path, "customer email"])
    assert result.exit_code == 0, result.output
    assert "Metadata Search" in result.output
    assert "name" in result.output
