"""Write auto-derived metadata from scanning commands.

Implements Phase 1.3 of PLAN.md: ``--write-metadata`` on ``profile``,
``values``, and ``quality`` writes deterministic inferences (``temporal``,
``likely_sparse``, ``valid_values``) into a table's metadata YAML with
provenance tags.

Provenance model
----------------
An auto-derived field is written as a dict::

    valid_values:
      value: [active, inactive, pending]
      source: values          # profile | values | quality | human
      confidence: 0.8
      written_at: 2026-04-14T12:34:56+00:00
      author: calex

A plain scalar / list is treated as human-authored (``confidence == 1.0``)
and is never overwritten without ``--force``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from querido.core.metadata import _read_yaml, _write_yaml, metadata_path
from querido.core.quality import QualityResult
from querido.core.values import ValuesResult

if TYPE_CHECKING:
    from querido.connectors.base import Connector


VALID_VALUES_CARDINALITY_CEILING = 20
NULL_SPARSE_THRESHOLD = 95.0
TEMPORAL_NAME_SUFFIXES = ("_at", "_date", "_ts", "_time", "_timestamp")
TEMPORAL_TYPE_SUBSTRINGS = ("date", "time", "timestamp")


@dataclass
class FieldUpdate:
    """A single auto-derived metadata field."""

    field: str
    value: Any
    confidence: float
    column: str | None = None  # None = table-level


def _resolve_author() -> str:
    """Resolve the author string: ``$QDO_AUTHOR`` > git user.name > ``unknown``."""
    env_author = os.environ.get("QDO_AUTHOR", "").strip()
    if env_author:
        return env_author

    try:
        import subprocess

        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        name = result.stdout.strip()
        if name:
            return name
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return "unknown"


def _resolve_written_at() -> str:
    """Resolve ``written_at``: active session name, else ISO timestamp."""
    session = os.environ.get("QDO_SESSION", "").strip()
    if session:
        return session
    return datetime.now(UTC).isoformat(timespec="seconds")


def _provenance(value: Any, source: str, confidence: float, author: str, written_at: str) -> dict:
    return {
        "value": value,
        "source": source,
        "confidence": confidence,
        "written_at": written_at,
        "author": author,
    }


def _is_auto_written(field: Any) -> bool:
    """Return True if *field* is a provenance-wrapped auto-written value."""
    return (
        isinstance(field, dict)
        and "value" in field
        and "source" in field
        and "confidence" in field
    )


def _is_human_field(field: Any) -> bool:
    """Return True if *field* is human-authored (plain value or confidence 1.0).

    A missing field, a placeholder (``"<...>"``), an empty string/list, or an
    auto-written provenance dict with confidence < 1.0 all return False.
    """
    if field is None:
        return False
    if _is_auto_written(field):
        return float(field.get("confidence", 0)) >= 1.0
    # Plain scalar / list — check for placeholder / empty
    if isinstance(field, str):
        stripped = field.strip()
        return bool(stripped) and not stripped.startswith("<")
    if isinstance(field, list):
        return len(field) > 0
    return True


def derive_from_profile(stats: list[dict], col_info: list[dict]) -> list[FieldUpdate]:
    """Derive ``temporal`` from profile stats + column metadata."""
    updates: list[FieldUpdate] = []
    type_by_name = {c.get("name", ""): (c.get("type") or "") for c in col_info}
    for row in stats:
        name = row.get("column_name") or ""
        if not name:
            continue
        col_type = (type_by_name.get(name) or row.get("column_type") or "").lower()
        is_temporal_name = name.lower().endswith(TEMPORAL_NAME_SUFFIXES)
        is_temporal_type = any(s in col_type for s in TEMPORAL_TYPE_SUBSTRINGS)
        if is_temporal_name and is_temporal_type:
            updates.append(FieldUpdate(field="temporal", value=True, confidence=0.9, column=name))
    return updates


def derive_from_values(result: ValuesResult) -> list[FieldUpdate]:
    """Derive candidate ``valid_values`` from a ``values`` result."""
    column = result.get("column")
    if not column:
        return []
    distinct_count = result.get("distinct_count") or 0
    truncated = result.get("truncated", False)
    rows = result.get("values") or []
    if truncated or distinct_count == 0 or distinct_count >= VALID_VALUES_CARDINALITY_CEILING:
        return []

    # Only propose valid_values for string-shaped data
    string_values: list[str] = []
    for r in rows:
        v = r.get("value")
        if isinstance(v, str):
            string_values.append(v)
        elif v is None:
            continue
        else:
            # Mixed / non-string — skip
            return []
    if not string_values:
        return []

    return [
        FieldUpdate(
            field="valid_values",
            value=sorted(set(string_values)),
            confidence=0.8,
            column=column,
        )
    ]


def derive_from_quality(result: QualityResult) -> list[FieldUpdate]:
    """Derive ``likely_sparse`` from a ``quality`` result."""
    updates: list[FieldUpdate] = []
    for col in result.get("columns") or []:
        name = col.get("name") or ""
        if not name:
            continue
        null_pct = col.get("null_pct")
        if isinstance(null_pct, (int, float)) and null_pct > NULL_SPARSE_THRESHOLD:
            updates.append(
                FieldUpdate(field="likely_sparse", value=True, confidence=0.9, column=name)
            )
    return updates


def apply_updates(
    connector: Connector,
    connection: str,
    table: str,
    updates: list[FieldUpdate],
    *,
    source: str,
    force: bool = False,
) -> dict:
    """Merge *updates* into the table's metadata YAML and return a summary.

    Initializes the YAML (via :func:`metadata.init_metadata`) if it does not
    already exist. Never overwrites human-authored fields (plain values or
    provenance entries with ``confidence == 1.0``) unless *force* is True.

    Returns a summary dict::

        {"written": [...], "skipped": [...], "path": "<path>"}
    """
    from querido.core.metadata import init_metadata

    path = metadata_path(connection, table)
    if not path.exists():
        init_metadata(connector, connection, table)

    meta = _read_yaml(path) or {}
    author = _resolve_author()
    written_at = _resolve_written_at()

    cols_by_name: dict[str, dict] = {}
    for c in meta.get("columns") or []:
        n = c.get("name")
        if isinstance(n, str):
            cols_by_name[n] = c

    written: list[dict] = []
    skipped: list[dict] = []

    for upd in updates:
        target: dict | None
        if upd.column is None:
            target = meta
        else:
            target = cols_by_name.get(upd.column)
            if target is None:
                skipped.append(
                    {"column": upd.column, "field": upd.field, "reason": "column_not_found"}
                )
                continue

        existing = target.get(upd.field)
        if _is_human_field(existing) and not force:
            skipped.append({"column": upd.column, "field": upd.field, "reason": "human_authored"})
            continue

        target[upd.field] = _provenance(
            upd.value,
            source=source,
            confidence=upd.confidence,
            author=author,
            written_at=written_at,
        )
        written.append(
            {
                "column": upd.column,
                "field": upd.field,
                "value": upd.value,
                "confidence": upd.confidence,
            }
        )

    _write_yaml(path, meta)
    return {"written": written, "skipped": skipped, "path": str(path), "applied": True}


def preview_updates(
    connector: Connector,
    connection: str,
    table: str,
    updates: list[FieldUpdate],
    *,
    source: str,
    force: bool = False,
) -> dict:
    """Preview *updates* against the metadata YAML without writing anything."""
    path = metadata_path(connection, table)
    meta: dict[str, Any] = (_read_yaml(path) if path.exists() else {}) or {}

    cols_by_name: dict[str, dict] = {}
    for c in meta.get("columns") or []:
        n = c.get("name")
        if isinstance(n, str):
            cols_by_name[n] = c

    for col in connector.get_columns(table):
        name = col.get("name")
        if isinstance(name, str):
            cols_by_name.setdefault(name, {"name": name})

    written: list[dict] = []
    skipped: list[dict] = []

    for upd in updates:
        target: dict[str, Any]
        if upd.column is None:
            target = meta
        else:
            maybe_target = cols_by_name.get(upd.column)
            if maybe_target is None:
                skipped.append(
                    {"column": upd.column, "field": upd.field, "reason": "column_not_found"}
                )
                continue
            target = maybe_target

        existing = target.get(upd.field)
        if _is_human_field(existing) and not force:
            skipped.append({"column": upd.column, "field": upd.field, "reason": "human_authored"})
            continue

        written.append(
            {
                "column": upd.column,
                "field": upd.field,
                "value": upd.value,
                "confidence": upd.confidence,
                "source": source,
            }
        )

    return {"written": written, "skipped": skipped, "path": str(path), "applied": False}


def write_from_profile(
    connector: Connector,
    connection: str,
    table: str,
    stats: list[dict],
    col_info: list[dict],
    *,
    force: bool = False,
) -> dict:
    updates = derive_from_profile(stats, col_info)
    return apply_updates(connector, connection, table, updates, source="profile", force=force)


def preview_from_profile(
    connector: Connector,
    connection: str,
    table: str,
    stats: list[dict],
    col_info: list[dict],
    *,
    force: bool = False,
) -> dict:
    updates = derive_from_profile(stats, col_info)
    return preview_updates(connector, connection, table, updates, source="profile", force=force)


def write_from_values(
    connector: Connector,
    connection: str,
    table: str,
    result: ValuesResult,
    *,
    force: bool = False,
) -> dict:
    updates = derive_from_values(result)
    return apply_updates(connector, connection, table, updates, source="values", force=force)


def preview_from_values(
    connector: Connector,
    connection: str,
    table: str,
    result: ValuesResult,
    *,
    force: bool = False,
) -> dict:
    updates = derive_from_values(result)
    return preview_updates(connector, connection, table, updates, source="values", force=force)


def write_from_quality(
    connector: Connector,
    connection: str,
    table: str,
    result: QualityResult,
    *,
    force: bool = False,
) -> dict:
    updates = derive_from_quality(result)
    return apply_updates(connector, connection, table, updates, source="quality", force=force)


def preview_from_quality(
    connector: Connector,
    connection: str,
    table: str,
    result: QualityResult,
    *,
    force: bool = False,
) -> dict:
    updates = derive_from_quality(result)
    return preview_updates(connector, connection, table, updates, source="quality", force=force)


# Re-export for convenience
__all__ = [
    "FieldUpdate",
    "apply_updates",
    "derive_from_profile",
    "derive_from_quality",
    "derive_from_values",
    "preview_from_profile",
    "preview_from_quality",
    "preview_from_values",
    "preview_updates",
    "write_from_profile",
    "write_from_quality",
    "write_from_values",
]


def format_write_note(summary: dict) -> str:
    """Format a one-line summary of an ``apply_updates`` result for stderr."""
    written = summary.get("written") or []
    skipped = summary.get("skipped") or []
    path = summary.get("path", "")
    skipped_human = sum(1 for s in skipped if s.get("reason") == "human_authored")
    prefix = "metadata" if summary.get("applied", True) else "metadata plan"
    verb = "written to" if summary.get("applied", True) else "would be written to"
    parts = [f"{prefix}: {len(written)} field(s) {verb} {path}"]
    if skipped_human:
        parts.append(f"{skipped_human} skipped (human-authored; use --force to overwrite)")
    return "; ".join(parts)
