import re
from typing import Protocol, Self, runtime_checkable

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def validate_table_name(name: str) -> str:
    """Validate a table name to prevent SQL injection.

    Allows letters, digits, underscores, and dots (for schema.table).
    Raises ValueError if the name contains unsafe characters.
    """
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(
            f"Invalid table name: {name!r}. "
            "Names must start with a letter or underscore and contain only "
            "letters, digits, underscores, and dots."
        )
    return name


def validate_column_name(name: str) -> str:
    """Validate a column name to prevent SQL injection.

    Same rules as table names: letters, digits, underscores, and dots.
    """
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(
            f"Invalid column name: {name!r}. "
            "Names must start with a letter or underscore and contain only "
            "letters, digits, underscores, and dots."
        )
    return name


def validate_object_name(name: str) -> str:
    """Validate a fully-qualified object name for Snowflake queries.

    Allows letters, digits, underscores, and dots (for db.schema.table).
    Raises ValueError if the name contains unsafe characters.
    """
    if not _SAFE_IDENTIFIER.match(name):
        raise ValueError(
            f"Invalid object name: {name!r}. "
            "Names must start with a letter or underscore and contain only "
            "letters, digits, underscores, and dots."
        )
    return name


@runtime_checkable
class Connector(Protocol):
    dialect: str

    def execute(self, sql: str, params: dict | tuple | None = None) -> list[dict]:
        """Execute SQL and return results as list of dicts."""
        ...

    def get_tables(self) -> list[dict]:
        """Return list of tables/views with keys: name, type."""
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

    def cancel(self) -> None:
        """Cancel a running query.  Default is a no-op."""
        ...

    def close(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...
