"""Tests for TUI widgets and app using Textual's pilot testing framework."""

import sqlite3
from pathlib import Path

import pytest

# pytest-asyncio is required for async test functions but lives in the dev
# dependency group.  Skip the entire module gracefully when it's absent so
# that `pip install -e ".[all]" && pytest` doesn't fail unexpectedly.
pytest.importorskip("pytest_asyncio")


@pytest.fixture
def sqlite_connector(tmp_path: Path):
    """Create a SQLite connector with test data."""
    db_path = str(tmp_path / "tui_test.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE products"
        " (id INTEGER PRIMARY KEY, name TEXT NOT NULL,"
        " price REAL, category TEXT)"
    )
    for i in range(1, 51):
        conn.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?)",
            (i, f"Product {i}", 10.0 + i * 0.5, "A" if i % 2 == 0 else "B"),
        )
    conn.commit()
    conn.close()

    from querido.connectors.sqlite import SQLiteConnector

    return SQLiteConnector(db_path)


@pytest.fixture
def duckdb_connector(tmp_path: Path):
    """Create a DuckDB connector with test data."""
    import duckdb

    db_path = str(tmp_path / "tui_test.duckdb")
    conn = duckdb.connect(db_path)
    conn.execute(
        "CREATE TABLE products"
        " (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL,"
        " price DOUBLE, category VARCHAR)"
    )
    for i in range(1, 51):
        conn.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?)",
            (i, f"Product {i}", 10.0 + i * 0.5, "A" if i % 2 == 0 else "B"),
        )
    conn.close()

    from querido.connectors.duckdb import DuckDBConnector

    return DuckDBConnector(db_path)


async def test_app_launches_with_data(sqlite_connector):
    """App launches and populates DataTable with rows."""
    from textual.widgets import DataTable

    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products", max_rows=100)
    async with app.run_test():
        dt = app.query_one("#data-table", DataTable)
        assert dt.row_count == 50
        assert len(dt.columns) == 4


async def test_app_title(sqlite_connector):
    """App title includes table name."""
    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test():
        assert "products" in app.title


async def test_app_max_rows_limit(sqlite_connector):
    """App respects max_rows limit."""
    from textual.widgets import DataTable

    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products", max_rows=10)
    async with app.run_test():
        dt = app.query_one("#data-table", DataTable)
        assert dt.row_count == 10


async def test_sort_via_action(sqlite_connector):
    """Sort action updates internal sort state."""
    from textual.widgets import DataTable

    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products", max_rows=100)
    async with app.run_test(size=(120, 40)) as pilot:
        # Initially no sort
        assert app._sort_column is None
        assert len(app._rows) == 50

        # Simulate sorting by clicking a column header
        dt = app.query_one("#data-table", DataTable)
        first_col_key = next(iter(dt.columns.keys()))
        app._sort_column = str(first_col_key)
        app._sort_reverse = False
        app._apply_sort()
        await pilot.pause()

        assert app._sort_column == str(first_col_key)
        assert app._sort_reverse is False


async def test_inspect_via_action(sqlite_connector):
    """action_inspect opens the InspectScreen."""
    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test(size=(120, 40)) as pilot:
        app.action_inspect()
        await pilot.pause()
        from querido.tui.screens.inspect import InspectScreen

        assert isinstance(app.screen, InspectScreen)

        await app.screen.action_dismiss()
        await pilot.pause()
        assert not isinstance(app.screen, InspectScreen)


async def test_help_via_action(sqlite_connector):
    """action_help opens the HelpScreen."""
    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test(size=(120, 40)) as pilot:
        app.action_help()
        await pilot.pause()
        from querido.tui.screens.help import HelpScreen

        assert isinstance(app.screen, HelpScreen)

        await app.screen.action_dismiss()
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


async def test_sidebar_via_action(sqlite_connector):
    """action_sidebar toggles the metadata sidebar."""
    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test(size=(120, 40)) as pilot:
        sidebar = app.query_one("#sidebar")
        assert sidebar.has_class("hidden")

        app.action_sidebar()
        await pilot.pause()
        assert not sidebar.has_class("hidden")

        app.action_sidebar()
        await pilot.pause()
        assert sidebar.has_class("hidden")


async def test_status_bar_shows_info(sqlite_connector):
    """Status bar displays table name and row count."""
    from querido.tui.app import ExploreApp
    from querido.tui.widgets.status_bar import StatusBar

    app = ExploreApp(connector=sqlite_connector, table="products", max_rows=100)
    async with app.run_test():
        status = app.query_one("#status-bar", StatusBar)
        text = status._last_text
        assert "products" in text
        assert "50" in text


async def test_filter_bar_focus(sqlite_connector):
    """action_filter focuses the filter input."""
    from textual.widgets import Input

    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test(size=(120, 40)) as pilot:
        app.action_filter()
        await pilot.pause()
        focused = app.focused
        assert isinstance(focused, Input)


async def test_duckdb_app_launches(duckdb_connector):
    """App works with DuckDB connector too."""
    from textual.widgets import DataTable

    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=duckdb_connector, table="products", max_rows=100)
    async with app.run_test():
        dt = app.query_one("#data-table", DataTable)
        assert dt.row_count == 50
        assert len(dt.columns) == 4


async def test_columns_loaded(sqlite_connector):
    """App loads column metadata on mount."""
    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test():
        assert len(app._columns) == 4
        col_names = [c["name"] for c in app._columns]
        assert "id" in col_names
        assert "price" in col_names


async def test_profile_via_action(sqlite_connector):
    """action_profile opens the ProfileScreen."""
    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test(size=(120, 40)) as pilot:
        app.action_profile()
        await pilot.pause()
        from querido.tui.screens.profile import ProfileScreen

        assert isinstance(app.screen, ProfileScreen)

        await app.screen.action_dismiss()
        await pilot.pause()
        assert not isinstance(app.screen, ProfileScreen)


async def test_profile_populates_data(sqlite_connector):
    """ProfileScreen populates DataTable with column statistics."""
    from textual.widgets import DataTable

    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test(size=(120, 40)) as pilot:
        app.action_profile()
        await pilot.pause()

        dt = app.screen.query_one("#profile-table", DataTable)
        assert dt.row_count == 4  # 4 columns in products table
        assert len(dt.columns) == 10


async def test_dist_column_picker(sqlite_connector):
    """action_distribution opens the column picker."""
    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test(size=(120, 40)) as pilot:
        app.action_distribution()
        await pilot.pause()
        from querido.tui.screens.column_picker import ColumnPickerScreen

        assert isinstance(app.screen, ColumnPickerScreen)


def test_status_bar_widget():
    """StatusBar.update_status builds correct text."""
    from querido.tui.widgets.status_bar import StatusBar

    sb = StatusBar()
    sb.update_status(table="users", displayed=100, total=5000, filtered=False)
    text = sb._last_text
    assert "users" in text
    assert "100" in text
    assert "5,000" in text


def test_status_bar_filtered():
    """StatusBar shows filtered indicator."""
    from querido.tui.widgets.status_bar import StatusBar

    sb = StatusBar()
    sb.update_status(table="t", displayed=10, total=100, filtered=True)
    text = sb._last_text
    assert "filtered" in text.lower()


def test_status_bar_sorted():
    """StatusBar shows sort info."""
    from querido.tui.widgets.status_bar import StatusBar

    sb = StatusBar()
    sb.update_status(
        table="t", displayed=10, total=100, filtered=False, sort_col="age", sort_dir="asc"
    )
    text = sb._last_text
    assert "age" in text
    assert "↑" in text
