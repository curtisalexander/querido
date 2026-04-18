from __future__ import annotations

from typing import Self


class SnowflakeConnector:
    dialect = "snowflake"
    supports_concurrent_queries = True

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

        # Load private key from file when private_key_path is provided.
        # Snowflake's connector expects a `private_key` bytes object, not a
        # file path, so we read and deserialize the PEM/DER key here.
        if "private_key_path" in kwargs:
            from pathlib import Path

            from cryptography.exceptions import UnsupportedAlgorithm
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.serialization import (
                Encoding,
                NoEncryption,
                PrivateFormat,
                load_der_private_key,
                load_pem_private_key,
            )

            key_path = Path(str(kwargs.pop("private_key_path"))).expanduser()
            passphrase = kwargs.pop("private_key_passphrase", None)
            if passphrase is not None:
                passphrase = str(passphrase).encode()

            key_bytes = key_path.read_bytes()
            try:
                private_key = load_pem_private_key(
                    key_bytes, password=passphrase, backend=default_backend()
                )
            except (ValueError, UnsupportedAlgorithm):
                private_key = load_der_private_key(
                    key_bytes, password=passphrase, backend=default_backend()
                )

            kwargs["private_key"] = private_key.private_bytes(
                encoding=Encoding.DER,
                format=PrivateFormat.PKCS8,
                encryption_algorithm=NoEncryption(),
            )

        # Enable credential caching by default so SSO/MFA users aren't
        # re-prompted on every CLI invocation.  Users can disable with
        # client_store_temporary_credential = false in their connection config.
        kwargs.setdefault("client_store_temporary_credential", True)
        kwargs.setdefault("client_request_mfa_token", True)

        # Capture database/schema from config before connecting so we can
        # qualify information_schema queries without extra roundtrips.
        # Snowflake stores unquoted identifiers as uppercase.
        cfg_database = str(kwargs.get("database", "")).upper()
        cfg_schema = str(kwargs.get("schema", "")).upper()

        from querido.connectors.base import wrap_driver_error

        try:
            self.conn = snowflake.connector.connect(**kwargs)
        except snowflake.connector.Error as exc:
            wrapped = wrap_driver_error(exc)
            if wrapped is not None:
                raise wrapped from exc
            raise
        self._active_cursor: object | None = None
        self._columns_cache: dict[str, list[dict]] = {}

        # Use config values when available; fall back to querying the session
        # for any that are missing (needed for connections.toml where db/schema
        # are set externally, or partial configs with only one of the two).
        self._database: str = cfg_database
        self._schema: str = cfg_schema
        if not self._database or not self._schema:
            cursor = self.conn.cursor()
            try:
                cursor.execute("select current_database(), current_schema()")
                row = cursor.fetchone()
                if not self._database:
                    self._database = row[0] if row and row[0] else ""
                if not self._schema:
                    self._schema = row[1] if row and row[1] else ""
            finally:
                cursor.close()

        # Validate that database/schema are safe for SQL interpolation when set.
        # These values are used in f-string SQL (e.g. {db}.information_schema)
        # so they must match the safe identifier pattern.  They may be empty if
        # the user intends to always supply fully-qualified table names.
        from querido.connectors.base import validate_object_name

        try:
            if self._database:
                validate_object_name(self._database)
            if self._schema:
                validate_object_name(self._schema)
        except ValueError:
            self.conn.close()
            raise

    def execute(self, sql: str, params: dict | tuple | None = None) -> list[dict]:
        import snowflake.connector  # type: ignore[import-not-found]

        from querido.connectors.base import wrap_driver_error

        cursor = self.conn.cursor()
        self._active_cursor = cursor
        try:
            try:
                cursor.execute(sql, params)
            except snowflake.connector.Error as exc:
                wrapped = wrap_driver_error(exc)
                if wrapped is not None:
                    raise wrapped from exc
                raise
            if cursor.description is None:
                return []
            try:
                return self._fetch_arrow(cursor)
            except (ImportError, NotImplementedError, RuntimeError):
                return self._fetch_standard(cursor)
        finally:
            self._active_cursor = None
            cursor.close()

    def execute_arrow(self, sql: str, params: dict | tuple | None = None) -> object:
        """Execute SQL and return results as a PyArrow Table."""
        import pyarrow as pa
        import snowflake.connector  # type: ignore[import-not-found]

        from querido.connectors.base import wrap_driver_error

        cursor = self.conn.cursor()
        self._active_cursor = cursor
        try:
            try:
                cursor.execute(sql, params)
            except snowflake.connector.Error as exc:
                wrapped = wrap_driver_error(exc)
                if wrapped is not None:
                    raise wrapped from exc
                raise
            if cursor.description is None:
                return pa.table({})
            batches = list(cursor.fetch_arrow_batches())
            if not batches:
                return pa.table({})
            table = pa.concat_tables(batches)
            return table.rename_columns([c.lower() for c in table.column_names])
        finally:
            self._active_cursor = None
            cursor.close()

    def _resolve_table(self, name: str) -> tuple[str, str, str]:
        """Parse a possibly-qualified table name into (database, schema, table).

        Supports:
          - ``table``               → (self._database, self._schema, TABLE)
          - ``schema.table``        → (self._database, SCHEMA, TABLE)
          - ``database.schema.table`` → (DATABASE, SCHEMA, TABLE)

        All components are uppercased (Snowflake convention) and validated.
        Raises ValueError with a helpful message when defaults are needed but
        not configured.
        """
        from querido.connectors.base import validate_object_name

        parts = name.split(".")
        if len(parts) == 1:
            if not self._database or not self._schema:
                missing = []
                if not self._database:
                    missing.append("'database'")
                if not self._schema:
                    missing.append("'schema'")
                raise ValueError(
                    f"Cannot resolve unqualified table name {name!r} — "
                    f"{' and '.join(missing)} not set. "
                    "Use a fully-qualified name (database.schema.table) or set "
                    f"{' and '.join(missing)} in your connection config."
                )
            database, schema, table = self._database, self._schema, parts[0]
        elif len(parts) == 2:
            if not self._database:
                raise ValueError(
                    f"Cannot resolve schema-qualified table name {name!r} — "
                    "'database' not set. "
                    "Use a fully-qualified name (database.schema.table) or set "
                    "'database' in your connection config."
                )
            database, schema, table = self._database, parts[0], parts[1]
        elif len(parts) == 3:
            database, schema, table = parts[0], parts[1], parts[2]
        else:
            raise ValueError(
                f"Invalid table reference: {name!r}. "
                "Expected 'table', 'schema.table', or 'database.schema.table'."
            )

        database, schema, table = database.upper(), schema.upper(), table.upper()
        validate_object_name(database)
        validate_object_name(schema)
        validate_object_name(table)
        return database, schema, table

    def get_tables(self, *, database: str | None = None, schema: str | None = None) -> list[dict]:
        """Return tables in the given (or default) database and schema.

        When *database* or *schema* are ``None`` the connector's defaults are
        used.  Raises ``ValueError`` if the required context is still missing.
        """
        from querido.connectors.base import validate_object_name

        db = database or self._database
        sch = schema or self._schema
        if not db or not sch:
            missing = []
            if not db:
                missing.append("'database'")
            if not sch:
                missing.append("'schema'")
            raise ValueError(
                f"Cannot list tables — {' and '.join(missing)} not set. "
                "Set them in your connection config or use a fully-qualified "
                "table name (database.schema.table)."
            )
        validate_object_name(db)
        validate_object_name(sch)

        rows = self.execute(
            f"select table_name, table_type from {db}.information_schema.tables "
            f"where table_schema = %s order by table_name",
            (sch,),
        )
        return [
            {
                "name": r["table_name"],
                "type": "view" if "VIEW" in r["table_type"] else "table",
            }
            for r in rows
        ]

    def get_columns(self, table: str) -> list[dict]:
        database, schema, tbl = self._resolve_table(table)
        cache_key = f"{database}.{schema}.{tbl}"
        if cache_key in self._columns_cache:
            return self._columns_cache[cache_key]
        rows = self.execute(
            f"select column_name, data_type, is_nullable, column_default, comment "
            f"from {database}.information_schema.columns "
            f"where table_schema = %s and table_name = %s "
            f"order by ordinal_position",
            (schema, tbl),
        )
        result = [
            {
                "name": r["column_name"],
                "type": r["data_type"],
                "nullable": r["is_nullable"] == "YES",
                "default": r["column_default"],
                "primary_key": False,
                "comment": r.get("comment") or None,
            }
            for r in rows
        ]
        self._columns_cache[cache_key] = result
        return result

    def get_table_comment(self, table: str) -> str | None:
        """Return the table comment from Snowflake, or None if not set."""
        database, schema, tbl = self._resolve_table(table)
        rows = self.execute(
            f"select comment from {database}.information_schema.tables "
            f"where table_schema = %s and table_name = %s",
            (schema, tbl),
        )
        if rows and rows[0].get("comment"):
            return rows[0]["comment"]
        return None

    def get_view_definition(self, view: str) -> str | None:
        """Return the SQL definition of a view from information_schema.views."""
        database, schema, tbl = self._resolve_table(view)
        rows = self.execute(
            f"select view_definition from {database}.information_schema.views "
            f"where table_schema = %s and table_name = %s",
            (schema, tbl),
        )
        if rows and rows[0].get("view_definition"):
            return rows[0]["view_definition"]
        return None

    def get_row_count(self, table: str) -> int:
        """Return row count from Snowflake metadata (no scan).

        Uses ``information_schema.tables`` which Snowflake maintains
        automatically.
        """
        database, schema, tbl = self._resolve_table(table)
        rows = self.execute(
            f"select row_count from {database}.information_schema.tables "
            f"where table_schema = %s and table_name = %s",
            (schema, tbl),
        )
        return rows[0].get("row_count", 0) if rows else 0

    def get_table_row_counts(self, table_names: list[str]) -> dict[str, int]:
        """Return row counts for all tables in one metadata query.

        Uses ``information_schema.tables`` — no table scans.
        """
        if not table_names:
            return {}
        # All table names share the same database/schema context
        db = self._database
        sch = self._schema
        rows = self.execute(
            f"select table_name, row_count from {db}.information_schema.tables "
            f"where table_schema = %s",
            (sch,),
        )
        metadata = {r.get("table_name", ""): r.get("row_count", 0) for r in rows}

        result: dict[str, int] = {}
        for name in table_names:
            upper_name = name.upper()
            result[name] = metadata.get(upper_name, 0)
        return result

    def sample_source(self, table: str, sample_size: int, *, row_count: int = 0) -> str:
        # Use block sampling for large tables (>10M rows). Block sampling
        # operates on whole micropartitions and is 5-10x faster because it
        # skips entire storage blocks rather than evaluating each row.
        from querido.connectors.base import validate_object_name

        validate_object_name(table)
        if sample_size <= 0:
            raise ValueError(f"sample_size must be positive, got {sample_size}")
        if row_count > 10_000_000:
            pct = max(sample_size / row_count * 100, 0.01)
            return f"(select * from {table} sample system ({pct:.4f})) as _sample"
        return f"(select * from {table} sample ({sample_size} rows)) as _sample"

    def cancel(self) -> None:
        """Cancel the currently executing query on the Snowflake connection."""
        import contextlib

        cursor = self._active_cursor
        if cursor is not None:
            with contextlib.suppress(Exception):
                cursor.cancel()  # type: ignore[union-attr]

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
        table = table.rename_columns([c.lower() for c in table.column_names])
        return table.to_pylist()

    def _fetch_standard(self, cursor: object) -> list[dict]:
        desc = cursor.description  # type: ignore[union-attr]
        if desc is None:
            return []
        columns = [d[0].lower() for d in desc]
        rows = cursor.fetchall()  # type: ignore[attr-defined]
        return [dict(zip(columns, row, strict=True)) for row in rows]
