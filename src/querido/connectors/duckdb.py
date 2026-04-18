from __future__ import annotations

from typing import Self

from querido.connectors.base import validate_table_name, wrap_driver_error


class DuckDBConnector:
    """DuckDB connector (also handles Parquet via ``register_parquet``).

    ``_columns_cache`` key convention: ``table.lower()``. DuckDB folds
    unquoted identifiers to lowercase in its catalog, so lowercasing in
    Python up front keeps cache lookups consistent with what ``duckdb_columns()``
    sees and avoids a per-row ``lower()`` in the catalog query.
    """

    dialect = "duckdb"
    supports_concurrent_queries = False

    def __init__(self, path: str = ":memory:") -> None:
        import duckdb

        try:
            self.conn = duckdb.connect(path)
        except duckdb.Error as exc:
            wrapped = wrap_driver_error(exc)
            if wrapped is not None:
                raise wrapped from exc
            raise
        self._columns_cache: dict[str, list[dict]] = {}

    def register_parquet(self, parquet_path: str) -> None:
        """Register a parquet file as a view."""
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
            f"create or replace view \"{safe_name}\" as select * from read_parquet('{safe_path}')"
        )

    def execute(self, sql: str, params: dict | tuple | None = None) -> list[dict]:
        import duckdb

        try:
            result = self.conn.execute(sql) if params is None else self.conn.execute(sql, params)
        except duckdb.Error as exc:
            wrapped = wrap_driver_error(exc)
            if wrapped is not None:
                raise wrapped from exc
            raise
        if result.description is None:
            return []
        try:
            return result.to_arrow_table().to_pylist()
        except (ImportError, RuntimeError, AttributeError):
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            return [dict(zip(columns, row, strict=True)) for row in rows]

    def execute_arrow(self, sql: str, params: dict | tuple | None = None) -> object:
        """Execute SQL and return results as a PyArrow Table."""
        import duckdb
        import pyarrow as pa

        try:
            result = self.conn.execute(sql) if params is None else self.conn.execute(sql, params)
        except duckdb.Error as exc:
            wrapped = wrap_driver_error(exc)
            if wrapped is not None:
                raise wrapped from exc
            raise
        if result.description is None:
            return pa.table({})
        return result.to_arrow_table()

    def get_tables(self, *, database: str | None = None, schema: str | None = None) -> list[dict]:
        rows = self.execute(
            "select table_name, table_type from information_schema.tables "
            "where table_schema = 'main' order by table_name"
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
        cache_key = table.lower()
        if cache_key in self._columns_cache:
            return self._columns_cache[cache_key]
        # Case normalization is done in Python (.lower()) rather than in SQL
        # (lower()) to avoid per-row function calls on large catalogs.
        rows = self.execute(
            "select column_name, data_type, is_nullable, column_default, comment "
            "from duckdb_columns() "
            "where schema_name = 'main' and table_name = $table_name",
            {"table_name": cache_key},
        )
        result = [
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
        self._columns_cache[cache_key] = result
        return result

    def get_table_comment(self, table: str) -> str | None:
        """Return the table comment, or None if not set."""
        validate_table_name(table)
        rows = self.execute(
            "select comment from duckdb_tables() "
            "where schema_name = 'main' and table_name = $table_name",
            {"table_name": table.lower()},
        )
        if rows and rows[0]["comment"]:
            return rows[0]["comment"]
        return None

    def get_view_definition(self, view: str) -> str | None:
        """Return the SQL definition of a view from duckdb_views()."""
        validate_table_name(view)
        rows = self.execute(
            "select sql from duckdb_views() where schema_name = 'main' and view_name = $view_name",
            {"view_name": view.lower()},
        )
        if rows and rows[0]["sql"]:
            return rows[0]["sql"]
        return None

    def get_row_count(self, table: str) -> int:
        """Return estimated row count from DuckDB metadata.

        Uses ``duckdb_tables()`` for base tables (no scan). Falls back
        to ``SELECT COUNT(*)`` for views or when metadata is unavailable.
        """
        validate_table_name(table)
        rows = self.execute(
            "select estimated_size from duckdb_tables() "
            "where schema_name = 'main' and table_name = $table_name",
            {"table_name": table.lower()},
        )
        if rows:
            return rows[0].get("estimated_size", 0)
        # Fallback for views or if metadata is unavailable
        rows = self.execute(f'select count(*) as cnt from "{table}"')
        return rows[0].get("cnt", 0) if rows else 0

    def get_table_row_counts(self, table_names: list[str]) -> dict[str, int]:
        """Return estimated row counts for all tables in one query.

        Uses ``duckdb_tables()`` metadata — no table scans.  Falls back
        to individual ``SELECT COUNT(*)`` for tables not found in metadata
        (e.g. views).
        """
        if not table_names:
            return {}
        rows = self.execute(
            "select table_name, estimated_size from duckdb_tables() where schema_name = 'main'"
        )
        metadata = {r.get("table_name", "").lower(): r.get("estimated_size", 0) for r in rows}

        result: dict[str, int] = {}
        for name in table_names:
            count = metadata.get(name.lower())
            if count is not None:
                result[name] = count
            else:
                # Fallback for views
                result[name] = self.get_row_count(name)
        return result

    def sample_source(self, table: str, sample_size: int, *, row_count: int = 0) -> str:
        # Use system (block-level) sampling for large tables (>10M rows).
        # System sampling skips entire row groups and is significantly faster
        # than reservoir sampling, which must scan every row.
        validate_table_name(table)
        if sample_size <= 0:
            raise ValueError(f"sample_size must be positive, got {sample_size}")
        if row_count > 10_000_000:
            pct = max(sample_size / row_count * 100, 0.01)
            return f"(select * from {table} using sample {pct:.4f} percent (system)) as _sample"
        return f"(select * from {table} using sample {sample_size}) as _sample"

    def cancel(self) -> None:
        """Interrupt a running query."""
        self.conn.interrupt()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
