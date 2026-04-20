import json

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_template_sqlite(sqlite_path: str):
    result = runner.invoke(app, ["template", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "id" in result.output
    assert "name" in result.output
    assert "age" in result.output
    # Rich may truncate long strings; check partial matches
    assert "<bu" in result.output  # <business_definition> truncated
    assert "<dat" in result.output  # <data_owner> truncated
    assert "<no" in result.output  # <notes> truncated


def test_template_duckdb(duckdb_path: str):
    result = runner.invoke(app, ["template", "--connection", duckdb_path, "--table", "users"])
    assert result.exit_code == 0
    assert "id" in result.output
    assert "name" in result.output
    assert "age" in result.output


def test_template_shows_row_count(sqlite_path: str):
    result = runner.invoke(app, ["template", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "2" in result.output


def test_template_shows_sample_values(sqlite_path: str):
    """Verify sample values appear — use JSON format to avoid Rich truncation."""
    result = runner.invoke(app, ["--format", "json", "template", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    name_col = next(c for c in data["columns"] if c["name"] == "name")
    assert "Alice" in name_col["sample_values"]


def test_template_no_sample_values(sqlite_path: str):
    result = runner.invoke(
        app,
        ["template", "--connection", sqlite_path, "--table", "users", "--sample-values", "0"],
    )
    assert result.exit_code == 0
    assert "id" in result.output
    # With 0 sample values, Alice shouldn't appear in the sample column
    # (though it may appear elsewhere in the output like distinct count)


def test_template_json(sqlite_path: str):
    result = runner.invoke(app, ["--format", "json", "template", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["command"] == "template"
    data = payload["data"]
    assert data["table"] == "users"
    assert data["row_count"] == 2
    assert len(data["columns"]) == 3
    col_names = [c["name"] for c in data["columns"]]
    assert "id" in col_names
    assert "name" in col_names
    assert "age" in col_names
    # Check that profile stats are present
    name_col = next(c for c in data["columns"] if c["name"] == "name")
    assert name_col["distinct_count"] == 2
    # next_steps should include a metadata-authoring nudge.
    assert any("metadata init" in s["cmd"] for s in payload["next_steps"])


def test_template_csv(sqlite_path: str):
    result = runner.invoke(app, ["--format", "csv", "template", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert len(lines) == 4  # header + 3 columns
    assert "column" in lines[0]
    assert "business_definition" in lines[0]
    assert "data_owner" in lines[0]
    assert "notes" in lines[0]


def test_template_markdown(sqlite_path: str):
    result = runner.invoke(
        app, ["--format", "markdown", "template", "-c", sqlite_path, "-t", "users"]
    )
    assert result.exit_code == 0
    assert "## users" in result.output
    assert "Business Definition" in result.output
    assert "Data Owner" in result.output
    assert "Row count: 2" in result.output


def test_template_duckdb_with_comments(duckdb_with_comments_path: str):
    result = runner.invoke(
        app,
        ["--format", "json", "template", "-c", duckdb_with_comments_path, "-t", "users"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["table_comment"] == "Application user accounts"
    name_col = next(c for c in data["columns"] if c["name"] == "name")
    assert name_col["comment"] == "Full legal name"


def test_template_yaml_has_semantic_model(sqlite_path: str):
    result = runner.invoke(app, ["--format", "yaml", "template", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0
    assert "name: users_semantic_model" in result.output
    assert "tables:" in result.output
    assert "dimensions:" in result.output
    assert "measures:" in result.output


def test_template_yaml_has_sample_values(sqlite_path: str):
    result = runner.invoke(
        app,
        ["--format", "yaml", "template", "-c", sqlite_path, "-t", "users", "--sample-values", "3"],
    )
    assert result.exit_code == 0
    assert "sample_values:" in result.output
    assert "Alice" in result.output


def test_template_yaml_structured_base_table():
    """Qualified table names should produce structured base_table."""
    from querido.core.semantic import build_semantic_yaml

    columns = [{"name": "id", "type": "INTEGER", "comment": None}]
    yaml_str = build_semantic_yaml("MY_DB.MY_SCHEMA.MY_TABLE", columns, None)
    assert "database: MY_DB" in yaml_str
    assert "schema: MY_SCHEMA" in yaml_str
    assert "table: MY_TABLE" in yaml_str


def test_template_yaml_bare_table_name():
    """Bare table names should use flat base_table."""
    from querido.core.semantic import build_semantic_yaml

    columns = [{"name": "id", "type": "INTEGER", "comment": None}]
    yaml_str = build_semantic_yaml("users", columns, None)
    assert "base_table: users" in yaml_str
    assert "database:" not in yaml_str


def test_template_yaml_smart_aggregation():
    """Measure columns with rate/pct keywords should get avg aggregation."""
    from querido.core.semantic import build_semantic_yaml

    columns = [
        {"name": "click_rate", "type": "FLOAT", "comment": None},
        {"name": "revenue", "type": "FLOAT", "comment": None},
    ]
    yaml_str = build_semantic_yaml("metrics", columns, None)
    assert "default_aggregation: avg" in yaml_str
    assert "default_aggregation: sum" in yaml_str


def test_template_markdown_detailed_style(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "--format",
            "markdown",
            "template",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "--style",
            "detailed",
        ],
    )
    assert result.exit_code == 0
    assert "### `id`" in result.output
    assert "### `name`" in result.output
    assert "### `age`" in result.output
    assert "**Business definition**: _fill in_" in result.output
    assert "**Data owner**: _fill in_" in result.output
    assert "**Row count**:" in result.output


def test_template_markdown_table_style(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "--format",
            "markdown",
            "template",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "--style",
            "table",
        ],
    )
    assert result.exit_code == 0
    assert "## users" in result.output
    assert "Business Definition" in result.output
    assert "Row count: 2" in result.output
    # Should NOT have per-column headings
    assert "### `id`" not in result.output


def test_template_nonexistent_table(sqlite_path: str):
    result = runner.invoke(
        app, ["template", "--connection", sqlite_path, "--table", "nonexistent"]
    )
    assert result.exit_code != 0
