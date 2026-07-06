"""Tests for qdo metadata command."""

import json
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


def test_written_metadata_carries_schema_version(sqlite_path: str, tmp_path: Path, monkeypatch):
    # Failure mode: on-disk metadata had no version marker, so a future qdo
    # that changes the document shape would have nothing to migrate on.
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0, result.output

    meta_file = tmp_path / ".qdo" / "metadata" / "test" / "users.yaml"
    text = meta_file.read_text()
    meta = yaml.safe_load(text)
    assert meta.get("schema_version") == 1
    # Stamped first so it's the first thing a human sees in the file.
    assert text.lstrip().startswith("schema_version:")


def test_read_table_doc_refuses_newer_schema_version(tmp_path: Path):
    # Failure mode: a document written by a future qdo (schema_version 2+)
    # would be read as version 1 and silently misinterpreted.
    from querido.core.metadata import read_table_doc

    doc = tmp_path / "orders.yaml"
    doc.write_text("schema_version: 99\ntable: orders\n")
    with pytest.raises(ValueError, match="schema_version 99"):
        read_table_doc(doc)


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


def test_metadata_init_emits_envelope(sqlite_path: str, tmp_path: Path, monkeypatch):
    """Under -f json, init must emit a parseable envelope (not silence) with the path."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "init", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload) == {"command", "data", "next_steps", "meta"}
    assert payload.get("command") == "metadata init"
    data = payload.get("data")
    assert data.get("created") is True
    assert Path(data.get("path")).exists()
    assert payload.get("meta", {}).get("table") == "users"
    # init nudges toward deterministic auto-fill
    assert any("metadata suggest" in s.get("cmd", "") for s in payload.get("next_steps"))


def test_metadata_init_resolves_table_case(sqlite_path: str, tmp_path: Path, monkeypatch):
    """init goes through resolve_table — mixed-case names resolve to the canonical table."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["metadata", "init", "-c", sqlite_path, "-t", "USERS"],
    )
    assert result.exit_code == 0, result.output
    meta_file = tmp_path / ".qdo" / "metadata" / "test" / "users.yaml"
    assert meta_file.exists()


def test_metadata_init_table_not_found_structured(sqlite_path: str, tmp_path: Path, monkeypatch):
    """A mistyped table yields a structured TABLE_NOT_FOUND error with suggestions."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "init", "-c", sqlite_path, "-t", "userz"],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload.get("error") is True
    assert payload.get("code") == "TABLE_NOT_FOUND"
    assert isinstance(payload.get("try_next"), list)


def test_metadata_show(sqlite_path: str, tmp_path: Path, monkeypatch):
    """Show reads back stored metadata."""
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "show", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code == 0
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


def test_metadata_refresh_emits_envelope(sqlite_path: str, tmp_path: Path, monkeypatch):
    """Under -f json, refresh must emit a parseable envelope (not silence) with the path."""
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])

    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "refresh", "-c", sqlite_path, "-t", "users"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload) == {"command", "data", "next_steps", "meta"}
    assert payload.get("command") == "metadata refresh"
    data = payload.get("data")
    assert Path(data.get("path")).exists()
    assert data.get("row_count") == 2
    assert payload.get("meta", {}).get("table") == "users"


def test_metadata_refresh_table_not_found_structured(
    sqlite_path: str, tmp_path: Path, monkeypatch
):
    """A mistyped table on refresh yields a structured TABLE_NOT_FOUND error."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["-f", "json", "metadata", "refresh", "-c", sqlite_path, "-t", "userz"],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload.get("error") is True
    assert payload.get("code") == "TABLE_NOT_FOUND"


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
