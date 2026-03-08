import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


@pytest.fixture
def multi_table_sqlite(tmp_path: Path) -> str:
    """SQLite database with multiple tables and views for search testing."""
    db_path = str(tmp_path / "search.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, user_name TEXT, email TEXT)")
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, total REAL)")
    conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, product_name TEXT, price REAL)")
    conn.execute(
        "CREATE VIEW user_orders AS SELECT u.user_name, o.total "
        "FROM users u JOIN orders o ON u.id = o.user_id"
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def multi_table_duckdb(tmp_path: Path) -> str:
    """DuckDB database with multiple tables for search testing."""
    import duckdb

    db_path = str(tmp_path / "search.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, user_name VARCHAR, email VARCHAR)")
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, total DOUBLE)")
    conn.execute(
        "CREATE TABLE products (id INTEGER PRIMARY KEY, product_name VARCHAR, price DOUBLE)"
    )
    conn.close()
    return db_path


# -- Table name search --------------------------------------------------------


def test_search_table_by_name(multi_table_sqlite: str):
    result = runner.invoke(app, ["search", "-p", "user", "-c", multi_table_sqlite])
    assert result.exit_code == 0
    assert "users" in result.output
    assert "user_orders" in result.output


def test_search_case_insensitive(multi_table_sqlite: str):
    result = runner.invoke(app, ["search", "-p", "USER", "-c", multi_table_sqlite])
    assert result.exit_code == 0
    assert "users" in result.output


def test_search_no_results(multi_table_sqlite: str):
    result = runner.invoke(app, ["search", "-p", "nonexistent", "-c", multi_table_sqlite])
    assert result.exit_code == 0
    assert "No matches" in result.output


# -- Column search ------------------------------------------------------------


def test_search_column_match(multi_table_sqlite: str):
    result = runner.invoke(
        app, ["search", "-p", "email", "-c", multi_table_sqlite, "--type", "column"]
    )
    assert result.exit_code == 0
    assert "email" in result.output
    assert "users" in result.output


def test_search_column_across_tables(multi_table_sqlite: str):
    """'id' column exists in multiple tables."""
    result = runner.invoke(
        app, ["search", "-p", "id", "-c", multi_table_sqlite, "--type", "column"]
    )
    assert result.exit_code == 0
    assert "users" in result.output
    assert "orders" in result.output
    assert "products" in result.output


# -- Type filter --------------------------------------------------------------


def test_search_type_table_only(multi_table_sqlite: str):
    """--type table should only match table names, not column names."""
    result = runner.invoke(
        app, ["search", "-p", "email", "-c", multi_table_sqlite, "--type", "table"]
    )
    assert result.exit_code == 0
    assert "No matches" in result.output


def test_search_type_all_matches_both(multi_table_sqlite: str):
    """'user' matches table name 'users' and column 'user_name' and 'user_id'."""
    result = runner.invoke(
        app, ["search", "-p", "user", "-c", multi_table_sqlite, "--type", "all"]
    )
    assert result.exit_code == 0
    assert "users" in result.output
    assert "user_name" in result.output


# -- View detection -----------------------------------------------------------


def test_search_finds_views(multi_table_sqlite: str):
    result = runner.invoke(app, ["search", "-p", "user_orders", "-c", multi_table_sqlite])
    assert result.exit_code == 0
    assert "view" in result.output


# -- DuckDB ------------------------------------------------------------------


def test_search_duckdb(multi_table_duckdb: str):
    result = runner.invoke(app, ["search", "-p", "product", "-c", multi_table_duckdb])
    assert result.exit_code == 0
    assert "products" in result.output
    assert "product_name" in result.output


# -- Output formats -----------------------------------------------------------


def test_search_json_format(multi_table_sqlite: str):
    result = runner.invoke(
        app, ["--format", "json", "search", "-p", "user", "-c", multi_table_sqlite]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["pattern"] == "user"
    assert len(data["results"]) > 0
    table_names = {r["table_name"] for r in data["results"]}
    assert "users" in table_names


def test_search_csv_format(multi_table_sqlite: str):
    result = runner.invoke(
        app, ["--format", "csv", "search", "-p", "user", "-c", multi_table_sqlite]
    )
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert "table_name" in lines[0]
    assert "match_type" in lines[0]


def test_search_markdown_format(multi_table_sqlite: str):
    result = runner.invoke(
        app, ["--format", "markdown", "search", "-p", "user", "-c", multi_table_sqlite]
    )
    assert result.exit_code == 0
    assert "## Search:" in result.output
    assert "| Table |" in result.output


# -- Invalid type -------------------------------------------------------------


def test_search_invalid_type(multi_table_sqlite: str):
    result = runner.invoke(
        app, ["search", "-p", "user", "-c", multi_table_sqlite, "--type", "invalid"]
    )
    assert result.exit_code != 0
