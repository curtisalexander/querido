"""End-to-end tests for --format agent (TOON + YAML envelope)."""

from __future__ import annotations

import os

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_preview_agent_renders_rows_as_toon_tabular(sqlite_path: str):
    result = runner.invoke(app, ["-f", "agent", "preview", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0, result.output
    # Envelope is rendered; top-level object wraps a TOON tabular rows array.
    assert "command: preview" in result.output
    assert "rows[2]{id,name,age}:" in result.output
    assert "1,Alice,30" in result.output
    # next_steps gets the same tabular treatment.
    assert "next_steps[" in result.output


def test_preview_qdo_format_env_agent(sqlite_path: str):
    env = {**os.environ, "QDO_FORMAT": "agent"}
    result = runner.invoke(app, ["preview", "-c", sqlite_path, "-t", "users"], env=env)
    assert result.exit_code == 0, result.output
    assert "rows[2]{id,name,age}:" in result.output


def test_catalog_agent_falls_back_to_yaml(sqlite_path: str):
    """Catalog has nested columns-inside-tables, so TOON's tabular form
    isn't applicable — we expect the YAML fallback rendering."""
    result = runner.invoke(app, ["-f", "agent", "catalog", "-c", sqlite_path])
    assert result.exit_code == 0, result.output
    # YAML fallback uses list-item syntax `- name: ...`.
    assert "command: catalog" in result.output
    assert "- name: users" in result.output


def test_agent_error_is_structured(sqlite_path: str):
    """Errors in agent mode render through the same TOON/YAML path."""
    result = runner.invoke(
        app,
        ["-f", "agent", "query", "-c", sqlite_path, "--sql", "select * from nonexistent"],
    )
    assert result.exit_code != 0
    # stderr is captured into result.output for CliRunner's default mix_stderr=True
    err = result.output
    assert "error: true" in err.lower()
    assert "code:" in err


def test_values_agent_tabular(sqlite_path: str):
    result = runner.invoke(
        app, ["-f", "agent", "values", "-c", sqlite_path, "-t", "users", "-C", "name"]
    )
    assert result.exit_code == 0, result.output
    assert "command: values" in result.output
    # values payload has a tabular array of {value, count}
    assert "{value,count}:" in result.output
