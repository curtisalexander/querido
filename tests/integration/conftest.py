from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent.parent.parent / "data"

_skip = pytest.mark.skipif(
    not (DATA_DIR / "test.db").exists() or not (DATA_DIR / "test.duckdb").exists(),
    reason="Test databases not found. Run: uv run python scripts/init_test_data.py",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(_skip)


@pytest.fixture
def integration_sqlite_path() -> str:
    return str(DATA_DIR / "test.db")


@pytest.fixture
def integration_duckdb_path() -> str:
    return str(DATA_DIR / "test.duckdb")
