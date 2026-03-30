"""Local metadata cache for fast table/column search.

Stores table and column metadata in a local SQLite database so that
operations like search, fuzzy suggestions, and tab completion can be
instant — especially for large Snowflake databases.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector

# Default time-to-live for cached metadata (seconds)
DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24 hours

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS cached_tables (
    connection TEXT NOT NULL,
    table_name TEXT NOT NULL,
    table_type TEXT NOT NULL,
    cached_at REAL NOT NULL,
    PRIMARY KEY (connection, table_name)
);

CREATE TABLE IF NOT EXISTS cached_columns (
    connection TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    column_type TEXT NOT NULL,
    nullable INTEGER NOT NULL,
    comment TEXT,
    cached_at REAL NOT NULL,
    PRIMARY KEY (connection, table_name, column_name)
);
"""


class MetadataCache:
    """SQLite-backed metadata cache."""

    def __init__(self, cache_path: Path | None = None) -> None:
        if cache_path is None:
            from querido.config import get_config_dir

            cache_dir = get_config_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / "cache.db"

        self._path = cache_path
        self._conn = sqlite3.connect(str(cache_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)

    def sync(
        self,
        connection_name: str,
        connector: Connector,
    ) -> dict:
        """Fetch all table/column metadata and store it in the cache.

        Returns a summary dict with keys: tables, columns, elapsed.
        """
        start = time.monotonic()
        now = time.time()

        # Clear old data for this connection
        self._conn.execute("DELETE FROM cached_tables WHERE connection = ?", (connection_name,))
        self._conn.execute("DELETE FROM cached_columns WHERE connection = ?", (connection_name,))

        tables = connector.get_tables()
        table_count = 0
        column_count = 0

        for tbl in tables:
            self._conn.execute(
                "INSERT INTO cached_tables (connection, table_name, table_type, cached_at) "
                "VALUES (?, ?, ?, ?)",
                (connection_name, tbl["name"], tbl["type"], now),
            )
            table_count += 1

        # Fetch column metadata — use parallel fetching for concurrent connectors
        concurrent = getattr(connector, "supports_concurrent_queries", False)
        table_names = [t["name"] for t in tables]

        def _fetch_cols(tbl_name: str) -> tuple[str, list[dict]]:
            try:
                return tbl_name, connector.get_columns(tbl_name)
            except Exception as exc:
                print(
                    f"Warning: could not read columns for '{tbl_name}': {exc}",
                    file=sys.stderr,
                )
                return tbl_name, []

        if concurrent and len(table_names) > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            max_workers = min(len(table_names), 4)
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(_fetch_cols, n): n for n in table_names}
                for future in as_completed(futures):
                    tbl_name, columns = future.result()
                    column_count += self._insert_columns(connection_name, tbl_name, columns, now)
        else:
            for tbl_name in table_names:
                _, columns = _fetch_cols(tbl_name)
                column_count += self._insert_columns(connection_name, tbl_name, columns, now)

        self._conn.commit()
        elapsed = time.monotonic() - start

        return {"tables": table_count, "columns": column_count, "elapsed": round(elapsed, 2)}

    def sync_tables_only(
        self,
        connection_name: str,
        connector: Connector,
    ) -> int:
        """Fetch table names and cache them (no column metadata).

        This is a lightweight alternative to :meth:`sync` designed for
        auto-warming the cache in the background.  Only the table list is
        fetched — column metadata is skipped because fetching columns for
        every table is the expensive part of a full sync.

        Returns the number of tables cached.
        """
        now = time.time()

        self._conn.execute("DELETE FROM cached_tables WHERE connection = ?", (connection_name,))

        tables = connector.get_tables()
        for tbl in tables:
            self._conn.execute(
                "INSERT INTO cached_tables (connection, table_name, table_type, cached_at) "
                "VALUES (?, ?, ?, ?)",
                (connection_name, tbl["name"], tbl["type"], now),
            )

        self._conn.commit()
        return len(tables)

    def _insert_columns(
        self, connection_name: str, tbl_name: str, columns: list[dict], now: float
    ) -> int:
        """Insert column rows into the cache and return the count."""
        count = 0
        for col in columns:
            self._conn.execute(
                "INSERT INTO cached_columns "
                "(connection, table_name, column_name, column_type, "
                "nullable, comment, cached_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    connection_name,
                    tbl_name,
                    col["name"],
                    col["type"],
                    1 if col.get("nullable") else 0,
                    col.get("comment"),
                    now,
                ),
            )
            count += 1
        return count

    def status(self, connection_name: str | None = None) -> list[dict]:
        """Return cache status for one or all connections.

        Returns list of dicts with keys: connection, tables, columns, cached_at, age_hours.
        """
        now = time.time()

        if connection_name:
            where = "WHERE connection = ?"
            params: tuple = (connection_name,)
        else:
            where = ""
            params = ()

        rows = self._conn.execute(
            f"SELECT connection, COUNT(*) as table_count, MAX(cached_at) as last_cached "
            f"FROM cached_tables {where} GROUP BY connection ORDER BY connection",
            params,
        ).fetchall()

        results = []
        for row in rows:
            conn_name = row["connection"]
            col_count = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM cached_columns WHERE connection = ?",
                (conn_name,),
            ).fetchone()["cnt"]

            last_cached = row["last_cached"]
            age_hours = round((now - last_cached) / 3600, 1) if last_cached else None

            results.append(
                {
                    "connection": conn_name,
                    "tables": row["table_count"],
                    "columns": col_count,
                    "cached_at": last_cached,
                    "age_hours": age_hours,
                }
            )

        return results

    def clear(self, connection_name: str | None = None) -> int:
        """Clear cached metadata. Returns number of tables removed."""
        if connection_name:
            cursor = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM cached_tables WHERE connection = ?",
                (connection_name,),
            )
            count = cursor.fetchone()["cnt"]
            self._conn.execute(
                "DELETE FROM cached_tables WHERE connection = ?", (connection_name,)
            )
            self._conn.execute(
                "DELETE FROM cached_columns WHERE connection = ?", (connection_name,)
            )
        else:
            cursor = self._conn.execute("SELECT COUNT(*) as cnt FROM cached_tables")
            count = cursor.fetchone()["cnt"]
            self._conn.execute("DELETE FROM cached_tables")
            self._conn.execute("DELETE FROM cached_columns")

        self._conn.commit()
        return count

    def search(
        self,
        connection_name: str,
        pattern: str,
        search_type: str = "all",
    ) -> list[dict]:
        """Search cached metadata for pattern matches.

        Returns results in the same format as cli/search.py's _search_metadata.
        """
        escaped = pattern.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pat = f"%{escaped}%"
        results: list[dict] = []

        search_tables = search_type in ("table", "all")
        search_columns = search_type in ("column", "all")

        if search_tables:
            rows = self._conn.execute(
                "SELECT table_name, table_type FROM cached_tables "
                "WHERE connection = ? AND lower(table_name) LIKE ? ESCAPE '\\'",
                (connection_name, pat),
            ).fetchall()
            for r in rows:
                results.append(
                    {
                        "table_name": r["table_name"],
                        "table_type": r["table_type"],
                        "match_type": "table",
                        "column_name": None,
                        "column_type": None,
                    }
                )

        if search_columns:
            rows = self._conn.execute(
                "SELECT t.table_name, t.table_type, "
                "c.column_name, c.column_type "
                "FROM cached_columns c "
                "JOIN cached_tables t "
                "ON c.connection = t.connection "
                "AND c.table_name = t.table_name "
                "WHERE c.connection = ? AND lower(c.column_name) LIKE ? ESCAPE '\\'",
                (connection_name, pat),
            ).fetchall()
            for r in rows:
                results.append(
                    {
                        "table_name": r["table_name"],
                        "table_type": r["table_type"],
                        "match_type": "column",
                        "column_name": r["column_name"],
                        "column_type": r["column_type"],
                    }
                )

        return results

    def has_table(self, connection_name: str, table: str) -> bool | None:
        """Check if a table exists in the cache.

        Returns ``True``/``False`` if the cache is fresh, or ``None`` if the
        cache is stale or empty (caller should fall back to a live query).
        """
        if not self.is_fresh(connection_name):
            return None
        row = self._conn.execute(
            "SELECT 1 FROM cached_tables WHERE connection = ? AND lower(table_name) = lower(?)",
            (connection_name, table),
        ).fetchone()
        return row is not None

    def get_cached_columns(self, connection_name: str, table: str) -> list[dict] | None:
        """Return cached column metadata for a table, or None if stale/missing."""
        if not self.is_fresh(connection_name):
            return None
        rows = self._conn.execute(
            "SELECT column_name, column_type, nullable, comment "
            "FROM cached_columns "
            "WHERE connection = ? AND lower(table_name) = lower(?)",
            (connection_name, table),
        ).fetchall()
        if not rows:
            return None
        return [
            {
                "name": r["column_name"],
                "type": r["column_type"],
                "nullable": bool(r["nullable"]),
                "default": None,
                "primary_key": False,
                "comment": r["comment"],
            }
            for r in rows
        ]

    def get_cached_tables(self, connection_name: str) -> list[dict] | None:
        """Return cached table list, or None if stale/missing."""
        if not self.is_fresh(connection_name):
            return None
        rows = self._conn.execute(
            "SELECT table_name, table_type FROM cached_tables "
            "WHERE connection = ? ORDER BY table_name",
            (connection_name,),
        ).fetchall()
        if not rows:
            return None
        return [{"name": r["table_name"], "type": r["table_type"]} for r in rows]

    def is_fresh(self, connection_name: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
        """Check if the cache for a connection is fresh (within TTL)."""
        row = self._conn.execute(
            "SELECT MAX(cached_at) as last FROM cached_tables WHERE connection = ?",
            (connection_name,),
        ).fetchone()

        if row is None or row["last"] is None:
            return False

        return (time.time() - row["last"]) < ttl_seconds

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> MetadataCache:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
