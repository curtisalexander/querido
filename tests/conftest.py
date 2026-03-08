import sqlite3
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent.parent / "data"

integration_skip = pytest.mark.skipif(
    not (DATA_DIR / "test.db").exists() or not (DATA_DIR / "test.duckdb").exists(),
    reason="Test databases not found. Run: uv run python scripts/init_test_data.py",
)


# --- Unit test fixtures (tiny, in tmp_path) ---


@pytest.fixture
def sqlite_path(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INTEGER)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def duckdb_path(tmp_path: Path) -> str:
    import duckdb

    db_path = str(tmp_path / "test.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, age INTEGER)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
    conn.close()
    return db_path


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


# --- Integration test fixtures (real data, requires init-test-data) ---


@pytest.fixture
def integration_sqlite_path() -> str:
    return str(DATA_DIR / "test.db")


@pytest.fixture
def integration_duckdb_path() -> str:
    return str(DATA_DIR / "test.duckdb")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "integration: requires test databases from init_test_data.py"
    )
