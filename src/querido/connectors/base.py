import re
from typing import Protocol, Self, runtime_checkable

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _validate_identifier(name: str, kind: str) -> str:
    """Validate an identifier to prevent SQL injection.

    Allows letters, digits, underscores, and dots (for schema-qualified names).
    Raises ValueError if the name contains unsafe characters.

    This is a deliberate allowlist (validate, don't escape): qdo interpolates
    identifiers into SQL templates and sampling subqueries, so it accepts only
    plain identifiers and rejects names needing quoting — spaces, hyphens, ``$``,
    or unicode. Such names are legal when quoted in every supported dialect, but
    supporting them would mean carrying an escaping layer across three dialects;
    qdo keeps the security boundary simple instead. Rename or alias such a column
    in a view if you need to explore it.
    """
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(
            f"Invalid {kind} name: {name!r}. "
            "For SQL-injection safety qdo accepts only plain identifiers: a name "
            "must start with a letter or underscore and contain only letters, "
            "digits, underscores, and dots. Names that would need quoting (spaces, "
            "hyphens, '$', unicode) are not supported — alias the column in a view."
        )
    return name


def validate_table_name(name: str) -> str:
    """Validate a table name to prevent SQL injection."""
    return _validate_identifier(name, "table")


def validate_column_name(name: str) -> str:
    """Validate a column name to prevent SQL injection."""
    return _validate_identifier(name, "column")


def validate_object_name(name: str) -> str:
    """Validate a fully-qualified object name (e.g. db.schema.table)."""
    return _validate_identifier(name, "object")


def quote_qualified_name(name: str) -> str:
    """Quote a (possibly schema-qualified) identifier per segment.

    ``schema.table`` becomes ``"schema"."table"`` rather than a single
    quoted identifier containing a dot. Segments are assumed already
    validated by :func:`validate_table_name` / :func:`validate_column_name`.
    """
    return ".".join(f'"{part}"' for part in name.split("."))


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class ConnectorError(Exception):
    """Base exception for all connector errors.

    Wraps driver-specific exceptions (``sqlite3.Error``, ``duckdb.Error``,
    ``snowflake.connector.Error``) so CLI code can isinstance-check against
    a dialect-neutral hierarchy instead of string-matching driver messages.
    """


class TableNotFoundError(ConnectorError):
    """Raised when a referenced table does not exist."""

    def __init__(self, table: str, available: list[str] | None = None) -> None:
        self.table = table
        self.available = available or []
        super().__init__(f"Table not found: {table!r}")


class ColumnNotFoundError(ConnectorError):
    """Raised when a referenced column does not exist."""

    def __init__(self, column: str, table: str, available: list[str] | None = None) -> None:
        self.column = column
        self.table = table
        self.available = available or []
        super().__init__(f"Column {column!r} not found in table {table!r}")


class DatabaseLockedError(ConnectorError):
    """Raised when the database is locked by another process."""


class DatabaseOpenError(ConnectorError):
    """Raised when the database file cannot be opened (missing, permission denied, corrupt)."""


class AuthenticationError(ConnectorError):
    """Raised when driver authentication fails (bad credentials, expired token)."""


class DatabaseError(ConnectorError):
    """Generic wrapper for driver errors that don't fit a narrower subclass."""


def wrap_driver_error(exc: Exception) -> ConnectorError | None:
    """Classify a raw driver exception into a :class:`ConnectorError` subclass.

    Returns ``None`` when *exc* doesn't match a known pattern — callers
    should re-raise the original in that case so tracebacks stay intact.

    Message-pattern matching is intentionally centralized here so each
    connector wraps driver errors the same way and CLI-layer code can
    switch on exception type instead of parsing messages.
    """
    msg = str(exc).lower()
    # Column errors first: "does not exist" / "invalid identifier" are used by
    # Snowflake and DuckDB for missing columns too, so match those before the
    # table branch to avoid misclassifying a column error as a missing table.
    if (
        "no such column" in msg
        or "invalid identifier" in msg
        or ("column" in msg and ("does not exist" in msg or "not found" in msg))
    ):
        return ColumnNotFoundError(str(exc), "")
    if "no such table" in msg:
        return TableNotFoundError(str(exc))
    if "does not exist" in msg or "not found" in msg:
        # Snowflake/DuckDB phrasing for a missing table/object/relation. Column
        # cases were already handled above. We can't reliably extract the bare
        # identifier from an arbitrary driver message, so only wrap as a table
        # error when the message is table/object/relation-shaped; otherwise fall
        # through to the generic wrapper rather than stuffing the whole message
        # into TableNotFoundError.table.
        if any(kw in msg for kw in ("table", "object", "relation", "view")):
            return TableNotFoundError(str(exc))
        return DatabaseError(str(exc))
    if "database is locked" in msg:
        return DatabaseLockedError(str(exc))
    if "unable to open database" in msg or "could not open" in msg:
        return DatabaseOpenError(str(exc))
    if "readonly database" in msg or "read-only" in msg:
        # SQLite: "attempt to write a readonly database";
        # DuckDB: "Cannot execute statement ... in read-only mode!".
        return DatabaseError(
            f"{exc} (connections are read-only by default; use --allow-write for write statements)"
        )
    # Auth: match auth-shaped phrases, not any message merely containing the
    # word "password" (e.g. a query referencing a column called password).
    if (
        "authentication" in msg
        or "incorrect username or password" in msg
        or "invalid password" in msg
        or "password is incorrect" in msg
        or "password expired" in msg
        or "authentication token" in msg
    ):
        return AuthenticationError(str(exc))
    return None


# ---------------------------------------------------------------------------
# Connector Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Connector(Protocol):
    dialect: str
    supports_concurrent_queries: bool

    def execute(self, sql: str, params: dict | tuple | None = None) -> list[dict]:
        """Execute SQL and return results as list of dicts."""
        ...

    def get_tables(self, *, database: str | None = None, schema: str | None = None) -> list[dict]:
        """Return list of tables/views with keys: name, type.

        *database* and *schema* are optional overrides for connectors
        that support them (Snowflake).  Other connectors ignore them.
        """
        ...

    def get_columns(self, table: str) -> list[dict]:
        """Return column metadata for a table."""
        ...

    def get_table_comment(self, table: str) -> str | None:
        """Return the table-level comment/description, or None."""
        ...

    def get_view_definition(self, view: str) -> str | None:
        """Return the SQL definition of a view, or None if not a view."""
        ...

    def get_row_count(self, table: str) -> int:
        """Return the (possibly estimated) row count for *table*.

        Connectors should use metadata lookups when possible to avoid a
        full table scan.  The result is used for sampling decisions where
        an estimate is acceptable.
        """
        ...

    def get_table_row_counts(self, table_names: list[str]) -> dict[str, int]:
        """Return estimated row counts for multiple tables in one call.

        Returns a dict mapping table name to row count.  Connectors
        should use bulk metadata queries when possible to avoid N+1
        query patterns.
        """
        ...

    def sample_source(self, table: str, sample_size: int, *, row_count: int = 0) -> str:
        """Return a SQL source expression for sampling *sample_size* rows.

        When *row_count* is provided and the table is very large, connectors
        may use block-level sampling (percentage-based) for better performance.
        """
        ...

    def cancel(self) -> None:
        """Cancel a running query.  Default is a no-op.

        Behavior varies by connector: SQLite/DuckDB call ``conn.interrupt()``
        which cancels all queries on the connection, while Snowflake calls
        ``cursor.cancel()`` which only cancels the active cursor's query.
        """
        ...

    def close(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...


@runtime_checkable
class ArrowConnector(Connector, Protocol):
    """Extended connector that supports returning results as PyArrow Tables.

    Connectors that implement ``execute_arrow()`` enable zero-copy data
    handling in operations like profiling.  Use
    ``connectors/arrow_util.py:execute_arrow_or_dicts()`` to
    opportunistically take the Arrow path with automatic fallback for
    connectors that only implement the base ``Connector`` protocol.
    """

    def execute_arrow(self, sql: str, params: dict | tuple | None = None) -> object:
        """Execute SQL and return results as a PyArrow Table."""
        ...
