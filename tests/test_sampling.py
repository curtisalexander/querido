import json
import sqlite3

import pytest
from typer.testing import CliRunner

from querido.cli.main import app

runner = CliRunner()

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
