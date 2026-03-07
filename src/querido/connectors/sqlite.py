from __future__ import annotations

import sqlite3
from typing import Self

from querido.connectors.base import validate_table_name


class SQLiteConnector:
    dialect = "sqlite"

    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql: str, params: dict | tuple | None = None) -> list[dict]:
        cursor = self.conn.execute(sql, params or {})
        rows = cursor.fetchall()
        if not rows:
            return []
        return [dict(row) for row in rows]

    def get_columns(self, table: str) -> list[dict]:
        validate_table_name(table)
        # PRAGMA doesn't support bind parameters, so we use an f-string here.
        # validate_table_name above ensures the name is a safe identifier.
        rows = self.execute(f"PRAGMA table_info({table})")
        return [
            {
                "name": r["name"],
                "type": r["type"],
                "nullable": not r["notnull"],
                "default": r["dflt_value"],
                "primary_key": bool(r["pk"]),
            }
            for r in rows
        ]

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
