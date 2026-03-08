"""Local metadata cache for fast table/column search.

Stores table and column metadata in a local SQLite database so that
operations like search, fuzzy suggestions, and tab completion can be
instant — especially for large Snowflake databases.
"""

from __future__ import annotations

import sqlite3
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
        *,
        on_progress: object | None = None,
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
            tbl_name = tbl["name"]
            tbl_type = tbl["type"]

            self._conn.execute(
                "INSERT INTO cached_tables (connection, table_name, table_type, cached_at) "
                "VALUES (?, ?, ?, ?)",
                (connection_name, tbl_name, tbl_type, now),
            )
            table_count += 1

            try:
                columns = connector.get_columns(tbl_name)
            except Exception:
                continue

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
                column_count += 1

        self._conn.commit()
        elapsed = time.monotonic() - start

        return {"tables": table_count, "columns": column_count, "elapsed": round(elapsed, 2)}

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

            results.append({
                "connection": conn_name,
                "tables": row["table_count"],
                "columns": col_count,
                "cached_at": last_cached,
                "age_hours": age_hours,
            })

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
        pat = f"%{pattern.lower()}%"
        results: list[dict] = []

        search_tables = search_type in ("table", "all")
        search_columns = search_type in ("column", "all")

        if search_tables:
            rows = self._conn.execute(
                "SELECT table_name, table_type FROM cached_tables "
                "WHERE connection = ? AND lower(table_name) LIKE ?",
                (connection_name, pat),
            ).fetchall()
            for r in rows:
                results.append({
                    "table_name": r["table_name"],
                    "table_type": r["table_type"],
                    "match_type": "table",
                    "column_name": None,
                    "column_type": None,
                })

        if search_columns:
            rows = self._conn.execute(
                "SELECT t.table_name, t.table_type, "
                "c.column_name, c.column_type "
                "FROM cached_columns c "
                "JOIN cached_tables t "
                "ON c.connection = t.connection "
                "AND c.table_name = t.table_name "
                "WHERE c.connection = ? AND lower(c.column_name) LIKE ?",
                (connection_name, pat),
            ).fetchall()
            for r in rows:
                results.append({
                    "table_name": r["table_name"],
                    "table_type": r["table_type"],
                    "match_type": "column",
                    "column_name": r["column_name"],
                    "column_type": r["column_type"],
                })

        return results

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
