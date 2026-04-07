"""Full database catalog — tables, columns, row counts in one call."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def get_catalog(
    connector: Connector,
    *,
    tables_only: bool = False,
    schema: str | None = None,
) -> dict:
    """Return the full catalog for a database connection.

    Returns::

        {
            "tables": [
                {
                    "name": str,
                    "type": "table" | "view",
                    "row_count": int | None,
                    "columns": [{"name", "type", "nullable", "comment"}, ...] | None,
                }
            ],
            "table_count": int,
        }

    When *tables_only* is True, ``columns`` and ``row_count`` are omitted
    (set to None) for a fast listing.
    """
    kwargs: dict = {}
    if schema is not None:
        kwargs["schema"] = schema
    raw_tables = connector.get_tables(**kwargs)

    if tables_only:
        tables = [
            {
                "name": t.get("name", ""), "type": t.get("type", ""),
                "row_count": None, "columns": None,
            }
            for t in raw_tables
        ]
        return {"tables": tables, "table_count": len(tables)}

    concurrent = getattr(connector, "supports_concurrent_queries", False)

    if concurrent and len(raw_tables) > 1:
        tables = _fetch_parallel(connector, raw_tables)
    else:
        tables = [_fetch_table_detail(connector, t) for t in raw_tables]

    return {"tables": tables, "table_count": len(tables)}


def get_catalog_cached(
    connection_name: str,
    *,
    tables_only: bool = False,
    ttl_seconds: int = 86400,
) -> dict | None:
    """Try to build a catalog from the local metadata cache.

    Returns None if the cache is stale or empty for this connection.
    """
    from querido.cache import MetadataCache

    cache = MetadataCache()
    try:
        if not cache.is_fresh(connection_name, ttl_seconds):
            return None

        cached_tables = cache.get_cached_tables(connection_name)
        if cached_tables is None:
            return None

        if tables_only:
            tables = [
                {
                    "name": t.get("name", ""), "type": t.get("type", ""),
                    "row_count": None, "columns": None,
                }
                for t in cached_tables
            ]
            return {"tables": tables, "table_count": len(tables)}

        # Build full catalog from cache (columns but no row counts)
        tables = []
        for t in cached_tables:
            cached_cols = cache.get_cached_columns(connection_name, t.get("name", ""))
            columns = None
            if cached_cols is not None:
                columns = [
                    {
                        "name": c.get("column_name", ""),
                        "type": c.get("column_type", ""),
                        "nullable": bool(c.get("nullable", False)),
                        "comment": c.get("comment") or "",
                    }
                    for c in cached_cols
                ]
            tables.append(
                {
                    "name": t.get("name", ""),
                    "type": t.get("type", ""),
                    "row_count": None,  # cache doesn't store row counts
                    "columns": columns,
                }
            )
        return {"tables": tables, "table_count": len(tables)}
    finally:
        cache.close()


def _fetch_table_detail(connector: Connector, table_info: dict) -> dict:
    """Fetch columns and row count for a single table."""
    from querido.sql.renderer import render_template

    name = table_info.get("name", "")
    columns = connector.get_columns(name)

    try:
        count_sql = render_template("count", connector.dialect, table=name)
        row_count = connector.execute(count_sql)[0].get("cnt", 0)
    except Exception:
        row_count = None

    return {
        "name": name,
        "type": table_info.get("type", ""),
        "row_count": row_count,
        "columns": [
            {
                "name": c.get("name", ""),
                "type": c.get("type", ""),
                "nullable": c.get("nullable", False),
                "comment": c.get("comment") or "",
            }
            for c in columns
        ],
    }


def _fetch_parallel(connector: Connector, raw_tables: list[dict]) -> list[dict]:
    """Fetch table details in parallel using thread pool."""
    from querido.core._concurrent import run_parallel_ordered

    return run_parallel_ordered(
        raw_tables,
        lambda t: _fetch_table_detail(connector, t),
        max_workers=4,
    )
