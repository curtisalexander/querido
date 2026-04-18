from __future__ import annotations

import sqlite3
from typing import Self

from querido.connectors.base import validate_table_name, wrap_driver_error


class SQLiteConnector:
    """SQLite connector.

    ``_columns_cache`` key convention: ``table.lower()``. SQLite treats
    identifiers case-insensitively (unless double-quoted), so a single
    lowercase key collapses every casing a caller might supply.
    """

    dialect = "sqlite"
    supports_concurrent_queries = False

    def __init__(self, path: str, *, check_same_thread: bool = True) -> None:
        try:
            self.conn = sqlite3.connect(path, check_same_thread=check_same_thread)
        except sqlite3.Error as exc:
            wrapped = wrap_driver_error(exc)
            if wrapped is not None:
                raise wrapped from exc
            raise
        self.conn.row_factory = sqlite3.Row
        self._columns_cache: dict[str, list[dict]] = {}
        # Optimize for read-heavy profiling workloads.
        self.conn.execute("pragma journal_mode = WAL")
        self.conn.execute("pragma cache_size = -65536")  # 64 MB page cache
        self.conn.execute("pragma mmap_size = 268435456")  # 256 MB mmap

    def execute(self, sql: str, params: dict | tuple | None = None) -> list[dict]:
        try:
            cursor = self.conn.execute(sql) if params is None else self.conn.execute(sql, params)
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            wrapped = wrap_driver_error(exc)
            if wrapped is not None:
                raise wrapped from exc
            raise
        if not rows:
            return []
        return [dict(row) for row in rows]

    def get_tables(self, *, database: str | None = None, schema: str | None = None) -> list[dict]:
        rows = self.execute(
            "select name, type from sqlite_master where type in ('table', 'view') "
            "and name not like 'sqlite_%' order by name"
        )
        return [{"name": r["name"], "type": r["type"]} for r in rows]

    def get_columns(self, table: str) -> list[dict]:
        validate_table_name(table)
        cache_key = table.lower()
        if cache_key in self._columns_cache:
            return self._columns_cache[cache_key]
        # PRAGMA doesn't support bind parameters, so we use an f-string here.
        # validate_table_name above ensures the name is a safe identifier.
        rows = self.execute(f"pragma table_info({table})")
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
            "select sql from sqlite_master where type = 'view' and name = ?",
            (view,),
        )
        if rows and rows[0]["sql"]:
            return rows[0]["sql"]
        return None

    def get_row_count(self, table: str) -> int:
        """Return exact row count via ``SELECT COUNT(*)``.

        SQLite has no metadata shortcut, so this always scans the table.
        """
        validate_table_name(table)
        rows = self.execute(f'select count(*) as cnt from "{table}"')
        return rows[0].get("cnt", 0) if rows else 0

    def get_table_row_counts(self, table_names: list[str]) -> dict[str, int]:
        """Return row counts for multiple tables via batched UNION ALL."""
        if not table_names:
            return {}
        for name in table_names:
            validate_table_name(name)

        result: dict[str, int] = {}
        # Batch in groups of 50 to avoid hitting SQL length limits.
        batch_size = 50
        for i in range(0, len(table_names), batch_size):
            batch = table_names[i : i + batch_size]
            parts = [f"select '{name}' as name, count(*) as cnt from \"{name}\"" for name in batch]
            sql = " union all ".join(parts)
            rows = self.execute(sql)
            for row in rows:
                result[row.get("name", "")] = row.get("cnt", 0)
        return result

    def sample_source(self, table: str, sample_size: int, *, row_count: int = 0) -> str:
        # Bernoulli-style sampling: probabilistically include rows without
        # sorting.  Much faster than ORDER BY RANDOM() on large tables because
        # it avoids the full sort and can stop early via LIMIT.
        # When row_count is provided, use it directly instead of embedding a
        # nested count(*) subquery that would re-scan the table.
        validate_table_name(table)
        if sample_size <= 0:
            raise ValueError(f"sample_size must be positive, got {sample_size}")
        if row_count > 0:
            modulus = max(row_count // sample_size, 1)
        else:
            # Fallback: embed the count subquery when row_count is unknown.
            return (
                f"(select * from {table} where abs(random()) % "
                f"max((select count(*) from {table}) / {sample_size}, 1) = 0 "
                f"limit {sample_size}) as _sample"
            )
        return (
            f"(select * from {table} where abs(random()) % {modulus} = 0 "
            f"limit {sample_size}) as _sample"
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
