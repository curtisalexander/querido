"""Table and column existence helpers with fuzzy suggestions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def require_snowflake(dialect: str, command: str) -> None:
    """Raise typer.BadParameter if *dialect* is not ``snowflake``."""
    if dialect != "snowflake":
        import typer

        raise typer.BadParameter(f"'{command}' requires a Snowflake connection (got {dialect}).")


def _fuzzy_suggestions(name: str, candidates: list[str], *, n: int = 3) -> list[str]:
    """Return up to *n* close matches for *name* from *candidates* using difflib."""
    from difflib import get_close_matches

    return get_close_matches(name.lower(), [c.lower() for c in candidates], n=n, cutoff=0.4)


def _format_not_found(
    kind: str,
    name: str,
    candidates: list[str],
    *,
    context: str = "",
    max_available: int = 30,
) -> str:
    """Build a 'not found' message with fuzzy suggestions.

    For small candidate lists, the full list is always shown.  For large lists
    (e.g. thousands of Snowflake tables) only fuzzy matches are shown.
    """
    msg = f"{kind} '{name}' not found"
    if context:
        msg += f" in {context}"
    msg += "."

    suggestions = _fuzzy_suggestions(name, candidates)
    if suggestions:
        # Map back to original casing
        lower_to_orig: dict[str, str] = {}
        for c in candidates:
            lower_to_orig.setdefault(c.lower(), c)
        originals = [lower_to_orig[s] for s in suggestions]
        msg += f"\nDid you mean: {', '.join(originals)}?"

    if candidates and len(candidates) <= max_available:
        msg += f"\nAvailable {kind.lower()}s: {', '.join(sorted(candidates))}"

    return msg


def resolve_table(connector: Connector, table: str) -> str:
    """Return the canonical table name (as stored in the database).

    Uses case-insensitive matching so users don't need to worry about casing.
    Raises typer.BadParameter with fuzzy suggestions on mismatch.
    """
    import typer

    # For Snowflake qualified names, resolve and check the right catalog.
    if "." in table and hasattr(connector, "_resolve_table"):
        from typing import cast

        from querido.connectors.snowflake import SnowflakeConnector

        sf = cast(SnowflakeConnector, connector)
        database, schema, tbl = sf._resolve_table(table)
        tables = sf.get_tables(database=database, schema=schema)
        table_names = [t["name"] for t in tables]
        for name in table_names:
            if name.lower() == tbl.lower():
                return f"{database}.{schema}.{name}"
        raise typer.BadParameter(_format_not_found("Table", table, table_names))

    tables = connector.get_tables()
    table_names = [t["name"] for t in tables]

    for name in table_names:
        if name.lower() == table.lower():
            return name

    raise typer.BadParameter(_format_not_found("Table", table, table_names))


def resolve_column(connector: Connector, table: str, column: str, *, label: str = "column") -> str:
    """Return the canonical column name (as stored in the database).

    Uses case-insensitive matching so users don't need to worry about casing.
    Raises typer.BadParameter with fuzzy suggestions on mismatch.
    """
    import typer

    col_meta = connector.get_columns(table)
    col_names = [c["name"] for c in col_meta]

    for name in col_names:
        if name.lower() == column.lower():
            return name

    raise typer.BadParameter(
        _format_not_found("Column", column, col_names, context=f"table '{table}'")
    )
