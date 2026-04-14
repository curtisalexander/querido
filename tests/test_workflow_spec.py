"""Tests for ``qdo workflow spec`` (Phase 4.1)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from querido.cli.main import app
from querido.core.workflow import WORKFLOW_SCHEMA, load_examples

runner = CliRunner()


def test_spec_emits_json_schema() -> None:
    result = runner.invoke(app, ["workflow", "spec"])
    assert result.exit_code == 0, result.stdout
    schema = json.loads(result.stdout)
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert schema["title"] == "qdo workflow"
    assert "steps" in schema["required"]
    # Strict-by-default: root and all $defs forbid unknown fields.
    assert schema["additionalProperties"] is False
    for name, defn in schema["$defs"].items():
        assert defn["additionalProperties"] is False, name


def test_spec_examples_flag_emits_bundled_yaml() -> None:
    result = runner.invoke(app, ["workflow", "spec", "--examples"])
    assert result.exit_code == 0, result.stdout
    assert "# file: schema-compare.yaml" in result.stdout
    assert "# file: table-summary.yaml" in result.stdout
    assert "name: table-summary" in result.stdout
    # Multi-doc YAML separator between examples.
    assert "\n---\n" in result.stdout


def test_load_examples_returns_nonempty_yaml() -> None:
    examples = load_examples()
    expected = {
        "column-deep-dive.yaml",
        "feature-target-exploration.yaml",
        "schema-compare.yaml",
        "table-handoff.yaml",
        "table-summary.yaml",
        "wide-table-triage.yaml",
    }
    assert set(examples) == expected
    for text in examples.values():
        assert text.strip().startswith("#") or text.startswith("name:")


def test_bundled_examples_validate_against_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    yaml = pytest.importorskip("yaml")

    for filename, text in load_examples().items():
        doc = yaml.safe_load(text)
        try:
            jsonschema.validate(doc, WORKFLOW_SCHEMA)
        except jsonschema.ValidationError as exc:  # pragma: no cover - diagnostic
            raise AssertionError(f"{filename} failed schema validation: {exc.message}") from exc


def test_schema_rejects_shell_escape_in_run() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    bad = {
        "name": "bad",
        "description": "shell escape attempt",
        "version": 1,
        "steps": [{"id": "s", "run": "rm -rf /"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, WORKFLOW_SCHEMA)


def test_schema_rejects_unknown_step_field() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    bad = {
        "name": "bad",
        "description": "unknown field",
        "version": 1,
        "steps": [{"id": "s", "run": "qdo inspect", "shell": "bash"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, WORKFLOW_SCHEMA)


def test_schema_rejects_invalid_name_slug() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    bad = {
        "name": "Bad_Name",
        "description": "...",
        "version": 1,
        "steps": [{"id": "s", "run": "qdo inspect"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, WORKFLOW_SCHEMA)
