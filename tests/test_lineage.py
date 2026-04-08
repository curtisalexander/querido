import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


@pytest.fixture
def view_sqlite(tmp_path: Path) -> str:
    db_path = str(tmp_path / "lineage.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@example.com')")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 'bob@example.com')")
    conn.execute("CREATE VIEW active_users AS SELECT id, name FROM users WHERE name IS NOT NULL")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def view_duckdb(tmp_path: Path) -> str:
    import duckdb

    db_path = str(tmp_path / "lineage.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE orders (id INTEGER, customer TEXT, total DOUBLE)")
    conn.execute("INSERT INTO orders VALUES (1, 'Alice', 99.99)")
    conn.execute("CREATE VIEW high_value_orders AS SELECT * FROM orders WHERE total > 50")
    conn.close()
    return db_path


# -- SQLite view definition ---------------------------------------------------


def test_lineage_sqlite_rich(view_sqlite: str):
    result = runner.invoke(app, ["view-def", "--view", "active_users", "-c", view_sqlite])
    assert result.exit_code == 0
    assert "active_users" in result.output


def test_lineage_sqlite_json(view_sqlite: str):
    result = runner.invoke(
        app, ["--format", "json", "view-def", "--view", "active_users", "-c", view_sqlite]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["view"] == "active_users"
    assert data["dialect"] == "sqlite"
    assert "SELECT" in data["definition"]
    assert "users" in data["definition"]


def test_lineage_sqlite_markdown(view_sqlite: str):
    result = runner.invoke(
        app, ["--format", "markdown", "view-def", "--view", "active_users", "-c", view_sqlite]
    )
    assert result.exit_code == 0
    assert "## View: active_users" in result.output
    assert "```sql" in result.output


def test_lineage_sqlite_csv(view_sqlite: str):
    result = runner.invoke(
        app, ["--format", "csv", "view-def", "--view", "active_users", "-c", view_sqlite]
    )
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert "view" in lines[0]
    assert "definition" in lines[0]


# -- DuckDB view definition ---------------------------------------------------


def test_lineage_duckdb_rich(view_duckdb: str):
    result = runner.invoke(app, ["view-def", "--view", "high_value_orders", "-c", view_duckdb])
    assert result.exit_code == 0
    assert "high_value_orders" in result.output


def test_lineage_duckdb_json(view_duckdb: str):
    result = runner.invoke(
        app, ["--format", "json", "view-def", "--view", "high_value_orders", "-c", view_duckdb]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["view"] == "high_value_orders"
    assert data["dialect"] == "duckdb"
    assert "orders" in data["definition"]


# -- Error cases ---------------------------------------------------------------


def test_lineage_table_not_view(view_sqlite: str):
    """Requesting lineage for a table (not a view) should fail gracefully."""
    result = runner.invoke(app, ["view-def", "--view", "users", "-c", view_sqlite])
    assert result.exit_code != 0


def test_lineage_nonexistent_view(view_sqlite: str):
    """Requesting lineage for a view that doesn't exist should fail."""
    result = runner.invoke(app, ["view-def", "--view", "no_such_view", "-c", view_sqlite])
    assert result.exit_code != 0


def test_lineage_invalid_name(view_sqlite: str):
    """Invalid view names should be rejected."""
    result = runner.invoke(app, ["view-def", "--view", "'; DROP TABLE--", "-c", view_sqlite])
    assert result.exit_code != 0


# -- Connector method tests ---------------------------------------------------


def test_sqlite_get_view_definition(view_sqlite: str):
    from querido.connectors.sqlite import SQLiteConnector

    with SQLiteConnector(view_sqlite) as conn:
        defn = conn.get_view_definition("active_users")
        assert defn is not None
        assert "SELECT" in defn
        assert "users" in defn

        # Non-view returns None
        assert conn.get_view_definition("users") is None


def test_duckdb_get_view_definition(view_duckdb: str):
    from querido.connectors.duckdb import DuckDBConnector

    with DuckDBConnector(view_duckdb) as conn:
        defn = conn.get_view_definition("high_value_orders")
        assert defn is not None
        assert "orders" in defn

        # Non-view returns None
        assert conn.get_view_definition("orders") is None
