"""Report data layer — aggregates pure data for the HTML renderers.

``build_table_report`` collects context/quality/joins/metadata for a
single table. ``build_session_report`` collects step records + captured
stdout for a named session. Both return plain dicts; the HTML renderers
in :mod:`querido.output.report_html` translate them to single-file HTML.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
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


def build_session_report(
    name: str,
    *,
    cwd: Path | None = None,
    command: str = "",
) -> dict:
    """Collect step records + captured stdout for a named session.

    The returned shape is intentionally flat so the renderer can iterate
    ``steps`` and treat each card independently. ``stdout`` is loaded
    eagerly — sessions top out at a handful of KB per step, and a
    single-file HTML report needs the content inline anyway.

    Raises :class:`FileNotFoundError` if the session directory doesn't exist.
    """
    from querido.core.session import iter_steps, session_dir, sessions_root

    dir_ = session_dir(name, cwd)
    if not dir_.is_dir():
        raise FileNotFoundError(f"Session not found: {name}")

    sessions_base = sessions_root(cwd)

    steps: list[dict] = []
    for record in iter_steps(name, cwd):
        stdout_rel = record.get("stdout_path") or ""
        stdout_text = ""
        if stdout_rel:
            # ``stdout_path`` is stored relative to the parent of the
            # sessions directory (i.e. ``.qdo/``). Resolve it through the
            # sessions base so tests can override cwd.
            resolved = sessions_base.parent / stdout_rel
            if resolved.is_file():
                stdout_text = resolved.read_text(encoding="utf-8")
        steps.append({**record, "stdout": stdout_text})

    return {
        "session_name": name,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "step_count": len(steps),
        "steps": steps,
        "command": command,
    }
