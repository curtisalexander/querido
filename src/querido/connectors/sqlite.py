from __future__ import annotations

import sqlite3
from typing import Self

from querido.connectors.base import validate_table_name


class SQLiteConnector:
    dialect = "sqlite"
    supports_concurrent_queries = False

    def __init__(self, path: str, *, check_same_thread: bool = True) -> None:
        self.conn = sqlite3.connect(path, check_same_thread=check_same_thread)
        self.conn.row_factory = sqlite3.Row
        self._columns_cache: dict[str, list[dict]] = {}
        # Optimize for read-heavy profiling workloads.
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA cache_size = -65536")  # 64 MB page cache
        self.conn.execute("PRAGMA mmap_size = 268435456")  # 256 MB mmap

    def execute(self, sql: str, params: dict | tuple | None = None) -> list[dict]:
        cursor = self.conn.execute(sql) if params is None else self.conn.execute(sql, params)
        rows = cursor.fetchall()
        if not rows:
            return []
        return [dict(row) for row in rows]

    def get_tables(self) -> list[dict]:
        rows = self.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [{"name": r["name"], "type": r["type"]} for r in rows]

    def get_columns(self, table: str) -> list[dict]:
        validate_table_name(table)
        cache_key = table.lower()
        if cache_key in self._columns_cache:
            return self._columns_cache[cache_key]
        # PRAGMA doesn't support bind parameters, so we use an f-string here.
        # validate_table_name above ensures the name is a safe identifier.
        rows = self.execute(f"PRAGMA table_info({table})")
        result = [
            {
                "name": r["name"],
                "type": r["type"],
                "nullable": not r["notnull"],
                "default": r["dflt_value"],
                "primary_key": bool(r["pk"]),
                "comment": None,
            }
            for r in rows
        ]
        self._columns_cache[cache_key] = result
        return result

    def get_table_comment(self, table: str) -> str | None:
        """SQLite does not support table comments."""
        return None

    def get_view_definition(self, view: str) -> str | None:
        """Return the SQL definition of a view from sqlite_master."""
        validate_table_name(view)
        rows = self.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'view' AND name = ?",
            (view,),
        )
        if rows and rows[0]["sql"]:
            return rows[0]["sql"]
        return None

    def sample_source(self, table: str, sample_size: int, *, row_count: int = 0) -> str:
        # Bernoulli-style sampling: probabilistically include rows without
        # sorting.  Much faster than ORDER BY RANDOM() on large tables because
        # it avoids the full sort and can stop early via LIMIT.
        return (
            f"(SELECT * FROM {table} WHERE ABS(RANDOM()) % "
            f"MAX((SELECT COUNT(*) FROM {table}) / {sample_size}, 1) = 0 "
            f"LIMIT {sample_size}) AS _sample"
        )

    def cancel(self) -> None:
        """Interrupt a running query."""
        self.conn.interrupt()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
