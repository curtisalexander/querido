"""Table report data layer — aggregates context/quality/joins/metadata.

``build_table_report`` is a pure data function: it calls the existing
core modules, collates their output into a single dict, and hands it to
the HTML renderer. No HTML lives here; no SQL is new.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def build_table_report(
    connector: Connector,
    connection: str,
    table: str,
    *,
    command: str = "",
) -> dict:
    """Collect every section the HTML report renders.

    The returned shape is intentionally flat so the renderer can treat
    each section as optional and skip/empty-state it independently.
    """
    from querido.core.context import get_context
    from querido.core.joins import discover_joins
    from querido.core.metadata import show_metadata
    from querido.core.quality import get_quality

    # Context covers schema + per-column stats + sample values in one scan
    # (and pulls stored metadata on a background thread). Reuse it as the
    # schema source so the schema table has row-level stats too.
    ctx = get_context(connector, table, connection)

    quality = get_quality(connector, table)
    joins = discover_joins(connector, table)
    metadata = show_metadata(connection, table)

    return {
        "connection": connection,
        "table": table,
        "dialect": ctx.get("dialect", connector.dialect),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "row_count": ctx.get("row_count", 0),
        "table_comment": ctx.get("table_comment"),
        "table_description": ctx.get("table_description"),
        "columns": ctx.get("columns", []),
        "metadata": metadata,
        "quality": quality,
        "joins": joins,
        "command": command,
    }
