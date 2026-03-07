from __future__ import annotations

from typing import Self


class DuckDBConnector:
    dialect = "duckdb"

    def __init__(self, path: str = ":memory:") -> None:
        import duckdb

        self.conn = duckdb.connect(path)

    def execute(self, sql: str, params: dict | tuple | list | None = None) -> list[dict]:
        result = self.conn.execute(sql, params) if params else self.conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def get_columns(self, table: str) -> list[dict]:
        from querido.connectors.base import validate_table_name

        validate_table_name(table)
        rows = self.execute(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_name = $table_name",
            {"table_name": table},
        )
        return [
            {
                "name": r["column_name"],
                "type": r["data_type"],
                "nullable": r["is_nullable"] == "YES",
                "default": r["column_default"],
                "primary_key": False,
            }
            for r in rows
        ]

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
