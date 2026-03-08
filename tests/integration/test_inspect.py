"""Integration tests for qdo inspect against real databases."""

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


class TestInspectSQLite:
    def test_customers_table(self, integration_sqlite_path: str):
        result = runner.invoke(
            app, ["inspect", "--connection", integration_sqlite_path, "--table", "customers"]
        )
        assert result.exit_code == 0
        assert "customer_id" in result.output
        assert "first_name" in result.output
        assert "email" in result.output
        assert "1,000" in result.output

    def test_products_table(self, integration_sqlite_path: str):
        result = runner.invoke(
            app, ["inspect", "--connection", integration_sqlite_path, "--table", "products"]
        )
        assert result.exit_code == 0
        assert "price" in result.output
        assert "stock" in result.output
        assert "1,000" in result.output


class TestInspectDuckDB:
    def test_customers_table(self, integration_duckdb_path: str):
        result = runner.invoke(
            app, ["inspect", "--connection", integration_duckdb_path, "--table", "customers"]
        )
        assert result.exit_code == 0
        assert "customer_id" in result.output
        assert "first_name" in result.output
        assert "email" in result.output
        assert "1,000" in result.output

    def test_products_table(self, integration_duckdb_path: str):
        result = runner.invoke(
            app, ["inspect", "--connection", integration_duckdb_path, "--table", "products"]
        )
        assert result.exit_code == 0
        assert "price" in result.output
        assert "stock" in result.output
        assert "1,000" in result.output
