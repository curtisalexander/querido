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

        self.conn = snowflake.connector.connect(**kwargs)
        self._active_cursor: object | None = None

        # Use config values when available; fall back to querying the session
        # for any that are missing (needed for connections.toml where db/schema
        # are set externally, or partial configs with only one of the two).
        self._database: str = cfg_database
        self._schema: str = cfg_schema
        if not self._database or not self._schema:
            cursor = self.conn.cursor()
            try:
                cursor.execute("SELECT CURRENT_DATABASE(), CURRENT_SCHEMA()")
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
        cursor = self.conn.cursor()
        self._active_cursor = cursor
        try:
            cursor.execute(sql, params)
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

        cursor = self.conn.cursor()
        self._active_cursor = cursor
        try:
            cursor.execute(sql, params)
            if cursor.description is None:
                return pa.table({})
            batches = list(cursor.fetch_arrow_batches())
            if not batches:
                return pa.table({})
            return pa.concat_tables(batches)
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
            f"SELECT table_name, table_type FROM {db}.information_schema.tables "
            f"WHERE table_schema = %s ORDER BY table_name",
            (sch,),
        )
        return [
            {
                "name": r["TABLE_NAME"],
                "type": "view" if "VIEW" in r["TABLE_TYPE"] else "table",
            }
            for r in rows
        ]

    def get_columns(self, table: str) -> list[dict]:
        database, schema, tbl = self._resolve_table(table)
        rows = self.execute(
            f"SELECT column_name, data_type, is_nullable, column_default, comment "
            f"FROM {database}.information_schema.columns "
            f"WHERE table_schema = %s AND table_name = %s "
            f"ORDER BY ordinal_position",
            (schema, tbl),
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
        database, schema, tbl = self._resolve_table(table)
        rows = self.execute(
            f"SELECT comment FROM {database}.information_schema.tables "
            f"WHERE table_schema = %s AND table_name = %s",
            (schema, tbl),
        )
        if rows and rows[0].get("COMMENT"):
            return rows[0]["COMMENT"]
        return None

    def get_view_definition(self, view: str) -> str | None:
        """Return the SQL definition of a view from information_schema.views."""
        database, schema, tbl = self._resolve_table(view)
        rows = self.execute(
            f"SELECT view_definition FROM {database}.information_schema.views "
            f"WHERE table_schema = %s AND table_name = %s",
            (schema, tbl),
        )
        if rows and rows[0].get("VIEW_DEFINITION"):
            return rows[0]["VIEW_DEFINITION"]
        return None

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
        return table.to_pylist()

    def _fetch_standard(self, cursor: object) -> list[dict]:
        desc = cursor.description  # type: ignore[union-attr]
        if desc is None:
            return []
        columns = [d[0] for d in desc]
        rows = cursor.fetchall()  # type: ignore[attr-defined]
        return [dict(zip(columns, row, strict=True)) for row in rows]
