"""Integration tests for qdo profile against real databases."""

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


class TestProfileSQLite:
    def test_customers_full(self, integration_sqlite_path: str):
        result = runner.invoke(
            app, ["profile", "--connection", integration_sqlite_path, "--table", "customers"]
        )
        assert result.exit_code == 0
        assert "Numeric Columns" in result.output or "String Columns" in result.output
        assert "Total rows" in result.output

    def test_products_numeric(self, integration_sqlite_path: str):
        result = runner.invoke(
            app,
            [
                "profile",
                "--connection",
                integration_sqlite_path,
                "--table",
                "products",
                "--columns",
                "price",
            ],
        )
        assert result.exit_code == 0
        assert "Numeric Columns" in result.output

    def test_columns_filter(self, integration_sqlite_path: str):
        result = runner.invoke(
            app,
            [
                "profile",
                "--connection",
                integration_sqlite_path,
                "--table",
                "customers",
                "--columns",
                "company,city",
            ],
        )
        assert result.exit_code == 0
        assert "String Columns" in result.output


class TestProfileDuckDB:
    def test_customers_full(self, integration_duckdb_path: str):
        result = runner.invoke(
            app, ["profile", "--connection", integration_duckdb_path, "--table", "customers"]
        )
        assert result.exit_code == 0
        assert "Total rows" in result.output

    def test_products_numeric(self, integration_duckdb_path: str):
        result = runner.invoke(
            app,
            [
                "profile",
                "--connection",
                integration_duckdb_path,
                "--table",
                "products",
                "--columns",
                "price",
            ],
        )
        assert result.exit_code == 0
        assert "Numeric Columns" in result.output

    def test_no_sample_flag(self, integration_duckdb_path: str):
        result = runner.invoke(
            app,
            [
                "profile",
                "--connection",
                integration_duckdb_path,
                "--table",
                "products",
                "--no-sample",
            ],
        )
        assert result.exit_code == 0
        assert "Total rows" in result.output
