from __future__ import annotations

from typing import Self

from querido.connectors.base import validate_table_name


class DuckDBConnector:
    dialect = "duckdb"

    def __init__(self, path: str = ":memory:") -> None:
        import duckdb

        self.conn = duckdb.connect(path)

    def register_parquet(self, parquet_path: str) -> str:
        """Register a parquet file as a view and return the view name."""
        from pathlib import Path

        p = Path(parquet_path)
        if not p.exists():
            raise FileNotFoundError(f"Parquet file not found: {parquet_path}")
        resolved = str(p.resolve())
        name = p.stem
        validate_table_name(name)
        # Use forward slashes (works on all platforms in DuckDB) and escape quotes
        safe_path = resolved.replace("\\", "/").replace("'", "''")
        safe_name = name.replace('"', '""')
        self.conn.execute(
            f"CREATE OR REPLACE VIEW \"{safe_name}\" AS SELECT * FROM read_parquet('{safe_path}')"
        )
        return name

    def execute(self, sql: str, params: dict | tuple | None = None) -> list[dict]:
        result = self.conn.execute(sql, params) if params else self.conn.execute(sql)
        if result.description is None:
            return []
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def get_tables(self) -> list[dict]:
        rows = self.execute(
            "SELECT table_name, table_type FROM information_schema.tables "
            "WHERE table_schema = 'main' ORDER BY table_name"
        )
        return [
            {
                "name": r["table_name"],
                "type": "view" if "VIEW" in r["table_type"] else "table",
            }
            for r in rows
        ]

    def get_columns(self, table: str) -> list[dict]:
        validate_table_name(table)
        rows = self.execute(
            "SELECT column_name, data_type, is_nullable, column_default, comment "
            "FROM duckdb_columns() "
            "WHERE lower(table_name) = lower($table_name)",
            {"table_name": table},
        )
        return [
            {
                "name": r["column_name"],
                "type": r["data_type"],
                "nullable": r["is_nullable"] == "YES",
                "default": r["column_default"],
                "primary_key": False,
                "comment": r["comment"] if r["comment"] else None,
            }
            for r in rows
        ]

    def get_table_comment(self, table: str) -> str | None:
        """Return the table comment, or None if not set."""
        validate_table_name(table)
        rows = self.execute(
            "SELECT comment FROM duckdb_tables() WHERE lower(table_name) = lower($table_name)",
            {"table_name": table},
        )
        if rows and rows[0]["comment"]:
            return rows[0]["comment"]
        return None

    def get_view_definition(self, view: str) -> str | None:
        """Return the SQL definition of a view from duckdb_views()."""
        validate_table_name(view)
        rows = self.execute(
            "SELECT sql FROM duckdb_views() WHERE lower(view_name) = lower($view_name)",
            {"view_name": view},
        )
        if rows and rows[0]["sql"]:
            return rows[0]["sql"]
        return None

    def cancel(self) -> None:
        """Interrupt a running query."""
        self.conn.interrupt()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
