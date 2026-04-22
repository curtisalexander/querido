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

    payload = json.loads(result.output)["data"]
    assert payload["table_count"] == 1
    assert payload["tables"][0]["name"] == "users"
    assert payload["tables"][0]["row_count"] == 2
    assert len(payload["tables"][0]["columns"]) == 3


def test_catalog_format_json_tables_only(sqlite_path: str):
    result = runner.invoke(app, ["-f", "json", "catalog", "-c", sqlite_path, "--tables-only"])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
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

    payload = json.loads(result.output)["data"]
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

    payload = json.loads(result.output)["data"]
    types = {t["name"]: t["type"] for t in payload["tables"]}
    assert types["users"] == "table"
    assert types["active_users"] == "view"


def test_catalog_live_flag(sqlite_path: str):
    """--live should always query the database, not the cache."""
    result = runner.invoke(app, ["-f", "json", "catalog", "-c", sqlite_path, "--live"])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    assert payload["table_count"] == 1


def test_catalog_functions_duckdb_json(duckdb_path: str):
    result = runner.invoke(app, ["-f", "json", "catalog", "functions", "-c", duckdb_path])
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads(result.output)["data"]
    assert payload["supported"] is True
    assert payload["dialect"] == "duckdb"
    assert payload["function_count"] > 0
    assert any(entry["name"] == "lower" for entry in payload["functions"])


def test_catalog_functions_duckdb_pattern_filters(duckdb_path: str):
    result = runner.invoke(
        app,
        ["-f", "json", "catalog", "functions", "-c", duckdb_path, "--pattern", "lower"],
    )
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads(result.output)["data"]
    assert payload["supported"] is True
    assert payload["function_count"] >= 1
    assert all("lower" in entry["name"].lower() for entry in payload["functions"])


def test_catalog_functions_sqlite_is_gracefully_unsupported(sqlite_path: str):
    result = runner.invoke(app, ["-f", "json", "catalog", "functions", "-c", sqlite_path])
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads(result.output)["data"]
    assert payload["supported"] is False
    assert payload["dialect"] == "sqlite"
    assert payload["function_count"] == 0
    assert "not supported" in payload["reason"].lower()


def test_catalog_functions_rich_unsupported_message(sqlite_path: str):
    result = runner.invoke(app, ["catalog", "functions", "-c", sqlite_path])
    assert result.exit_code == 0
    assert "Function catalog unavailable" in result.output


def test_catalog_column_details(sqlite_path: str):
    """Columns should include type and nullable info."""
    result = runner.invoke(app, ["-f", "json", "catalog", "-c", sqlite_path])
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    cols = payload["tables"][0]["columns"]
    col_names = [c["name"] for c in cols]
    assert "id" in col_names
    assert "name" in col_names
    assert "age" in col_names
    # Each column has type info
    for c in cols:
        assert "type" in c
        assert "nullable" in c


def test_catalog_enrich(sqlite_path: str, tmp_path: Path, monkeypatch):
    """--enrich merges stored metadata into catalog output."""
    import yaml

    monkeypatch.chdir(tmp_path)

    # First, init metadata
    result = runner.invoke(app, ["metadata", "init", "-c", sqlite_path, "-t", "users"])
    assert result.exit_code == 0

    # Fill in human fields
    meta_dir = tmp_path / ".qdo" / "metadata" / "test"
    meta_file = meta_dir / "users.yaml"
    meta = yaml.safe_load(meta_file.read_text())
    meta["table_description"] = "Application user accounts"
    meta["data_owner"] = "Identity team"
    meta["columns"][0]["description"] = "Auto-increment primary key"
    with open(meta_file, "w") as f:
        yaml.dump(meta, f)

    # Run catalog with --enrich
    result = runner.invoke(
        app,
        ["-f", "json", "catalog", "-c", sqlite_path, "--enrich"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    users_table = payload["tables"][0]
    assert users_table.get("table_description") == "Application user accounts"
    assert users_table.get("data_owner") == "Identity team"

    # First column should have enriched description
    first_col = users_table["columns"][0]
    assert first_col.get("description") == "Auto-increment primary key"


def test_catalog_enrich_no_metadata(sqlite_path: str, tmp_path: Path, monkeypatch):
    """--enrich with no stored metadata should return catalog unchanged."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        ["-f", "json", "catalog", "-c", sqlite_path, "--enrich"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)["data"]
    # Should work fine, just no enrichment
    assert payload["table_count"] == 1
    assert "table_description" not in payload["tables"][0]


def test_print_catalog_rich_summary_includes_counts() -> None:
    """Rich catalog output should summarize object counts before the detail table."""
    from rich.console import Console

    from querido.output.console import print_catalog

    console = Console(record=True, width=120)
    print_catalog(
        {
            "table_count": 3,
            "tables": [
                {
                    "name": "orders",
                    "type": "table",
                    "row_count": 5000,
                    "columns": [{"name": "id"}, {"name": "amount"}, {"name": "status"}],
                },
                {
                    "name": "customers",
                    "type": "table",
                    "row_count": 1000,
                    "columns": [{"name": "id"}, {"name": "email"}],
                },
                {
                    "name": "active_orders",
                    "type": "view",
                    "row_count": None,
                    "columns": [{"name": "id"}, {"name": "status"}],
                },
            ],
        },
        console=console,
    )
    text = console.export_text()
    assert "Catalog Summary" in text
    assert "2 tables" in text
    assert "1 views" in text
    assert "7 columns" in text
    assert "largest: orders (5,000 rows)" in text
    assert "Object Detail" in text


def test_print_catalog_rich_enriched_notes() -> None:
    """Enriched catalog output should surface descriptions and owners in notes."""
    from rich.console import Console

    from querido.output.console import print_catalog

    console = Console(record=True, width=120)
    print_catalog(
        {
            "table_count": 1,
            "tables": [
                {
                    "name": "users",
                    "type": "table",
                    "row_count": 2,
                    "columns": [{"name": "id"}, {"name": "name"}],
                    "table_description": "Application user accounts",
                    "data_owner": "Identity team",
                }
            ],
        },
        console=console,
    )
    text = console.export_text()
    assert "1 enriched" in text
    assert "Application user accounts" in text
    assert "owner: Identity team" in text
