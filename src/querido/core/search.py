from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def search_metadata(
    connector: Connector,
    pattern: str,
    search_type: str,
    schema: str | None = None,
) -> list[dict]:
    """Search tables and columns for pattern matches.

    Returns a list of dicts with keys:
      - table_name: str
      - table_type: str ("table" or "view")
      - match_type: str ("table" or "column")
      - column_name: str | None (None for table-level matches)
      - column_type: str | None
    """
    pat = pattern.lower()
    results: list[dict] = []

    tables = connector.get_tables()

    if schema:
        schema_lower = schema.lower()
        tables = [t for t in tables if t["name"].lower().startswith(schema_lower + ".")]

    search_tables = search_type in ("table", "all")
    search_columns = search_type in ("column", "all")

    for tbl in tables:
        tbl_name = tbl["name"]
        tbl_type = tbl["type"]

        if search_tables and pat in tbl_name.lower():
            results.append(
                {
                    "table_name": tbl_name,
                    "table_type": tbl_type,
                    "match_type": "table",
                    "column_name": None,
                    "column_type": None,
                }
            )

        if search_columns:
            try:
                columns = connector.get_columns(tbl_name)
            except (ValueError, LookupError, OSError, RuntimeError):
                logging.getLogger(__name__).debug(
                    "Could not read columns for '%s'", tbl_name, exc_info=True
                )
                continue
            results.extend(
                {
                    "table_name": tbl_name,
                    "table_type": tbl_type,
                    "match_type": "column",
                    "column_name": col["name"],
                    "column_type": col["type"],
                }
                for col in columns
                if pat in col["name"].lower()
            )

    return results


def try_cached_search(
    connection_name: str,
    pattern: str,
    search_type: str,
    schema: str | None = None,
) -> list[dict] | None:
    """Try to search from cache. Returns None if cache is stale or empty."""
    try:
        from querido.cache import MetadataCache

        cache = MetadataCache()
        try:
            if not cache.is_fresh(connection_name):
                return None
            results = cache.search(connection_name, pattern, search_type)
            if schema:
                schema_lower = schema.lower()
                results = [
                    r for r in results if r["table_name"].lower().startswith(schema_lower + ".")
                ]
            return results
        finally:
            cache.close()
    except (ImportError, OSError, ValueError, RuntimeError):
        return None
