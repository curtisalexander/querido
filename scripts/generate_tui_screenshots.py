from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "docs" / "examples" / "screenshots"


def _build_wide_demo_db(path: Path) -> None:
    conn = sqlite3.connect(path)
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


async def _capture_orders_main() -> None:
    from querido.connectors.sqlite import SQLiteConnector
    from querido.tui.app import ExploreApp

    connector = SQLiteConnector(str(REPO_ROOT / "data" / "test.db"))
    try:
        app = ExploreApp(connector=connector, table="orders", max_rows=18, connection_name="test")
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            app.save_screenshot(filename="explore-orders-main.svg", path=str(OUTPUT_DIR))
    finally:
        connector.close()


async def _capture_orders_sidebar() -> None:
    from querido.connectors.sqlite import SQLiteConnector
    from querido.tui.app import ExploreApp

    connector = SQLiteConnector(str(REPO_ROOT / "data" / "test.db"))
    try:
        app = ExploreApp(connector=connector, table="orders", max_rows=18, connection_name="test")
        async with app.run_test(size=(140, 40)) as pilot:
            app._set_selected_column("status")
            app.action_sidebar()
            await pilot.pause()
            app.save_screenshot(filename="explore-orders-sidebar.svg", path=str(OUTPUT_DIR))
    finally:
        connector.close()


async def _capture_wide_triage() -> None:
    from querido.connectors.sqlite import SQLiteConnector
    from querido.tui.app import ExploreApp

    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "wide-demo.db"
        _build_wide_demo_db(db_path)
        connector = SQLiteConnector(str(db_path))
        old_threshold = os.environ.get("QDO_QUICK_THRESHOLD")
        os.environ["QDO_QUICK_THRESHOLD"] = "6"
        try:
            app = ExploreApp(
                connector=connector,
                table="events",
                max_rows=10,
                connection_name="wide-demo",
            )
            async with app.run_test(size=(140, 40)) as pilot:
                app.action_profile()
                await pilot.pause()
                await pilot.pause()
                app.save_screenshot(filename="explore-wide-triage.svg", path=str(OUTPUT_DIR))
        finally:
            if old_threshold is None:
                os.environ.pop("QDO_QUICK_THRESHOLD", None)
            else:
                os.environ["QDO_QUICK_THRESHOLD"] = old_threshold
            connector.close()


async def _main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    await _capture_orders_main()
    await _capture_orders_sidebar()
    await _capture_wide_triage()


if __name__ == "__main__":
    asyncio.run(_main())
