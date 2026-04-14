import sqlite3
from pathlib import Path

import pytest


def create_sqlite_db(
    db_path: str,
    *,
    tables: dict[str, list[str]] | None = None,
) -> str:
    """Create a SQLite database with the given tables and data.

    *tables* maps table DDL to a list of INSERT statements.
    If None, creates a default ``users`` table with 2 rows.
    """
    if tables is None:
        tables = {
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER)": [
                "INSERT INTO users VALUES (1, 'Alice', 30)",
                "INSERT INTO users VALUES (2, 'Bob', 25)",
            ],
        }
    conn = sqlite3.connect(db_path)
    for ddl, inserts in tables.items():
        conn.execute(ddl)
        for ins in inserts:
            conn.execute(ins)
    conn.commit()
    conn.close()
    return db_path


def create_duckdb_db(
    db_path: str,
    *,
    tables: dict[str, list[str]] | None = None,
) -> str:
    """Create a DuckDB database with the given tables and data.

    *tables* maps table DDL to a list of INSERT statements.
    If None, creates a default ``users`` table with 2 rows.
    """
    import duckdb

    if tables is None:
        tables = {
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, age INTEGER)": [
                "INSERT INTO users VALUES (1, 'Alice', 30)",
                "INSERT INTO users VALUES (2, 'Bob', 25)",
            ],
        }
    conn = duckdb.connect(db_path)
    for ddl, inserts in tables.items():
        conn.execute(ddl)
        for ins in inserts:
            conn.execute(ins)
    conn.close()
    return db_path


# --- Unit test fixtures (tiny, in tmp_path) ---


@pytest.fixture
def sqlite_path(tmp_path: Path) -> str:
    return create_sqlite_db(str(tmp_path / "test.db"))


@pytest.fixture
def make_sqlite_db():
    """Return the ``create_sqlite_db`` factory as a fixture.

    Lets test modules create additional SQLite databases (e.g. a second
    connection for bundle import tests) without importing private helpers
    from conftest.py — the import path isn't uniformly resolvable across
    pytest rootdir configurations and ty's module resolver.
    """
    return create_sqlite_db


@pytest.fixture
def duckdb_path(tmp_path: Path) -> str:
    return create_duckdb_db(str(tmp_path / "test.duckdb"))


@pytest.fixture
def duckdb_with_comments_path(tmp_path: Path) -> str:
    """DuckDB database with table and column comments set."""
    import duckdb

    db_path = str(tmp_path / "commented.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, age INTEGER)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
    conn.execute("COMMENT ON TABLE users IS 'Application user accounts'")
    conn.execute("COMMENT ON COLUMN users.name IS 'Full legal name'")
    conn.execute("COMMENT ON COLUMN users.age IS 'Age in years'")
    conn.close()
    return db_path


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "integration: requires test databases from init_test_data.py"
    )
