"""Tests for agent ergonomics: QDO_FORMAT env var and structured errors."""

import json
import os

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_qdo_format_env_sets_default(sqlite_path: str):
    """QDO_FORMAT=json should make output JSON without --format flag."""
    env = {**os.environ, "QDO_FORMAT": "json"}
    result = runner.invoke(
        app,
        ["preview", "-c", sqlite_path, "-t", "users"],
        env=env,
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "rows" in payload


def test_qdo_format_explicit_flag_overrides_env(sqlite_path: str):
    """Explicit --format should override QDO_FORMAT env var."""
    env = {**os.environ, "QDO_FORMAT": "json"}
    result = runner.invoke(
        app,
        ["-f", "csv", "preview", "-c", sqlite_path, "-t", "users"],
        env=env,
    )
    assert result.exit_code == 0
    # CSV output, not JSON
    assert "id,name,age" in result.output


def test_qdo_format_env_invalid_falls_back_to_rich(sqlite_path: str):
    """Invalid QDO_FORMAT value should fall back to rich."""
    env = {**os.environ, "QDO_FORMAT": "badvalue"}
    result = runner.invoke(
        app,
        ["preview", "-c", sqlite_path, "-t", "users"],
        env=env,
    )
    assert result.exit_code == 0
    # Rich output contains table formatting characters
    assert "Alice" in result.output


def test_qdo_format_env_csv(sqlite_path: str):
    """QDO_FORMAT=csv should produce CSV output."""
    env = {**os.environ, "QDO_FORMAT": "csv"}
    result = runner.invoke(
        app,
        ["inspect", "-c", sqlite_path, "-t", "users"],
        env=env,
    )
    assert result.exit_code == 0
    assert "name" in result.output
    # CSV has commas
    assert "," in result.output


def test_qdo_format_env_markdown(sqlite_path: str):
    """QDO_FORMAT=markdown should produce markdown."""
    env = {**os.environ, "QDO_FORMAT": "markdown"}
    result = runner.invoke(
        app,
        ["inspect", "-c", sqlite_path, "-t", "users"],
        env=env,
    )
    assert result.exit_code == 0
    assert "| Column" in result.output


def test_qdo_format_env_case_insensitive(sqlite_path: str):
    """QDO_FORMAT should be case-insensitive."""
    env = {**os.environ, "QDO_FORMAT": "JSON"}
    result = runner.invoke(
        app,
        ["preview", "-c", sqlite_path, "-t", "users"],
        env=env,
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "rows" in payload


def test_json_error_on_bad_table(sqlite_path: str):
    """When format is JSON, errors should be structured JSON on stderr."""
    env = {**os.environ, "QDO_FORMAT": "json"}
    result = runner.invoke(
        app,
        ["inspect", "-c", sqlite_path, "-t", "nonexistent"],
        env=env,
    )
    assert result.exit_code != 0


def test_json_error_on_sql_error(sqlite_path: str):
    """SQL errors with --format json should emit structured error."""
    result = runner.invoke(
        app,
        ["-f", "json", "query", "-c", sqlite_path, "--sql", "INVALID SQL HERE"],
    )
    assert result.exit_code == 1
