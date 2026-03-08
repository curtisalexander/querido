"""Integration tests using real databases created by scripts/init_test_data.py."""

from querido.connectors.duckdb import DuckDBConnector
from querido.connectors.factory import create_connector
from querido.connectors.sqlite import SQLiteConnector


class TestSQLiteIntegration:
    def test_customers_row_count(self, integration_sqlite_path: str):
        with SQLiteConnector(integration_sqlite_path) as conn:
            rows = conn.execute("SELECT COUNT(*) as cnt FROM customers")
            assert rows[0]["cnt"] == 1000

    def test_products_row_count(self, integration_sqlite_path: str):
        with SQLiteConnector(integration_sqlite_path) as conn:
            rows = conn.execute("SELECT COUNT(*) as cnt FROM products")
            assert rows[0]["cnt"] == 1000

    def test_customers_columns(self, integration_sqlite_path: str):
        with SQLiteConnector(integration_sqlite_path) as conn:
            cols = conn.get_columns("customers")
            names = [c["name"] for c in cols]
            assert "customer_id" in names
            assert "first_name" in names
            assert "email" in names
            assert "subscription_date" in names

    def test_products_has_numeric_data(self, integration_sqlite_path: str):
        with SQLiteConnector(integration_sqlite_path) as conn:
            rows = conn.execute(
                "SELECT price, stock FROM products WHERE price IS NOT NULL LIMIT 5"
            )
            assert len(rows) > 0
            assert isinstance(rows[0]["price"], (int, float))

    def test_factory_with_file_path(self, integration_sqlite_path: str):
        with create_connector({"type": "sqlite", "path": integration_sqlite_path}) as conn:
            rows = conn.execute("SELECT COUNT(*) as cnt FROM customers")
            assert rows[0]["cnt"] == 1000


class TestDuckDBIntegration:
    def test_customers_row_count(self, integration_duckdb_path: str):
        with DuckDBConnector(integration_duckdb_path) as conn:
            rows = conn.execute("SELECT COUNT(*) as cnt FROM customers")
            assert rows[0]["cnt"] == 1000

    def test_products_row_count(self, integration_duckdb_path: str):
        with DuckDBConnector(integration_duckdb_path) as conn:
            rows = conn.execute("SELECT COUNT(*) as cnt FROM products")
            assert rows[0]["cnt"] == 1000

    def test_customers_columns(self, integration_duckdb_path: str):
        with DuckDBConnector(integration_duckdb_path) as conn:
            cols = conn.get_columns("customers")
            names = [c["name"] for c in cols]
            assert "customer_id" in names
            assert "first_name" in names
            assert "email" in names
            assert "subscription_date" in names

    def test_products_has_numeric_data(self, integration_duckdb_path: str):
        with DuckDBConnector(integration_duckdb_path) as conn:
            rows = conn.execute(
                "SELECT price, stock FROM products WHERE price IS NOT NULL LIMIT 5"
            )
            assert len(rows) > 0
            assert isinstance(rows[0]["price"], (int, float))

    def test_factory_with_file_path(self, integration_duckdb_path: str):
        with create_connector({"type": "duckdb", "path": integration_duckdb_path}) as conn:
            rows = conn.execute("SELECT COUNT(*) as cnt FROM customers")
            assert rows[0]["cnt"] == 1000
