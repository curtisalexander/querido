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
def snowflake_cmd_sqlite(tmp_path: Path) -> str:
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
        from querido.core.semantic import build_semantic_yaml

        columns = [
            {"name": "ORDER_ID", "type": "NUMBER", "comment": "Primary key"},
            {"name": "CUSTOMER_NAME", "type": "VARCHAR", "comment": None},
            {"name": "TOTAL", "type": "FLOAT", "comment": "Order total"},
            {"name": "ORDER_DATE", "type": "DATE", "comment": "When placed"},
            {"name": "STATUS", "type": "VARCHAR", "comment": "Current status"},
        ]
        yaml_str = build_semantic_yaml("ORDERS", columns, "Orders table")

        assert "name: orders_semantic_model" in yaml_str
        assert "description: Orders table" in yaml_str
        assert "base_table: ORDERS" in yaml_str
        assert "dimensions:" in yaml_str
        assert "measures:" in yaml_str
        assert "time_dimensions:" in yaml_str

    def test_classify_id_as_dimension(self):
        from querido.core._utils import classify_column_kind

        col = {"name": "ORDER_ID", "type": "NUMBER"}
        assert classify_column_kind(col) == "dimension"

    def test_classify_numeric_as_measure(self):
        from querido.core._utils import classify_column_kind

        col = {"name": "TOTAL", "type": "FLOAT"}
        assert classify_column_kind(col) == "measure"

    def test_classify_date_as_time_dimension(self):
        from querido.core._utils import classify_column_kind

        col = {"name": "ORDER_DATE", "type": "DATE"}
        assert classify_column_kind(col) == "time_dimension"

    def test_classify_timestamp_as_time_dimension(self):
        from querido.core._utils import classify_column_kind

        col = {"name": "CREATED_AT", "type": "TIMESTAMP_NTZ"}
        assert classify_column_kind(col) == "time_dimension"

    def test_classify_string_as_dimension(self):
        from querido.core._utils import classify_column_kind

        col = {"name": "STATUS", "type": "VARCHAR"}
        assert classify_column_kind(col) == "dimension"

    def test_yaml_includes_comments_as_descriptions(self):
        from querido.core.semantic import build_semantic_yaml

        columns = [
            {"name": "REVENUE", "type": "FLOAT", "comment": "Total revenue"},
        ]
        yaml_str = build_semantic_yaml("SALES", columns, None)
        assert "description: Total revenue" in yaml_str

    def test_yaml_placeholder_when_no_comment(self):
        from querido.core.semantic import build_semantic_yaml

        columns = [
            {"name": "STATUS", "type": "VARCHAR", "comment": None},
        ]
        yaml_str = build_semantic_yaml("ORDERS", columns, None)
        assert "<description>" in yaml_str

    def test_yaml_measures_have_default_aggregation(self):
        from querido.core.semantic import build_semantic_yaml

        columns = [
            {"name": "AMOUNT", "type": "FLOAT", "comment": None},
        ]
        yaml_str = build_semantic_yaml("SALES", columns, None)
        assert "default_aggregation: sum" in yaml_str

    def test_yaml_dimensions_have_synonyms_placeholder(self):
        from querido.core.semantic import build_semantic_yaml

        columns = [
            {"name": "STATUS", "type": "VARCHAR", "comment": None},
        ]
        yaml_str = build_semantic_yaml("ORDERS", columns, None)
        assert "synonyms:" in yaml_str
        assert "<synonym>" in yaml_str


# ---------------------------------------------------------------------------
# Semantic view DDL — unit tests (what `qdo snowflake semantic` emits)
# ---------------------------------------------------------------------------


class TestSemanticViewDdl:
    def test_basic_structure_and_clause_order(self):
        from querido.core.semantic import build_semantic_view_ddl

        columns = [
            {"name": "ORDER_ID", "type": "NUMBER", "comment": "Primary key"},
            {"name": "TOTAL", "type": "FLOAT", "comment": "Order total"},
            {"name": "ORDER_DATE", "type": "DATE", "comment": "When placed"},
            {"name": "STATUS", "type": "VARCHAR", "comment": "Current status"},
        ]
        ddl = build_semantic_view_ddl("ORDERS", columns, "Orders table")

        assert ddl.startswith("create or replace semantic view orders_semantic_view")
        assert "orders as ORDERS" in ddl
        assert "comment = 'Orders table'" in ddl
        # Clause order is fixed by the syntax: tables, facts, dimensions, metrics.
        assert (
            ddl.index("tables (")
            < ddl.index("facts (")
            < ddl.index("dimensions (")
            < ddl.index("metrics (")
        )

    def test_measures_become_facts_and_metrics(self):
        from querido.core.semantic import build_semantic_view_ddl

        columns = [{"name": "AMOUNT", "type": "FLOAT", "comment": None}]
        ddl = build_semantic_view_ddl("SALES", columns, None)
        assert "sales.amount as AMOUNT" in ddl
        assert "sales.sum_amount as sum(amount)" in ddl

    def test_avg_keyword_measures_use_avg(self):
        from querido.core.semantic import build_semantic_view_ddl

        columns = [{"name": "RATE", "type": "FLOAT", "comment": None}]
        ddl = build_semantic_view_ddl("SALES", columns, None)
        assert "sales.avg_rate as avg(rate)" in ddl

    def test_time_dimension_is_a_plain_dimension(self):
        from querido.core.semantic import build_semantic_view_ddl

        columns = [{"name": "CREATED_AT", "type": "TIMESTAMP_NTZ", "comment": None}]
        ddl = build_semantic_view_ddl("ORDERS", columns, None)
        assert "dimensions (" in ddl
        assert "orders.created_at as CREATED_AT" in ddl
        # Clause openers are indented two spaces; the trailing guidance
        # comments also mention "facts (...)", so match the clause form.
        assert "\n  facts (" not in ddl
        assert "\n  metrics (" not in ddl

    def test_primary_key_from_column_metadata(self):
        from querido.core.semantic import build_semantic_view_ddl

        columns = [
            {"name": "ORDER_ID", "type": "NUMBER", "comment": None, "primary_key": True},
        ]
        ddl = build_semantic_view_ddl("ORDERS", columns, None)
        assert "primary key (ORDER_ID)" in ddl

    def test_comment_single_quotes_escaped(self):
        from querido.core.semantic import build_semantic_view_ddl

        columns = [{"name": "STATUS", "type": "VARCHAR", "comment": "Customer's status"}]
        ddl = build_semantic_view_ddl("ORDERS", columns, None)
        assert "comment = 'Customer''s status.'" in ddl

    def test_sample_values_appended_to_comment(self):
        from querido.core.semantic import build_semantic_view_ddl

        columns = [{"name": "STATUS", "type": "VARCHAR", "comment": "Status"}]
        ddl = build_semantic_view_ddl(
            "ORDERS",
            columns,
            None,
            sample_values_per_col={"STATUS": ["pending", "shipped"]},
        )
        assert "Sample values: pending, shipped." in ddl

    def test_synonyms_left_to_review_not_emitted(self):
        """A placeholder synonym would execute; guidance goes in SQL comments."""
        from querido.core.semantic import build_semantic_view_ddl

        columns = [{"name": "STATUS", "type": "VARCHAR", "comment": None}]
        ddl = build_semantic_view_ddl("ORDERS", columns, None)
        assert "with synonyms" not in ddl.split("-- Synonyms")[0]
        assert "-- Synonyms" in ddl


# ---------------------------------------------------------------------------
# F8: Semantic CLI — non-Snowflake rejection
# ---------------------------------------------------------------------------


class TestSemanticCLI:
    def test_semantic_rejects_sqlite(self, snowflake_cmd_sqlite: str):
        result = runner.invoke(
            app, ["snowflake", "semantic", "-t", "orders", "-c", snowflake_cmd_sqlite]
        )
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

    def test_semantic_rejects_sqlite_json(self, snowflake_cmd_sqlite: str):
        result = runner.invoke(
            app,
            ["-f", "json", "snowflake", "semantic", "-t", "orders", "-c", snowflake_cmd_sqlite],
        )
        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["code"] == "SNOWFLAKE_REQUIRED"

    def test_semantic_output_file_emits_envelope_json(
        self, snowflake_cmd_sqlite: str, tmp_path: Path, monkeypatch
    ):
        """Under -f json, `semantic -o <file>` must emit an envelope with the written path
        rather than leaving stdout empty (M8)."""
        import querido.cli.snowflake as snowflake_cli

        monkeypatch.setattr(snowflake_cli, "require_snowflake", lambda *a, **k: None)
        out_file = tmp_path / "orders.sql"
        result = runner.invoke(
            app,
            [
                "-f",
                "json",
                "snowflake",
                "semantic",
                "-t",
                "orders",
                "-c",
                snowflake_cmd_sqlite,
                "-o",
                str(out_file),
                "--sample-values",
                "0",
            ],
        )
        assert result.exit_code == 0, result.output
        assert out_file.exists()
        payload = json.loads(result.output)
        assert set(payload) == {"command", "data", "next_steps", "meta"}
        assert payload.get("command") == "snowflake semantic"
        assert payload.get("data", {}).get("path") == str(out_file)

    def test_semantic_output_file_rich_stays_quiet_on_stdout(
        self, snowflake_cmd_sqlite: str, tmp_path: Path, monkeypatch
    ):
        """Human format with -o keeps writing the file and reporting on stderr only."""
        import querido.cli.snowflake as snowflake_cli

        monkeypatch.setattr(snowflake_cli, "require_snowflake", lambda *a, **k: None)
        out_file = tmp_path / "orders.sql"
        result = runner.invoke(
            app,
            [
                "snowflake",
                "semantic",
                "-t",
                "orders",
                "-c",
                snowflake_cmd_sqlite,
                "-o",
                str(out_file),
                "--sample-values",
                "0",
            ],
        )
        assert result.exit_code == 0, result.output
        assert out_file.exists()
        assert "create or replace semantic view" in out_file.read_text()


# ---------------------------------------------------------------------------
# F9: Lineage CLI — non-Snowflake rejection
# ---------------------------------------------------------------------------


class TestLineageCLI:
    def test_lineage_rejects_sqlite(self, snowflake_cmd_sqlite: str):
        result = runner.invoke(
            app,
            ["snowflake", "lineage", "--object", "db.schema.orders", "-c", snowflake_cmd_sqlite],
        )
        assert result.exit_code != 0
        assert "Snowflake" in result.output

    def test_lineage_invalid_direction(self, snowflake_cmd_sqlite: str):
        result = runner.invoke(
            app,
            [
                "snowflake",
                "lineage",
                "--object",
                "db.schema.orders",
                "-c",
                snowflake_cmd_sqlite,
                "-d",
                "sideways",
            ],
        )
        assert result.exit_code != 0

    def test_lineage_invalid_direction_json(self, snowflake_cmd_sqlite: str):
        result = runner.invoke(
            app,
            [
                "-f",
                "json",
                "snowflake",
                "lineage",
                "--object",
                "db.schema.orders",
                "-c",
                snowflake_cmd_sqlite,
                "-d",
                "sideways",
            ],
        )
        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["code"] == "LINEAGE_DIRECTION_INVALID"

    def test_lineage_invalid_domain(self, snowflake_cmd_sqlite: str):
        result = runner.invoke(
            app,
            [
                "snowflake",
                "lineage",
                "--object",
                "db.schema.orders",
                "-c",
                snowflake_cmd_sqlite,
                "--domain",
                "database",
            ],
        )
        assert result.exit_code != 0

    def test_lineage_invalid_domain_json(self, snowflake_cmd_sqlite: str):
        result = runner.invoke(
            app,
            [
                "-f",
                "json",
                "snowflake",
                "lineage",
                "--object",
                "db.schema.orders",
                "-c",
                snowflake_cmd_sqlite,
                "--domain",
                "database",
            ],
        )
        assert result.exit_code != 0
        payload = json.loads(result.output)
        assert payload["code"] == "LINEAGE_DOMAIN_INVALID"


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
