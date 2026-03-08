"""Integration tests for qdo preview against real databases."""

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


class TestPreviewSQLite:
    def test_customers_default(self, integration_sqlite_path: str):
        result = runner.invoke(
            app, ["preview", "--connection", integration_sqlite_path, "--table", "customers"]
        )
        assert result.exit_code == 0
        assert "20 row(s)" in result.output

    def test_products_custom_rows(self, integration_sqlite_path: str):
        result = runner.invoke(
            app,
            ["preview", "--connection", integration_sqlite_path, "--table", "products", "-r", "5"],
        )
        assert result.exit_code == 0
        assert "5 row(s)" in result.output


class TestPreviewDuckDB:
    def test_customers_default(self, integration_duckdb_path: str):
        result = runner.invoke(
            app, ["preview", "--connection", integration_duckdb_path, "--table", "customers"]
        )
        assert result.exit_code == 0
        assert "20 row(s)" in result.output

    def test_products_custom_rows(self, integration_duckdb_path: str):
        result = runner.invoke(
            app,
            [
                "preview",
                "--connection",
                integration_duckdb_path,
                "--table",
                "products",
                "-r",
                "5",
            ],
        )
        assert result.exit_code == 0
        assert "5 row(s)" in result.output
