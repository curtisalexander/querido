"""Tests for qdo joins command."""

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


@pytest.fixture
def relational_db(tmp_path: Path) -> str:
    """Database with customers, orders, products, order_items tables."""
    db_path = str(tmp_path / "shop.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE customers (  id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    conn.execute(
        "CREATE TABLE orders ("
        "  id INTEGER PRIMARY KEY, customer_id INTEGER, "
        "  order_date TEXT, total REAL"
        ")"
    )
    conn.execute("CREATE TABLE products (  id INTEGER PRIMARY KEY, name TEXT, price REAL)")
    conn.execute(
        "CREATE TABLE order_items ("
        "  id INTEGER PRIMARY KEY, order_id INTEGER, "
        "  product_id INTEGER, quantity INTEGER"
        ")"
    )
    conn.execute("INSERT INTO customers VALUES (1, 'Alice', 'a@b.com')")
    conn.execute("INSERT INTO orders VALUES (1, 1, '2024-01-01', 99.99)")
    conn.execute("INSERT INTO products VALUES (1, 'Widget', 9.99)")
    conn.execute("INSERT INTO order_items VALUES (1, 1, 1, 2)")
    conn.commit()
    conn.close()
    return db_path


def test_joins_discovers_convention_match(relational_db: str):
    """orders.customer_id should match customers.id via convention."""
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "joins",
            "-c",
            relational_db,
            "-t",
            "orders",
            "--target",
            "customers",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert len(payload["candidates"]) == 1
    keys = payload["candidates"][0]["join_keys"]
    # Should find customer_id → id convention match
    matches = [k for k in keys if k["source_col"] == "customer_id" and k["target_col"] == "id"]
    assert len(matches) == 1
    assert matches[0]["match_type"] == "convention"


def test_joins_discovers_exact_name_match(relational_db: str):
    """orders.id and order_items.id share the same name."""
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "joins",
            "-c",
            relational_db,
            "-t",
            "orders",
            "--target",
            "order_items",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert len(payload["candidates"]) == 1
    keys = payload["candidates"][0]["join_keys"]
    exact = [k for k in keys if k["match_type"] == "exact_name"]
    assert len(exact) >= 1  # at least "id" matches


def test_joins_scan_all_tables(relational_db: str):
    """Without --target, should scan all tables."""
    result = runner.invoke(
        app,
        ["-f", "json", "joins", "-c", relational_db, "-t", "orders"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    # Should find candidates in multiple tables
    target_names = {c["target_table"] for c in payload["candidates"]}
    assert len(target_names) >= 1


def test_joins_no_candidates(tmp_path: Path):
    """Tables with no matching columns should return empty candidates."""
    db_path = str(tmp_path / "no_match.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE alpha (x INTEGER, y TEXT)")
    conn.execute("CREATE TABLE beta (a REAL, b TEXT)")
    conn.execute("INSERT INTO alpha VALUES (1, 'a')")
    conn.execute("INSERT INTO beta VALUES (1.0, 'b')")
    conn.commit()
    conn.close()

    result = runner.invoke(
        app,
        ["-f", "json", "joins", "-c", db_path, "-t", "alpha"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["candidates"] == []


def test_joins_format_rich(relational_db: str):
    result = runner.invoke(
        app,
        ["joins", "-c", relational_db, "-t", "orders", "--target", "customers"],
    )
    assert result.exit_code == 0
    assert "customer_id" in result.output


def test_joins_format_csv(relational_db: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "csv",
            "joins",
            "-c",
            relational_db,
            "-t",
            "orders",
            "--target",
            "customers",
        ],
    )
    assert result.exit_code == 0
    assert "source_col" in result.output
    assert "customer_id" in result.output


def test_joins_format_markdown(relational_db: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "markdown",
            "joins",
            "-c",
            relational_db,
            "-t",
            "orders",
            "--target",
            "customers",
        ],
    )
    assert result.exit_code == 0
    assert "| Target" in result.output


def test_joins_reverse_convention(relational_db: str):
    """customers should discover orders via reverse convention (order.customer_id)."""
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "joins",
            "-c",
            relational_db,
            "-t",
            "customers",
            "--target",
            "orders",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert len(payload["candidates"]) == 1
    keys = payload["candidates"][0]["join_keys"]
    # Should find id → customer_id via reverse convention
    convention = [k for k in keys if k["match_type"] == "convention"]
    assert len(convention) >= 1


def test_joins_confidence_scoring(relational_db: str):
    """Confidence should be between 0 and 1."""
    result = runner.invoke(
        app,
        ["-f", "json", "joins", "-c", relational_db, "-t", "orders"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    for cand in payload["candidates"]:
        for key in cand["join_keys"]:
            assert 0.0 <= key["confidence"] <= 1.0


def test_joins_duckdb(tmp_path: Path):
    import duckdb

    db_path = str(tmp_path / "shop.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR)")
    conn.execute("CREATE TABLE posts (id INTEGER, user_id INTEGER, title VARCHAR)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice')")
    conn.execute("INSERT INTO posts VALUES (1, 1, 'Hello')")
    conn.close()

    result = runner.invoke(
        app,
        ["-f", "json", "joins", "-c", db_path, "-t", "posts", "--target", "users"],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert len(payload["candidates"]) == 1
    keys = payload["candidates"][0]["join_keys"]
    convention = [k for k in keys if k["source_col"] == "user_id"]
    assert len(convention) >= 1
