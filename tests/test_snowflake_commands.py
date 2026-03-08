"""Tests for Snowflake-specific CLI commands (F8: semantic, F9: lineage)."""

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_path(tmp_path: Path) -> str:
    """SQLite DB for testing non-Snowflake rejection."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE orders ("
        "order_id INTEGER PRIMARY KEY, "
        "customer_name TEXT, "
        "total REAL, "
        "order_date TEXT, "
        "status TEXT)"
    )
    conn.execute("INSERT INTO orders VALUES (1, 'Alice', 99.99, '2024-01-15', 'shipped')")
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# F8: Semantic YAML generation — unit tests
# ---------------------------------------------------------------------------


class TestSemanticYamlGeneration:
    def test_build_semantic_yaml_basic(self):
        from querido.cli.snowflake import _build_semantic_yaml

        columns = [
            {"name": "ORDER_ID", "type": "NUMBER", "comment": "Primary key"},
            {"name": "CUSTOMER_NAME", "type": "VARCHAR", "comment": None},
            {"name": "TOTAL", "type": "FLOAT", "comment": "Order total"},
            {"name": "ORDER_DATE", "type": "DATE", "comment": "When placed"},
            {"name": "STATUS", "type": "VARCHAR", "comment": "Current status"},
        ]
        yaml_str = _build_semantic_yaml("ORDERS", columns, "Orders table")

        assert "name: orders_semantic_model" in yaml_str
        assert "description: Orders table" in yaml_str
        assert "base_table: ORDERS" in yaml_str
        assert "dimensions:" in yaml_str
        assert "measures:" in yaml_str
        assert "time_dimensions:" in yaml_str

    def test_classify_id_as_dimension(self):
        from querido.cli.snowflake import _classify_semantic_column

        col = {"name": "ORDER_ID", "type": "NUMBER"}
        assert _classify_semantic_column(col) == "dimension"

    def test_classify_numeric_as_measure(self):
        from querido.cli.snowflake import _classify_semantic_column

        col = {"name": "TOTAL", "type": "FLOAT"}
        assert _classify_semantic_column(col) == "measure"

    def test_classify_date_as_time_dimension(self):
        from querido.cli.snowflake import _classify_semantic_column

        col = {"name": "ORDER_DATE", "type": "DATE"}
        assert _classify_semantic_column(col) == "time_dimension"

    def test_classify_timestamp_as_time_dimension(self):
        from querido.cli.snowflake import _classify_semantic_column

        col = {"name": "CREATED_AT", "type": "TIMESTAMP_NTZ"}
        assert _classify_semantic_column(col) == "time_dimension"

    def test_classify_string_as_dimension(self):
        from querido.cli.snowflake import _classify_semantic_column

        col = {"name": "STATUS", "type": "VARCHAR"}
        assert _classify_semantic_column(col) == "dimension"

    def test_yaml_includes_comments_as_descriptions(self):
        from querido.cli.snowflake import _build_semantic_yaml

        columns = [
            {"name": "REVENUE", "type": "FLOAT", "comment": "Total revenue"},
        ]
        yaml_str = _build_semantic_yaml("SALES", columns, None)
        assert "description: Total revenue" in yaml_str

    def test_yaml_placeholder_when_no_comment(self):
        from querido.cli.snowflake import _build_semantic_yaml

        columns = [
            {"name": "STATUS", "type": "VARCHAR", "comment": None},
        ]
        yaml_str = _build_semantic_yaml("ORDERS", columns, None)
        assert "<description>" in yaml_str

    def test_yaml_measures_have_default_aggregation(self):
        from querido.cli.snowflake import _build_semantic_yaml

        columns = [
            {"name": "AMOUNT", "type": "FLOAT", "comment": None},
        ]
        yaml_str = _build_semantic_yaml("SALES", columns, None)
        assert "default_aggregation: sum" in yaml_str

    def test_yaml_dimensions_have_synonyms_placeholder(self):
        from querido.cli.snowflake import _build_semantic_yaml

        columns = [
            {"name": "STATUS", "type": "VARCHAR", "comment": None},
        ]
        yaml_str = _build_semantic_yaml("ORDERS", columns, None)
        assert "synonyms:" in yaml_str
        assert "<synonym>" in yaml_str


# ---------------------------------------------------------------------------
# F8: Semantic CLI — non-Snowflake rejection
# ---------------------------------------------------------------------------


class TestSemanticCLI:
    def test_semantic_rejects_sqlite(self, sqlite_path: str):
        result = runner.invoke(app, ["snowflake", "semantic", "-t", "orders", "-c", sqlite_path])
        assert result.exit_code != 0
        assert "Snowflake" in result.output

    def test_semantic_rejects_duckdb(self, tmp_path: Path):
        import duckdb

        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.close()

        result = runner.invoke(app, ["snowflake", "semantic", "-t", "t", "-c", db_path])
        assert result.exit_code != 0
        assert "Snowflake" in result.output


# ---------------------------------------------------------------------------
# F9: Lineage CLI — non-Snowflake rejection
# ---------------------------------------------------------------------------


class TestLineageCLI:
    def test_lineage_rejects_sqlite(self, sqlite_path: str):
        result = runner.invoke(
            app,
            ["snowflake", "lineage", "--object", "db.schema.orders", "-c", sqlite_path],
        )
        assert result.exit_code != 0
        assert "Snowflake" in result.output

    def test_lineage_invalid_direction(self, sqlite_path: str):
        result = runner.invoke(
            app,
            [
                "snowflake",
                "lineage",
                "--object",
                "db.schema.orders",
                "-c",
                sqlite_path,
                "-d",
                "sideways",
            ],
        )
        assert result.exit_code != 0

    def test_lineage_invalid_domain(self, sqlite_path: str):
        result = runner.invoke(
            app,
            [
                "snowflake",
                "lineage",
                "--object",
                "db.schema.orders",
                "-c",
                sqlite_path,
                "--domain",
                "database",
            ],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# F9: Lineage output — unit tests
# ---------------------------------------------------------------------------


class TestLineageOutput:
    def test_format_snowflake_lineage_json_empty(self):
        from querido.output.formats import format_snowflake_lineage

        result = {
            "object": "db.schema.t",
            "direction": "downstream",
            "domain": "table",
            "depth": 5,
            "entries": [],
        }
        output = format_snowflake_lineage(result, "json")
        data = json.loads(output)
        assert data["entries"] == []
        assert data["object"] == "db.schema.t"

    def test_format_snowflake_lineage_json_with_data(self):
        from querido.output.formats import format_snowflake_lineage

        result = {
            "object": "db.schema.t",
            "direction": "downstream",
            "domain": "table",
            "depth": 5,
            "entries": [
                {"SOURCE": "db.schema.t", "TARGET": "db.schema.v"},
            ],
        }
        output = format_snowflake_lineage(result, "json")
        data = json.loads(output)
        assert len(data["entries"]) == 1

    def test_format_snowflake_lineage_markdown(self):
        from querido.output.formats import format_snowflake_lineage

        result = {
            "object": "db.schema.t",
            "direction": "upstream",
            "domain": "table",
            "depth": 3,
            "entries": [
                {"SOURCE": "db.schema.src", "TARGET": "db.schema.t"},
            ],
        }
        output = format_snowflake_lineage(result, "markdown")
        assert "## Lineage" in output
        assert "db.schema.t" in output
        assert "upstream" in output

    def test_format_snowflake_lineage_csv(self):
        from querido.output.formats import format_snowflake_lineage

        result = {
            "object": "db.schema.t",
            "direction": "downstream",
            "domain": "table",
            "depth": 5,
            "entries": [
                {"SOURCE": "db.schema.t", "TARGET": "db.schema.v"},
            ],
        }
        output = format_snowflake_lineage(result, "csv")
        assert "SOURCE" in output
        assert "TARGET" in output

    def test_print_snowflake_lineage_empty(self):
        from querido.output.console import print_snowflake_lineage

        result = {
            "object": "db.schema.t",
            "direction": "downstream",
            "entries": [],
        }
        # Should not raise
        print_snowflake_lineage(result)

    def test_print_snowflake_lineage_with_data(self):
        from querido.output.console import print_snowflake_lineage

        result = {
            "object": "db.schema.t",
            "direction": "downstream",
            "entries": [
                {"SOURCE": "db.schema.t", "TARGET": "db.schema.v", "DISTANCE": 1},
            ],
        }
        # Should not raise
        print_snowflake_lineage(result)
