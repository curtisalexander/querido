import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app
from querido.core._utils import unpack_single_row as _unpack_single_row

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


def test_profile_batched_produces_all_columns():
    """Column batching should produce stats for every column in order.

    Uses DuckDB single-threaded (DuckDB is not thread-safe), so we test
    the batching/merge logic by calling the internal helpers directly.
    """
    from querido.connectors.duckdb import DuckDBConnector
    from querido.core._utils import (
        build_col_info as _build_col_info,
    )
    from querido.core._utils import (
        unpack_single_row as _unpack_single_row,
    )
    from querido.sql.renderer import render_template

    with DuckDBConnector() as connector:
        # Create a wide table with 30 columns
        cols = ", ".join(f"c{i} INTEGER" for i in range(30))
        connector.conn.execute(f"CREATE TABLE wide ({cols})")
        vals = ", ".join("1" for _ in range(30))
        connector.conn.execute(f"INSERT INTO wide VALUES ({vals})")

        col_meta = connector.get_columns("wide")
        col_info = _build_col_info(col_meta)

        # Simulate batched profiling: split into batches, run each, merge
        batch_size = 10
        batches = [col_info[i : i + batch_size] for i in range(0, len(col_info), batch_size)]
        all_stats: list[dict] = []
        for batch in batches:
            sql = render_template(
                "profile", connector.dialect, columns=batch, source="wide", approx=True
            )
            raw = connector.execute(sql)
            assert len(raw) == 1
            assert "total_rows" in raw[0]
            all_stats.extend(_unpack_single_row(raw[0], batch))

        assert len(all_stats) == 30
        for i, s in enumerate(all_stats):
            assert s["column_name"] == f"c{i}"


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


def test_profile_empty_table(tmp_path: Path):
    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE empty_t (id INTEGER PRIMARY KEY, name TEXT NOT NULL, score REAL)")
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["profile", "-c", db_path, "-t", "empty_t"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Sampling (large tables)
# ---------------------------------------------------------------------------


ROW_COUNT = 1_100_000


@pytest.fixture(scope="module")
def big_sqlite(tmp_path_factory: pytest.TempPathFactory) -> str:
    db_path = str(tmp_path_factory.mktemp("big") / "big.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE big (id INTEGER PRIMARY KEY AUTOINCREMENT, val REAL)")
    conn.executemany("INSERT INTO big (val) VALUES (?)", ((i * 0.1,) for i in range(ROW_COUNT)))
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture(scope="module")
def big_duckdb(tmp_path_factory: pytest.TempPathFactory) -> str:
    import duckdb

    db_path = str(tmp_path_factory.mktemp("big") / "big.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE big (id INTEGER, val DOUBLE)")
    conn.execute(
        f"INSERT INTO big SELECT i, i * 0.1 FROM generate_series(0, {ROW_COUNT - 1}) t(i)"
    )
    conn.close()
    return db_path


def test_auto_sampling_sqlite(big_sqlite: str):
    result = runner.invoke(
        app,
        ["--format", "json", "profile", "-c", big_sqlite, "-t", "big"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["sampled"] is True


def test_no_sample_sqlite(big_sqlite: str):
    result = runner.invoke(
        app,
        ["--format", "json", "profile", "-c", big_sqlite, "-t", "big", "--no-sample"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["sampled"] is False


def test_explicit_sample_size_sqlite(big_sqlite: str):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "profile",
            "-c",
            big_sqlite,
            "-t",
            "big",
            "--sample",
            "500",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["sampled"] is True
    assert data["sample_size"] == 500


def test_auto_sampling_duckdb(big_duckdb: str):
    result = runner.invoke(
        app,
        ["--format", "json", "profile", "-c", big_duckdb, "-t", "big"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["sampled"] is True


def test_no_sample_duckdb(big_duckdb: str):
    result = runner.invoke(
        app,
        ["--format", "json", "profile", "-c", big_duckdb, "-t", "big", "--no-sample"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["sampled"] is False


def test_explicit_sample_size_duckdb(big_duckdb: str):
    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "profile",
            "-c",
            big_duckdb,
            "-t",
            "big",
            "--sample",
            "500",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["sampled"] is True
    assert data["sample_size"] == 500
