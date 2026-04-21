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
            (
                i,
                f"Product {i}",
                10.0 + i * 0.5,
                None if i % 4 == 0 else ("A" if i % 2 == 0 else "B"),
            ),
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
            (
                i,
                f"Product {i}",
                10.0 + i * 0.5,
                None if i % 4 == 0 else ("A" if i % 2 == 0 else "B"),
            ),
        )
    conn.close()

    from querido.connectors.duckdb import DuckDBConnector

    return DuckDBConnector(db_path)


@pytest.fixture
def wide_sqlite_connector(tmp_path: Path):
    """Wide-table fixture with sparse and constant columns for triage ordering."""
    db_path = str(tmp_path / "wide_tui_test.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE events ("
        "id INTEGER PRIMARY KEY, "
        "status TEXT, "
        "amount REAL, "
        "created_at TEXT, "
        "notes TEXT, "
        "country TEXT)"
    )
    rows = [
        (1, "new", 10.0, "2024-01-01", None, "US"),
        (2, "new", 15.0, "2024-01-02", None, "US"),
        (3, "done", 15.0, "2024-01-03", None, "US"),
        (4, "done", 25.0, "2024-01-04", None, "US"),
        (5, "new", 25.0, "2024-01-04", "follow up", "US"),
    ]
    conn.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()

    from querido.connectors.sqlite import SQLiteConnector

    return SQLiteConnector(db_path)


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

    app = ExploreApp(
        connector=sqlite_connector,
        table="products",
        max_rows=100,
        connection_name="demo",
    )
    async with app.run_test():
        status = app.query_one("#status-bar", StatusBar)
        text = status._last_text
        assert "demo" in text
        assert "products" in text
        assert "50" in text
        assert "sample exact" in text
        assert "meta no" in text


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
    from textual.widgets import DataTable, Static

    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test(size=(120, 40)) as pilot:
        app.action_profile()
        await pilot.pause()

        dt = app.screen.query_one("#profile-table", DataTable)
        summary = app.screen.query_one("#profile-summary", Static)
        assert dt.row_count == 4  # 4 columns in products table
        assert len(dt.columns) == 10
        assert "Full profile for all 4 columns" in str(summary.render())


async def test_profile_wide_table_shows_triage_selector(sqlite_connector, monkeypatch):
    """Wide-table profile path explains triage defaults before full profiling."""
    from textual.widgets import Static

    from querido.tui.app import ExploreApp
    from querido.tui.screens.column_selector import ColumnSelectorScreen

    monkeypatch.setenv("QDO_QUICK_THRESHOLD", "4")

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test(size=(120, 40)) as pilot:
        app.action_profile()
        await pilot.pause()
        await pilot.pause()

        assert isinstance(app.screen, ColumnSelectorScreen)
        title = app.screen.query_one("#selector-title", Static)
        summary = app.screen.query_one("#selector-summary", Static)
        footer = app.screen.query_one("#selector-footer", Static)
        assert "Wide-table triage" in str(title.render())
        assert "recommended columns are pre-selected" in str(summary.render())
        assert "High Cardinality" in str(summary.render())
        assert "Low Cardinality" in str(summary.render())
        assert "Keep quick view" in str(footer.render())


async def test_profile_wide_table_cancel_keeps_quick_view(sqlite_connector, monkeypatch):
    """Cancelling wide-table triage leaves the quick profile visible with guidance."""
    from textual.widgets import DataTable, Static

    from querido.tui.app import ExploreApp
    from querido.tui.screens.column_selector import ColumnSelectorScreen

    monkeypatch.setenv("QDO_QUICK_THRESHOLD", "4")

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test(size=(120, 40)) as pilot:
        app.action_profile()
        await pilot.pause()
        await pilot.pause()

        selector = app.screen
        assert isinstance(selector, ColumnSelectorScreen)
        selector.action_cancel()
        await pilot.pause()

        title = app.screen.query_one("#profile-title", Static)
        summary = app.screen.query_one("#profile-summary", Static)
        dt = app.screen.query_one("#profile-table", DataTable)
        assert "quick mode" in str(title.render()).lower()
        assert "Quick profile: nulls and distinct counts only." in str(summary.render())
        assert dt.row_count == 4


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
    sb.update_status(
        connection="warehouse",
        table="users",
        displayed=100,
        total=5000,
        filtered=False,
        sampled=False,
        metadata_present=True,
        focus_col="users_id",
        focus_category="high-card",
        wide_mode=True,
    )
    text = sb._last_text
    assert "conn warehouse" in text
    assert "table users" in text
    assert "rows 100/5,000" in text
    assert "mode triage" in text
    assert "sample exact" in text
    assert "meta yes" in text
    assert "focus users_id · high-card" in text


def test_column_selector_summary_and_labels():
    """Wide-table selector copy makes default triage legible."""
    from querido.tui.screens.column_selector import _selection_label, _selection_summary

    summary = _selection_summary(
        {
            "categories": {
                "measure": ["price"],
                "low_cardinality": ["category"],
                "sparse": ["notes"],
                "constant": ["country"],
            }
        }
    )
    assert "2 recommended columns are pre-selected" in summary
    assert "2 sparse/constant columns are skipped by default" in summary
    assert "Measure (numeric): 1" in summary

    recommended = _selection_label(
        "price",
        {"column_type": "REAL", "null_pct": 0.0, "distinct_count": 50},
        recommended=True,
    )
    skipped = _selection_label(
        "country",
        {"column_type": "TEXT", "null_pct": 0.0, "distinct_count": 1},
        recommended=False,
    )
    assert recommended.startswith("[rec] price")
    assert skipped.startswith("[skip] country")


def test_display_column_names_moves_sparse_and_constant_last():
    """Wide-table ordering keeps recommended columns ahead of sparse/constant ones."""
    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=None, table="demo")  # type: ignore[arg-type]
    app._row_count = 5
    app._columns = [
        {"name": "id", "type": "INTEGER", "null_pct": 0.0, "distinct_count": 5},
        {"name": "notes", "type": "TEXT", "null_pct": 95.0, "distinct_count": 2},
        {"name": "country", "type": "TEXT", "null_pct": 0.0, "distinct_count": 1},
        {"name": "status", "type": "TEXT", "null_pct": 0.0, "distinct_count": 2},
        {"name": "amount", "type": "REAL", "null_pct": 0.0, "distinct_count": 4},
        {"name": "created_at", "type": "TEXT", "null_pct": 0.0, "distinct_count": 4},
    ]

    import os

    old = os.environ.get("QDO_QUICK_THRESHOLD")
    os.environ["QDO_QUICK_THRESHOLD"] = "6"
    try:
        ordered = app._display_column_names()
    finally:
        if old is None:
            os.environ.pop("QDO_QUICK_THRESHOLD", None)
        else:
            os.environ["QDO_QUICK_THRESHOLD"] = old

    assert ordered[:4] == ["created_at", "amount", "status", "id"]
    assert ordered[-2:] == ["notes", "country"]


def test_status_bar_filtered():
    """StatusBar shows filtered indicator."""
    from querido.tui.widgets.status_bar import StatusBar

    sb = StatusBar()
    sb.update_status(table="t", displayed=10, total=100, filtered=True)
    text = sb._last_text
    assert "filter on" in text.lower()


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


def test_metadata_sidebar_widget():
    """Sidebar renders selected-column facts and quality flags."""
    from querido.tui.widgets.sidebar import MetadataSidebar

    sidebar = MetadataSidebar()
    sidebar.show_column(
        table="products",
        connection_name="demo",
        metadata_present=True,
        category="low-card",
        recommended=True,
        column={
            "name": "category",
            "type": "TEXT",
            "nullable": False,
            "distinct_count": 2,
            "null_count": 0,
            "null_pct": 0.0,
            "sample_values": ["A", "B"],
            "description": "Product grouping",
            "valid_values": ["A", "B"],
        },
        quality={
            "status": "warn",
            "issues": ["unexpected category values present"],
        },
    )
    text = sidebar._last_text
    assert "products" in text
    assert "demo" in text
    assert "category" in text
    assert "TEXT  •  not null  •  low-card  •  recommended" in text
    assert "Profile" in text
    assert "Signals" in text
    assert "Quality" in text
    assert "Product grouping" in text
    assert "allowed: A, B" in text
    assert "unexpected category values present" in text


async def test_sidebar_shows_selected_column_metadata(sqlite_connector, tmp_path, monkeypatch):
    """Sidebar reflects selected-column context and stored metadata."""
    from querido.tui.app import ExploreApp
    from querido.tui.widgets.sidebar import MetadataSidebar
    from querido.tui.widgets.status_bar import StatusBar

    monkeypatch.chdir(tmp_path)
    meta_dir = tmp_path / ".qdo" / "metadata" / "demo"
    meta_dir.mkdir(parents=True)
    (meta_dir / "products.yaml").write_text(
        """
table: products
connection: demo
columns:
  - name: category
    description: Product grouping
    valid_values:
      - A
      - B
""".strip()
        + "\n"
    )

    app = ExploreApp(connector=sqlite_connector, table="products", connection_name="demo")
    async with app.run_test(size=(120, 40)) as pilot:
        app._set_selected_column("category")
        app.action_sidebar()
        await pilot.pause()

        sidebar = app.query_one("#sidebar", MetadataSidebar)
        status = app.query_one("#status-bar", StatusBar)
        assert "category" in sidebar._last_text
        assert "TEXT  •  nullable  •  low-card  •  recommended" in sidebar._last_text
        assert "Product grouping" in sidebar._last_text
        assert "allowed: A, B" in sidebar._last_text
        assert "meta yes" in status._last_text
        assert "focus category · low-card" in status._last_text


async def test_wide_table_headers_move_sparse_columns_last(wide_sqlite_connector, monkeypatch):
    """Wide-table grid ordering should push sparse/constant columns to the end."""
    from textual.widgets import DataTable

    from querido.tui.app import ExploreApp

    monkeypatch.setenv("QDO_QUICK_THRESHOLD", "6")

    app = ExploreApp(connector=wide_sqlite_connector, table="events")
    async with app.run_test():
        dt = app.query_one("#data-table", DataTable)
        labels = [column.label.plain for column in dt.columns.values()]
        assert labels[:4] == ["created_at", "amount", "status", "id [PK]"]
        assert labels[-2:] == ["notes [!]", "country"]


async def test_wide_table_status_and_sidebar_show_triage_context(
    wide_sqlite_connector, monkeypatch
):
    """Wide-table app surfaces category and triage hints outside the profile flow."""
    from querido.tui.app import ExploreApp
    from querido.tui.widgets.sidebar import MetadataSidebar
    from querido.tui.widgets.status_bar import StatusBar

    monkeypatch.setenv("QDO_QUICK_THRESHOLD", "6")

    app = ExploreApp(connector=wide_sqlite_connector, table="events", connection_name="wide-demo")
    async with app.run_test(size=(120, 40)) as pilot:
        app._set_selected_column("notes")
        app.action_sidebar()
        await pilot.pause()

        status = app.query_one("#status-bar", StatusBar)
        sidebar = app.query_one("#sidebar", MetadataSidebar)
        assert "mode triage" in status._last_text
        assert "focus notes · constant" in status._last_text
        assert "TEXT  •  nullable  •  constant  •  background" in sidebar._last_text


async def test_table_headers_show_semantic_badges(sqlite_connector):
    """DataTable headers expose PK and warning badges."""
    from textual.widgets import DataTable

    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test():
        dt = app.query_one("#data-table", DataTable)
        columns = list(dt.columns.values())
        id_label = columns[0].label
        category_label = columns[3].label
        assert id_label.plain == "id [PK]"
        assert category_label.plain == "category [!]"


async def test_sort_updates_header_and_null_rendering(sqlite_connector):
    """Sorted columns get an arrow and null cells render explicitly."""
    from textual.coordinate import Coordinate
    from textual.widgets import DataTable

    from querido.tui.app import ExploreApp

    app = ExploreApp(connector=sqlite_connector, table="products")
    async with app.run_test(size=(120, 40)) as pilot:
        dt = app.query_one("#data-table", DataTable)
        app._sort_column = "category"
        app._sort_reverse = False
        app._apply_sort()
        app._populate_table()
        await pilot.pause()

        category_label = list(dt.columns.values())[3].label
        assert category_label.plain == "category [!] ↑"
        rendered_values = [
            getattr(
                dt.get_cell_at(Coordinate(row_index, 3)),
                "plain",
                str(dt.get_cell_at(Coordinate(row_index, 3))),
            )
            for row_index in range(dt.row_count)
        ]
        assert "NULL" in rendered_values
