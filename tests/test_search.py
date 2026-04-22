"""Tests for ``qdo search`` command discovery."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_search_prefers_diff_for_compare_tables() -> None:
    result = runner.invoke(app, ["-f", "json", "search", "compare schemas between tables"])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    assert payload["command"] == "search"
    data = payload["data"]
    assert data["results"]
    assert data["results"][0]["name"] == "diff"
    assert data["results"][0]["help_command"] == "qdo diff --help"
    assert payload["next_steps"][0]["cmd"] == "qdo diff --help"


def test_search_prefers_values_for_distinct_values_intent() -> None:
    result = runner.invoke(app, ["-f", "json", "search", "show distinct values for a column"])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    matches = payload["data"]["results"]
    assert matches
    assert matches[0]["name"] == "values"
    assert "description" in matches[0]["rationale"]


def test_search_empty_results_still_emits_envelope() -> None:
    result = runner.invoke(app, ["-f", "json", "search", "zxqv mnoprst uvwxyz"])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    assert set(payload) == {"command", "data", "next_steps", "meta"}
    assert payload["command"] == "search"
    assert payload["data"]["result_count"] == 0
    assert payload["data"]["results"] == []
    assert payload["next_steps"][0]["cmd"] == "qdo overview"


def test_search_agent_format_serialization_tag() -> None:
    result = runner.invoke(app, ["-f", "agent", "search", "compare schemas"])
    assert result.exit_code == 0, result.output
    assert "command: search" in result.output
    assert "serialization:" in result.output
