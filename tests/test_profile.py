import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app
from querido.core.profile import _unpack_single_row

runner = CliRunner()


# ---------------------------------------------------------------------------
# _unpack_single_row tests
# ---------------------------------------------------------------------------


class TestUnpackSingleRow:
    def test_numeric_column(self):
        row = {
            "total_rows": 100,
            "price__null_count": 5,
            "price__null_pct": 5.0,
            "price__distinct_count": 80,
            "price__min_val": 1.0,
            "price__max_val": 99.0,
            "price__mean_val": 50.0,
            "price__median_val": 48.0,
            "price__stddev_val": 25.0,
        }
        col_info = [{"name": "PRICE", "type": "FLOAT", "numeric": True}]
        result = _unpack_single_row(row, col_info)

        assert len(result) == 1
        r = result[0]
        assert r["column_name"] == "PRICE"
        assert r["column_type"] == "FLOAT"
        assert r["total_rows"] == 100
        assert r["distinct_count"] == 80
        assert r["min_val"] == 1.0
        assert r["max_val"] == 99.0
        assert r["min_length"] is None
        assert r["max_length"] is None

    def test_string_column(self):
        row = {
            "total_rows": 50,
            "email__null_count": 2,
            "email__null_pct": 4.0,
            "email__distinct_count": 48,
            "email__min_length": 5,
            "email__max_length": 30,
        }
        col_info = [{"name": "EMAIL", "type": "VARCHAR", "numeric": False}]
        result = _unpack_single_row(row, col_info)

        assert len(result) == 1
        r = result[0]
        assert r["column_name"] == "EMAIL"
        assert r["min_length"] == 5
        assert r["max_length"] == 30
        assert r["min_val"] is None
        assert r["max_val"] is None

    def test_multiple_columns(self):
        row = {
            "total_rows": 200,
            "id__null_count": 0,
            "id__null_pct": 0.0,
            "id__distinct_count": 200,
            "id__min_val": 1,
            "id__max_val": 200,
            "id__mean_val": 100.5,
            "id__median_val": 100.0,
            "id__stddev_val": 57.74,
            "name__null_count": 3,
            "name__null_pct": 1.5,
            "name__distinct_count": 150,
            "name__min_length": 2,
            "name__max_length": 50,
        }
        col_info = [
            {"name": "ID", "type": "NUMBER", "numeric": True},
            {"name": "NAME", "type": "VARCHAR", "numeric": False},
        ]
        result = _unpack_single_row(row, col_info)

        assert len(result) == 2
        assert result[0]["column_name"] == "ID"
        assert result[0]["distinct_count"] == 200
        assert result[1]["column_name"] == "NAME"
        assert result[1]["min_length"] == 2


def test_profile_sqlite(sqlite_path: str):
    result = runner.invoke(app, ["profile", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "Numeric Columns" in result.output


def test_profile_top_values(sqlite_path: str):
    result = runner.invoke(
        app,
        ["profile", "--connection", sqlite_path, "--table", "users", "--top", "3"],
    )
    assert result.exit_code == 0
    assert "Top values" in result.output
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_profile_top_zero_hides_frequencies(sqlite_path: str):
    result = runner.invoke(app, ["profile", "--connection", sqlite_path, "--table", "users"])
    assert result.exit_code == 0
    assert "Top values" not in result.output


def test_profile_sample_flag(sqlite_path: str):
    result = runner.invoke(
        app,
        ["profile", "--connection", sqlite_path, "--table", "users", "--sample", "1"],
    )
    assert result.exit_code == 0


def test_profile_no_sample_flag(sqlite_path: str):
    result = runner.invoke(
        app,
        ["profile", "--connection", sqlite_path, "--table", "users", "--no-sample"],
    )
    assert result.exit_code == 0


def test_profile_columns_filter(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "profile",
            "--connection",
            sqlite_path,
            "--table",
            "users",
            "--columns",
            "name",
        ],
    )
    assert result.exit_code == 0
    import json

    data = json.loads(result.output)
    col_names = [c["column_name"] for c in data["columns"]]
    assert "name" in col_names
    assert "id" not in col_names


@pytest.fixture
def string_only_sqlite(tmp_path: Path) -> str:
    db_path = str(tmp_path / "strings.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE names (first TEXT, last TEXT)")
    conn.execute("INSERT INTO names VALUES ('Alice', 'Smith')")
    conn.execute("INSERT INTO names VALUES ('Bob', 'Jones')")
    conn.commit()
    conn.close()
    return db_path


def test_profile_string_only_columns(string_only_sqlite: str):
    result = runner.invoke(
        app,
        ["profile", "--connection", string_only_sqlite, "--table", "names"],
    )
    assert result.exit_code == 0
    assert "String Columns" in result.output


def test_profile_duckdb(duckdb_path: str):
    result = runner.invoke(app, ["profile", "--connection", duckdb_path, "--table", "users"])
    assert result.exit_code == 0
    assert "Numeric Columns" in result.output


def test_profile_top_with_columns(sqlite_path: str):
    result = runner.invoke(
        app,
        [
            "profile",
            "--connection",
            sqlite_path,
            "--table",
            "users",
            "--columns",
            "name",
            "--top",
            "2",
        ],
    )
    assert result.exit_code == 0
    assert "Top values" in result.output
    assert "Alice" in result.output


def test_profile_exact_flag_accepted(sqlite_path: str):
    """The --exact flag is accepted (no-op on non-Snowflake backends)."""
    result = runner.invoke(
        app,
        ["profile", "--connection", sqlite_path, "--table", "users", "--exact"],
    )
    assert result.exit_code == 0
