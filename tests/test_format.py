"""Tests for --format flag (markdown, json, csv) on inspect, preview, profile."""

import json

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


# -- inspect -------------------------------------------------------------------


def test_inspect_json(sqlite_path: str):
    result = runner.invoke(app, ["--format", "json", "inspect", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["table"] == "users"
    assert data["row_count"] == 2
    assert len(data["columns"]) == 3


def test_inspect_csv(sqlite_path: str):
    result = runner.invoke(app, ["--format", "csv", "inspect", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert lines[0].strip() == "column,type,nullable,default,primary_key"
    assert len(lines) == 4  # header + 3 columns


def test_inspect_markdown(sqlite_path: str):
    result = runner.invoke(
        app, ["--format", "markdown", "inspect", "-c", sqlite_path, "-t", "users"]
    )
    assert result.exit_code == 0
    assert "## users" in result.output
    assert "| Column |" in result.output
    assert "Row count:" in result.output


# -- preview -------------------------------------------------------------------


def test_preview_json(sqlite_path: str):
    result = runner.invoke(app, ["--format", "json", "preview", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[0]["name"] == "Alice"


def test_preview_csv(sqlite_path: str):
    result = runner.invoke(app, ["--format", "csv", "preview", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert "id" in lines[0]
    assert len(lines) == 3  # header + 2 rows


def test_preview_markdown(sqlite_path: str):
    result = runner.invoke(
        app, ["--format", "markdown", "preview", "-c", sqlite_path, "-t", "users"]
    )
    assert result.exit_code == 0
    assert "## Preview:" in result.output
    assert "| id |" in result.output


# -- profile -------------------------------------------------------------------


def test_profile_json(sqlite_path: str):
    result = runner.invoke(app, ["--format", "json", "profile", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["table"] == "users"
    assert data["row_count"] == 2
    assert len(data["columns"]) > 0


def test_profile_csv(sqlite_path: str):
    result = runner.invoke(app, ["--format", "csv", "profile", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert "column_name" in lines[0]


def test_profile_markdown(sqlite_path: str):
    result = runner.invoke(
        app, ["--format", "markdown", "profile", "-c", sqlite_path, "-t", "users"]
    )
    assert result.exit_code == 0
    assert "## Profile:" in result.output
    assert "Total rows:" in result.output


# -- invalid format ------------------------------------------------------------


def test_invalid_format(sqlite_path: str):
    result = runner.invoke(app, ["--format", "xml", "inspect", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code != 0
