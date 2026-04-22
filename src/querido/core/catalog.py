"""Full database catalog — tables, columns, row counts in one call."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
                "name": t.get("name", ""),
                "type": t.get("type", ""),
                "row_count": None,
                "columns": None,
            }
            for t in raw_tables
        ]
        return {"tables": tables, "table_count": len(tables)}

    # Fetch all row counts in bulk (1 query instead of N).
    table_names = [t.get("name", "") for t in raw_tables]
    from querido.connectors.base import ConnectorError

    try:
        row_counts = connector.get_table_row_counts(table_names)
    except ConnectorError:
        # Best-effort — fall through to per-table counts below.
        row_counts = {}

    concurrent = getattr(connector, "supports_concurrent_queries", False)

    if concurrent and len(raw_tables) > 1:
        tables = _fetch_parallel(connector, raw_tables, row_counts)
    else:
        tables = [_fetch_table_detail(connector, t, row_counts) for t in raw_tables]

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
                    "name": t.get("name", ""),
                    "type": t.get("type", ""),
                    "row_count": None,
                    "columns": None,
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


def enrich_catalog(catalog: dict, connection: str) -> dict:
    """Merge stored metadata into a catalog result.

    For each table with a ``.qdo/metadata/<connection>/<table>.yaml`` file,
    adds ``table_description``, ``data_owner``, ``update_frequency``, and
    per-column ``description`` fields from the stored metadata.
    """
    from querido.core.metadata import list_metadata, show_metadata

    available = {e.get("table", ""): e for e in list_metadata(connection)}
    if not available:
        return catalog

    enriched_tables = []
    for table in catalog.get("tables", []):
        table_name = table.get("name", "")
        if table_name not in available:
            enriched_tables.append(table)
            continue

        meta = show_metadata(connection, table_name)
        if meta is None:
            enriched_tables.append(table)
            continue

        enriched = dict(table)

        # Table-level human fields
        for key in ("table_description", "data_owner", "update_frequency", "notes"):
            val = meta.get(key, "")
            if val and not str(val).startswith("<"):
                enriched[key] = val

        # Column-level descriptions
        if enriched.get("columns") and meta.get("columns"):
            meta_cols = {c.get("name", "").lower(): c for c in meta.get("columns", [])}
            enriched_cols = []
            for col in enriched.get("columns", []):
                col_copy = dict(col)
                mc = meta_cols.get(col_copy.get("name", "").lower(), {})
                desc = mc.get("description", "")
                if desc and not str(desc).startswith("<"):
                    col_copy["description"] = desc
                pii = mc.get("pii")
                if pii is not None:
                    col_copy["pii"] = pii
                valid = mc.get("valid_values")
                if valid:
                    col_copy["valid_values"] = valid
                enriched_cols.append(col_copy)
            enriched["columns"] = enriched_cols

        enriched_tables.append(enriched)

    return {
        "tables": enriched_tables,
        "table_count": catalog.get("table_count", len(enriched_tables)),
    }


def filter_catalog(catalog: dict, pattern: str) -> dict:
    """Filter catalog tables and columns by a case-insensitive substring pattern.

    A table is included if its name matches OR if any of its columns match.
    When a table is included via column matches, all columns are retained
    (the match is for inclusion, not trimming).
    """
    pat = pattern.lower()
    filtered = []
    for table in catalog.get("tables", []):
        name = table.get("name", "")
        table_match = pat in name.lower()
        columns = table.get("columns") or []
        column_match = any(pat in c.get("name", "").lower() for c in columns)
        if table_match or column_match:
            filtered.append(table)
    return {"tables": filtered, "table_count": len(filtered)}


def get_function_catalog(
    connector: Connector,
    *,
    pattern: str | None = None,
    schema: str | None = None,
) -> dict[str, Any]:
    """Return a function catalog for dialects that expose one."""
    if connector.dialect == "sqlite":
        return {
            "dialect": connector.dialect,
            "supported": False,
            "reason": "Function catalog is not supported for sqlite connections.",
            "schema": None,
            "function_count": 0,
            "functions": [],
            "sql": None,
        }

    sql, resolved_schema = _render_function_catalog_sql(connector, schema=schema)
    raw_functions = connector.execute(sql)
    functions = _summarize_function_rows(connector.dialect, raw_functions)
    if pattern:
        functions = filter_function_catalog(functions, pattern)

    return {
        "dialect": connector.dialect,
        "supported": True,
        "reason": None,
        "schema": resolved_schema,
        "function_count": len(functions),
        "functions": functions,
        "sql": sql,
    }


def filter_function_catalog(functions: list[dict[str, Any]], pattern: str) -> list[dict[str, Any]]:
    """Filter function entries by a case-insensitive substring pattern."""
    pat = pattern.lower()
    return [
        entry
        for entry in functions
        if pat in str(entry.get("name", "")).lower() or pat in str(entry.get("schema", "")).lower()
    ]


def _render_function_catalog_sql(
    connector: Connector, *, schema: str | None
) -> tuple[str, str | None]:
    from querido.connectors.base import validate_object_name
    from querido.sql.renderer import render_template

    if connector.dialect == "duckdb":
        return render_template("catalog_functions", "duckdb"), schema or "main"

    if connector.dialect == "snowflake":
        database = str(getattr(connector, "_database", "") or "")
        resolved_schema = str(schema or getattr(connector, "_schema", "") or "")
        if not database or not resolved_schema:
            missing = []
            if not database:
                missing.append("'database'")
            if not resolved_schema:
                missing.append("'schema'")
            raise ValueError(
                f"Cannot list functions — {' and '.join(missing)} not set. "
                "Set them in your connection config or pass --schema with a configured database."
            )
        validate_object_name(database)
        validate_object_name(resolved_schema)
        return (
            render_template(
                "catalog_functions",
                "snowflake",
                database=database,
                schema=resolved_schema.upper(),
            ),
            resolved_schema.upper(),
        )

    raise ValueError(f"Function catalog is not supported for {connector.dialect} connections.")


def _summarize_function_rows(dialect: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}

    for row in rows:
        schema = str(row.get("schema", "") or "")
        name = str(row.get("name", "") or "")
        fn_type = str(row.get("type", "") or "function")
        if not name:
            continue

        key = (schema, name, fn_type)
        entry = grouped.setdefault(
            key,
            {
                "schema": schema,
                "name": name,
                "type": fn_type,
                "overload_count": 0,
                "return_types": set(),
                "notes": set(),
                "_languages": set(),
            },
        )
        entry["overload_count"] += 1

        return_type = row.get("return_type")
        if return_type:
            entry["return_types"].add(str(return_type))

        description = row.get("description")
        if description and "description" not in entry:
            entry["description"] = str(description)

        if row.get("internal"):
            entry["notes"].add("internal")
        if row.get("has_side_effects"):
            entry["notes"].add("side effects")

        stability = row.get("stability")
        if stability:
            entry["notes"].add(str(stability))

        for category in row.get("categories") or []:
            entry["notes"].add(str(category))

        language = row.get("language")
        if language:
            entry["_languages"].add(str(language))

    summarized = []
    for entry in grouped.values():
        out = {
            "schema": entry["schema"],
            "name": entry["name"],
            "type": entry["type"],
            "overload_count": entry["overload_count"],
            "return_types": sorted(entry["return_types"]),
        }
        if entry.get("description"):
            out["description"] = entry["description"]
        if entry["notes"]:
            out["notes"] = sorted(entry["notes"])
        if dialect == "snowflake" and entry["_languages"]:
            out["languages"] = sorted(entry["_languages"])
        summarized.append(out)

    return sorted(
        summarized,
        key=lambda entry: (
            str(entry.get("schema", "")),
            str(entry.get("name", "")),
            str(entry.get("type", "")),
        ),
    )


def _fetch_table_detail(
    connector: Connector, table_info: dict, row_counts: dict[str, int] | None = None
) -> dict:
    """Fetch columns for a single table, using pre-fetched row counts."""
    name = table_info.get("name", "")
    columns = connector.get_columns(name)

    row_count: int | None = None
    if row_counts is not None:
        row_count = row_counts.get(name)
    if row_count is None:
        # Fallback: individual count for tables not in the bulk result
        from querido.connectors.base import ConnectorError

        try:
            row_count = connector.get_row_count(name)
        except ConnectorError:
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


def _fetch_parallel(
    connector: Connector, raw_tables: list[dict], row_counts: dict[str, int] | None = None
) -> list[dict]:
    """Fetch table details in parallel using thread pool."""
    from querido.core._concurrent import run_parallel_ordered

    return run_parallel_ordered(
        raw_tables,
        lambda t: _fetch_table_detail(connector, t, row_counts),
        max_workers=4,
    )
