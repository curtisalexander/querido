import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()


@pytest.fixture
def orders_path(tmp_path: Path) -> str:
    db_path = str(tmp_path / "orders.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE orders (id INTEGER PRIMARY KEY, region TEXT, status TEXT, amount REAL)"
    )
    rows = [
        (1, "east", "shipped", 100.0),
        (2, "east", "shipped", 200.0),
        (3, "east", "pending", 50.0),
        (4, "west", "shipped", 300.0),
        (5, "west", "pending", 150.0),
        (6, "west", "pending", 75.0),
    ]
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return db_path


def test_pivot_basic(orders_path: str):
    result = runner.invoke(
        app,
        ["pivot", "-c", orders_path, "-t", "orders", "-g", "region", "-a", "sum(amount)"],
    )
    assert result.exit_code == 0
    assert "east" in result.output
    assert "west" in result.output


def test_pivot_format_json(orders_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "pivot",
            "-c",
            orders_path,
            "-t",
            "orders",
            "-g",
            "region",
            "-a",
            "sum(amount)",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["command"] == "pivot"
    data = payload["data"]
    assert data["row_count"] == 2
    # Check we got sum_amount for each region
    by_region = {r["region"]: r["sum_amount"] for r in data["rows"]}
    assert by_region["east"] == 350.0
    assert by_region["west"] == 525.0


def test_pivot_multiple_group_by(orders_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "pivot",
            "-c",
            orders_path,
            "-t",
            "orders",
            "-g",
            "region,status",
            "-a",
            "sum(amount)",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["data"]["row_count"] == 4  # 2 regions x 2 statuses


def test_pivot_count(orders_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "pivot",
            "-c",
            orders_path,
            "-t",
            "orders",
            "-g",
            "region",
            "-a",
            "count(id)",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    by_region = {r["region"]: r["count_id"] for r in payload["data"]["rows"]}
    assert by_region["east"] == 3
    assert by_region["west"] == 3


def test_pivot_with_filter(orders_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "pivot",
            "-c",
            orders_path,
            "-t",
            "orders",
            "-g",
            "region",
            "-a",
            "sum(amount)",
            "--filter",
            "status = 'shipped'",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    by_region = {r["region"]: r["sum_amount"] for r in payload["data"]["rows"]}
    assert by_region["east"] == 300.0  # 100 + 200
    assert by_region["west"] == 300.0


def test_pivot_with_limit(orders_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "pivot",
            "-c",
            orders_path,
            "-t",
            "orders",
            "-g",
            "status",
            "-a",
            "count(id)",
            "--limit",
            "1",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["data"]["row_count"] == 1


def test_pivot_with_order_by(orders_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "pivot",
            "-c",
            orders_path,
            "-t",
            "orders",
            "-g",
            "region",
            "-a",
            "sum(amount)",
            "--order-by",
            "sum_amount desc",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    # west (525) should come first
    assert payload["data"]["rows"][0]["region"] == "west"


def test_pivot_format_csv(orders_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "csv",
            "pivot",
            "-c",
            orders_path,
            "-t",
            "orders",
            "-g",
            "region",
            "-a",
            "sum(amount)",
        ],
    )
    assert result.exit_code == 0
    assert "region" in result.output
    assert "sum_amount" in result.output


def test_pivot_format_markdown(orders_path: str):
    result = runner.invoke(
        app,
        [
            "-f",
            "markdown",
            "pivot",
            "-c",
            orders_path,
            "-t",
            "orders",
            "-g",
            "region",
            "-a",
            "sum(amount)",
        ],
    )
    assert result.exit_code == 0
    assert "| region" in result.output


def test_pivot_invalid_agg_format(orders_path: str):
    result = runner.invoke(
        app,
        ["pivot", "-c", orders_path, "-t", "orders", "-g", "region", "-a", "badformat"],
    )
    assert result.exit_code != 0


def test_pivot_mixed_functions_rejected(orders_path: str):
    result = runner.invoke(
        app,
        [
            "pivot",
            "-c",
            orders_path,
            "-t",
            "orders",
            "-g",
            "region",
            "-a",
            "sum(amount),count(id)",
        ],
    )
    assert result.exit_code != 0
    assert "same function" in result.output.lower()


def test_pivot_duckdb(tmp_path: Path):
    import duckdb

    db_path = str(tmp_path / "orders.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE orders (id INTEGER, region VARCHAR, amount DOUBLE)")
    conn.execute("INSERT INTO orders VALUES (1, 'east', 100), (2, 'west', 200)")
    conn.close()

    result = runner.invoke(
        app,
        [
            "-f",
            "json",
            "pivot",
            "-c",
            db_path,
            "-t",
            "orders",
            "-g",
            "region",
            "-a",
            "sum(amount)",
        ],
    )
    assert result.exit_code == 0
    import json

    payload = json.loads(result.output)
    assert payload["data"]["row_count"] == 2
