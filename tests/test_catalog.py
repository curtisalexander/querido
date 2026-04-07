import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


def test_catalog_sqlite(sqlite_path: str):
    result = runner.invoke(app, ["catalog", "-c", sqlite_path])
    assert result.exit_code == 0
    assert "users" in result.output
    assert "table" in result.output.lower()


def test_catalog_duckdb(duckdb_path: str):
    result = runner.invoke(app, ["catalog", "-c", duckdb_path])
    assert result.exit_code == 0
    assert "users" in result.output


def test_catalog_tables_only(sqlite_path: str):
    result = runner.invoke(app, ["catalog", "-c", sqlite_path, "--tables-only"])
    assert result.exit_code == 0
    assert "users" in result.output


def test_catalog_format_json(sqlite_path: str):
    result = runner.invoke(app, ["-f", "json", "catalog", "-c", sqlite_path])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["table_count"] == 1
    assert payload["tables"][0]["name"] == "users"
    assert payload["tables"][0]["row_count"] == 2
    assert len(payload["tables"][0]["columns"]) == 3


def test_catalog_format_json_tables_only(sqlite_path: str):
    result = runner.invoke(
        app, ["-f", "json", "catalog", "-c", sqlite_path, "--tables-only"]
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["table_count"] == 1
    assert payload["tables"][0]["columns"] is None
    assert payload["tables"][0]["row_count"] is None


def test_catalog_format_csv(sqlite_path: str):
    result = runner.invoke(app, ["-f", "csv", "catalog", "-c", sqlite_path])
    assert result.exit_code == 0
    assert "table" in result.output
    assert "users" in result.output


def test_catalog_format_markdown(sqlite_path: str):
    result = runner.invoke(app, ["-f", "markdown", "catalog", "-c", sqlite_path])
    assert result.exit_code == 0
    assert "### users" in result.output
    assert "| Column" in result.output


def test_catalog_empty_database(tmp_path: Path):
    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.close()
    result = runner.invoke(app, ["catalog", "-c", db_path])
    assert result.exit_code == 0
    assert "no tables" in result.output.lower()


def test_catalog_multiple_tables(tmp_path: Path):
    db_path = str(tmp_path / "multi.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount REAL)")
    conn.execute("INSERT INTO orders VALUES (1, 99.99)")
    conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO products VALUES (1, 'Widget')")
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["-f", "json", "catalog", "-c", db_path])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["table_count"] == 2
    names = {t["name"] for t in payload["tables"]}
    assert names == {"orders", "products"}


def test_catalog_includes_views(tmp_path: Path):
    db_path = str(tmp_path / "views.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice')")
    conn.execute("CREATE VIEW active_users AS SELECT * FROM users")
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["-f", "json", "catalog", "-c", db_path])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    types = {t["name"]: t["type"] for t in payload["tables"]}
    assert types["users"] == "table"
    assert types["active_users"] == "view"


def test_catalog_live_flag(sqlite_path: str):
    """--live should always query the database, not the cache."""
    result = runner.invoke(
        app, ["-f", "json", "catalog", "-c", sqlite_path, "--live"]
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["table_count"] == 1


def test_catalog_column_details(sqlite_path: str):
    """Columns should include type and nullable info."""
    result = runner.invoke(app, ["-f", "json", "catalog", "-c", sqlite_path])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    cols = payload["tables"][0]["columns"]
    col_names = [c["name"] for c in cols]
    assert "id" in col_names
    assert "name" in col_names
    assert "age" in col_names
    # Each column has type info
    for c in cols:
        assert "type" in c
        assert "nullable" in c
