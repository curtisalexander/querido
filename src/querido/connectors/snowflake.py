from __future__ import annotations

from typing import Self


class SnowflakeConnector:
    dialect = "snowflake"

    def __init__(self, **kwargs: object) -> None:
        import snowflake.connector  # type: ignore[import-not-found]

        # Pop qdo-specific keys that aren't Snowflake connect params
        kwargs.pop("type", None)

        # Map qdo 'auth' shorthand to Snowflake 'authenticator'
        if "auth" in kwargs:
            kwargs["authenticator"] = kwargs.pop("auth")

        # Support Snowflake's native connections.toml via connection_name
        if "snowflake_connection" in kwargs:
            kwargs["connection_name"] = kwargs.pop("snowflake_connection")

        # Enable credential caching by default so SSO/MFA users aren't
        # re-prompted on every CLI invocation.  Users can disable with
        # client_store_temporary_credential = false in their connection config.
        kwargs.setdefault("client_store_temporary_credential", True)
        kwargs.setdefault("client_request_mfa_token", True)

        self.conn = snowflake.connector.connect(**kwargs)

    def execute(self, sql: str, params: dict | tuple | None = None) -> list[dict]:
        cursor = self.conn.cursor()
        try:
            cursor.execute(sql, params)
            if cursor.description is None:
                return []
            try:
                return self._fetch_arrow(cursor)
            except (ImportError, NotImplementedError, RuntimeError):
                return self._fetch_standard(cursor)
        finally:
            cursor.close()

    def execute_arrow(self, sql: str, params: dict | tuple | None = None) -> object:
        """Execute SQL and return results as a PyArrow Table."""
        import pyarrow as pa

        cursor = self.conn.cursor()
        try:
            cursor.execute(sql, params)
            if cursor.description is None:
                return pa.table({})
            batches = list(cursor.fetch_arrow_batches())
            if not batches:
                return pa.table({})
            return pa.concat_tables(batches)
        finally:
            cursor.close()

    def get_tables(self) -> list[dict]:
        rows = self.execute(
            "SELECT table_name, table_type FROM information_schema.tables "
            "WHERE table_schema = CURRENT_SCHEMA() ORDER BY table_name"
        )
        return [
            {
                "name": r["TABLE_NAME"],
                "type": "view" if "VIEW" in r["TABLE_TYPE"] else "table",
            }
            for r in rows
        ]

    def get_columns(self, table: str) -> list[dict]:
        from querido.connectors.base import validate_table_name

        validate_table_name(table)
        # Snowflake uppercases unquoted identifiers, so metadata is stored
        # uppercase.  Use UPPER() to match regardless of what case the user typed.
        rows = self.execute(
            "SELECT column_name, data_type, is_nullable, column_default, comment "
            "FROM information_schema.columns "
            "WHERE table_name = UPPER(%s) "
            "ORDER BY ordinal_position",
            (table,),
        )
        return [
            {
                "name": r["COLUMN_NAME"],
                "type": r["DATA_TYPE"],
                "nullable": r["IS_NULLABLE"] == "YES",
                "default": r["COLUMN_DEFAULT"],
                "primary_key": False,
                "comment": r.get("COMMENT") or None,
            }
            for r in rows
        ]

    def get_table_comment(self, table: str) -> str | None:
        """Return the table comment from Snowflake, or None if not set."""
        from querido.connectors.base import validate_table_name

        validate_table_name(table)
        rows = self.execute(
            "SELECT comment FROM information_schema.tables WHERE table_name = UPPER(%s)",
            (table,),
        )
        if rows and rows[0].get("COMMENT"):
            return rows[0]["COMMENT"]
        return None

    def get_view_definition(self, view: str) -> str | None:
        """Return the SQL definition of a view from information_schema.views."""
        from querido.connectors.base import validate_table_name

        validate_table_name(view)
        rows = self.execute(
            "SELECT view_definition FROM information_schema.views WHERE table_name = UPPER(%s)",
            (view,),
        )
        if rows and rows[0].get("VIEW_DEFINITION"):
            return rows[0]["VIEW_DEFINITION"]
        return None

    def cancel(self) -> None:
        """Cancel the currently executing query on the Snowflake connection."""
        # Snowflake's cursor.cancel() is not available without a reference to the
        # active cursor, but closing the connection aborts any in-flight query.
        # Use a fresh cursor to issue a session-level cancel via the connection.
        try:
            cursor = self.conn.cursor()
            cursor.cancel()
            cursor.close()
        except Exception:
            pass

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _fetch_arrow(self, cursor: object) -> list[dict]:
        import pyarrow as pa

        batches = list(cursor.fetch_arrow_batches())  # type: ignore[attr-defined]
        if not batches:
            return []
        table = pa.concat_tables(batches)
        return table.to_pylist()

    def _fetch_standard(self, cursor: object) -> list[dict]:
        desc = cursor.description  # type: ignore[union-attr]
        if desc is None:
            return []
        columns = [d[0] for d in desc]
        rows = cursor.fetchall()  # type: ignore[attr-defined]
        return [dict(zip(columns, row, strict=True)) for row in rows]
