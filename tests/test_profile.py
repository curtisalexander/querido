import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from querido.cli.main import app
from querido.core._utils import classify_columns
from querido.core._utils import unpack_single_row as _unpack_single_row

runner = CliRunner()


# ---------------------------------------------------------------------------
# _unpack_single_row tests
# ---------------------------------------------------------------------------


class TestUnpackSingleRow:
    # Single-column numeric/string tests were dropped (2026-04-17) — the
    # ``test_multiple_columns`` case below exercises both code paths in one
    # shot (numeric + string side-by-side), so they were redundant.

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

    data = json.loads(result.output)["data"]
    col_names = [c["column_name"] for c in data["columns"]]
    assert "name" in col_names
    assert "id" not in col_names


def test_profile_short_C_flag(sqlite_path: str):
    """``-C`` is the short form of ``--columns`` — parity with values/dist (R.8)."""
    result = runner.invoke(
        app,
        ["-f", "json", "profile", "-c", sqlite_path, "-t", "users", "-C", "name"],
    )
    assert result.exit_code == 0
    import json

    data = json.loads(result.output)["data"]
    col_names = [c["column_name"] for c in data["columns"]]
    assert col_names == ["name"]


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


# ``test_profile_duckdb`` dropped (2026-04-17) — output rendering is
# dialect-agnostic; sampling / classification tests below still exercise
# the DuckDB path where it actually diverges.


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
    data = json.loads(result.output)["data"]
    assert data["sampled"] is True


def test_no_sample_sqlite(big_sqlite: str):
    result = runner.invoke(
        app,
        ["--format", "json", "profile", "-c", big_sqlite, "-t", "big", "--no-sample"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
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
    data = json.loads(result.output)["data"]
    assert data["sampled"] is True
    assert data["sample_size"] == 500


def test_auto_sampling_duckdb(big_duckdb: str):
    result = runner.invoke(
        app,
        ["--format", "json", "profile", "-c", big_duckdb, "-t", "big"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["sampled"] is True


def test_no_sample_duckdb(big_duckdb: str):
    result = runner.invoke(
        app,
        ["--format", "json", "profile", "-c", big_duckdb, "-t", "big", "--no-sample"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
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
    data = json.loads(result.output)["data"]
    assert data["sampled"] is True
    assert data["sample_size"] == 500


# ---------------------------------------------------------------------------
# Quick profile (Tier 1) tests
# ---------------------------------------------------------------------------


def test_quick_profile_sqlite(sqlite_path: str):
    """--quick should produce output without min/max/mean columns."""
    result = runner.invoke(
        app,
        ["--format", "json", "profile", "-c", sqlite_path, "-t", "users", "--quick"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    # All columns should have null_count and distinct_count
    for col in data["columns"]:
        assert "null_count" in col
        assert "distinct_count" in col
        # Quick mode should not compute expensive stats
        assert col.get("min_val") is None
        assert col.get("max_val") is None
        assert col.get("mean_val") is None


def test_no_quick_override(sqlite_path: str):
    """--no-quick should force full profile even on wide tables."""
    result = runner.invoke(
        app,
        ["--format", "json", "profile", "-c", sqlite_path, "-t", "users", "--no-quick"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    # Should have numeric stats for numeric columns
    numeric_cols = [c for c in data["columns"] if c.get("min_val") is not None]
    assert len(numeric_cols) > 0


# ``test_quick_profile_duckdb`` dropped (2026-04-17) — ``--quick`` changes
# the Jinja template used, not dialect-specific SQL.  The SQLite-backed
# test above proves the behavior.


# ---------------------------------------------------------------------------
# Auto-classification tests
# ---------------------------------------------------------------------------


class TestClassifyColumns:
    @pytest.mark.parametrize(
        ("name", "col_type", "numeric", "distinct", "null_pct", "expected_category"),
        [
            ("status", "VARCHAR", False, 1, 0, "constant"),
            ("legacy", "VARCHAR", False, 5, 95, "sparse"),
            ("user_id", "VARCHAR", False, 98, 0, "high_cardinality"),
            ("created_at", "TIMESTAMP", False, 80, 0, "time"),
            ("amount", "FLOAT", True, 80, 0, "measure"),
            ("country", "VARCHAR", False, 10, 5, "low_cardinality"),
        ],
        ids=["constant", "sparse", "high_cardinality", "time", "measure", "low_cardinality"],
    )
    def test_single_rule_category(
        self,
        name: str,
        col_type: str,
        numeric: bool,
        distinct: int,
        null_pct: float,
        expected_category: str,
    ) -> None:
        stats = [
            {
                "column_name": name,
                "column_type": col_type,
                "distinct_count": distinct,
                "null_pct": null_pct,
            }
        ]
        col_info = [{"name": name, "type": col_type, "numeric": numeric}]
        result = classify_columns(stats, col_info, row_count=100)
        assert result["column_category"][name] == expected_category

    def test_mixed_columns(self):
        stats = [
            {
                "column_name": "id",
                "column_type": "INTEGER",
                "distinct_count": 1000,
                "null_pct": 0,
            },
            {
                "column_name": "status",
                "column_type": "VARCHAR",
                "distinct_count": 1,
                "null_pct": 0,
            },
            {
                "column_name": "amount",
                "column_type": "FLOAT",
                "distinct_count": 500,
                "null_pct": 2,
            },
            {
                "column_name": "old_field",
                "column_type": "VARCHAR",
                "distinct_count": 3,
                "null_pct": 99,
            },
        ]
        col_info = [
            {"name": "id", "type": "INTEGER", "numeric": True},
            {"name": "status", "type": "VARCHAR", "numeric": False},
            {"name": "amount", "type": "FLOAT", "numeric": True},
            {"name": "old_field", "type": "VARCHAR", "numeric": False},
        ]
        result = classify_columns(stats, col_info, row_count=1000)
        assert result["column_category"]["status"] == "constant"
        assert result["column_category"]["old_field"] == "sparse"
        assert result["column_category"]["amount"] == "measure"

    def test_empty_categories_excluded(self):
        stats = [
            {
                "column_name": "x",
                "column_type": "VARCHAR",
                "distinct_count": 5,
                "null_pct": 0,
            }
        ]
        col_info = [{"name": "x", "type": "VARCHAR", "numeric": False}]
        result = classify_columns(stats, col_info, row_count=100)
        # Only low_cardinality should be present
        assert "constant" not in result["categories"]
        assert "sparse" not in result["categories"]
        assert "low_cardinality" in result["categories"]


def test_classify_cli_sqlite(sqlite_path: str):
    """--classify should produce classification output."""
    result = runner.invoke(
        app,
        ["profile", "-c", sqlite_path, "-t", "users", "--classify"],
    )
    assert result.exit_code == 0
    # Should have category labels in output
    assert "columns)" in result.output


def test_classify_cli_json(sqlite_path: str):
    """--classify --format json should produce structured JSON."""
    result = runner.invoke(
        app,
        ["--format", "json", "profile", "-c", sqlite_path, "-t", "users", "--classify"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert "categories" in data
    assert "column_category" in data
    assert data["table"] == "users"


# ---------------------------------------------------------------------------
# Column sets persistence tests
# ---------------------------------------------------------------------------


def test_column_set_save_load_delete(tmp_path: Path):
    from querido.config import delete_column_set, load_column_set, save_column_set

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    save_column_set("myconn", "orders", "default", ["id", "amount", "status"], config_dir)
    cols = load_column_set("myconn", "orders", "default", config_dir)
    assert cols == ["id", "amount", "status"]

    # Overwrite
    save_column_set("myconn", "orders", "default", ["id", "amount"], config_dir)
    cols = load_column_set("myconn", "orders", "default", config_dir)
    assert cols == ["id", "amount"]

    # Delete
    assert delete_column_set("myconn", "orders", "default", config_dir) is True
    assert load_column_set("myconn", "orders", "default", config_dir) is None
    assert delete_column_set("myconn", "orders", "default", config_dir) is False


def test_column_set_list(tmp_path: Path):
    from querido.config import list_column_sets, save_column_set

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    save_column_set("conn1", "t1", "s1", ["a", "b"], config_dir)
    save_column_set("conn1", "t2", "s1", ["c"], config_dir)
    save_column_set("conn2", "t1", "s1", ["d"], config_dir)

    # All
    all_sets = list_column_sets(config_dir=config_dir)
    assert len(all_sets) == 3

    # Filter by connection
    conn1_sets = list_column_sets(connection="conn1", config_dir=config_dir)
    assert len(conn1_sets) == 2

    # Filter by table
    t1_sets = list_column_sets(table="t1", config_dir=config_dir)
    assert len(t1_sets) == 2

    # Filter by both
    specific = list_column_sets(connection="conn1", table="t1", config_dir=config_dir)
    assert len(specific) == 1


def test_column_set_cli_save_and_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """CLI column-set save + list round-trip."""
    monkeypatch.setenv("QDO_CONFIG", str(tmp_path))

    result = runner.invoke(
        app,
        [
            "config",
            "column-set",
            "save",
            "-c",
            "test_conn",
            "-t",
            "orders",
            "-n",
            "default",
            "--columns",
            "id,amount,status",
        ],
    )
    assert result.exit_code == 0

    result = runner.invoke(app, ["config", "column-set", "list"])
    assert result.exit_code == 0
    assert "test_conn" in result.output
    assert "orders" in result.output


def test_profile_column_set_flag(
    sqlite_path: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """--column-set should resolve to saved columns."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setenv("QDO_CONFIG", str(config_dir))

    from querido.config import save_column_set

    save_column_set(sqlite_path, "users", "names_only", ["name"], config_dir)

    result = runner.invoke(
        app,
        [
            "--format",
            "json",
            "profile",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "--column-set",
            "names_only",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    col_names = [c["column_name"] for c in data["columns"]]
    assert col_names == ["name"]


def test_columns_and_column_set_mutually_exclusive(sqlite_path: str):
    """Using both --columns and --column-set should fail."""
    result = runner.invoke(
        app,
        [
            "profile",
            "-c",
            sqlite_path,
            "-t",
            "users",
            "--columns",
            "name",
            "--column-set",
            "default",
        ],
    )
    assert result.exit_code != 0
