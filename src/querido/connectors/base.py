import re
from typing import Protocol, Self

_SAFE_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def validate_table_name(name: str) -> str:
    """Validate a table name to prevent SQL injection.

    Allows letters, digits, underscores, and dots (for schema.table).
    Raises ValueError if the name contains unsafe characters.
    """
    if not _SAFE_TABLE_NAME.match(name):
        raise ValueError(
            f"Invalid table name: {name!r}. "
            "Names must start with a letter or underscore and contain only "
            "letters, digits, underscores, and dots."
        )
    return name


class Connector(Protocol):
    dialect: str

    def execute(self, sql: str, params: dict | tuple | None = None) -> list[dict]:
        """Execute SQL and return results as list of dicts."""
        ...

    def get_columns(self, table: str) -> list[dict]:
        """Return column metadata for a table."""
        ...

    def close(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(self, *args: object) -> None: ...
