"""Metadata scoring and suggestion (Phase 1.4).

``score_connection`` ranks tables by metadata completeness so agents
have a measurable target. ``build_suggestions`` re-runs the deterministic
scans used by ``--write-metadata`` and returns a preview diff — what
would be added, without writing. ``apply_suggestions`` writes them.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from querido.core.metadata import (
    _read_yaml,
    get_metadata_dir,
    metadata_path,
)
from querido.core.metadata_write import (
    FieldUpdate,
    _is_human_field,
    apply_updates,
    derive_from_profile,
    derive_from_quality,
    derive_from_values,
)

if TYPE_CHECKING:
    from querido.connectors.base import Connector


# Weights for the composite score (must sum to 1.0)
_W_DESCRIPTION = 0.5
_W_VALID_VALUES = 0.3
_W_FRESHNESS = 0.2

# Freshness decay: full credit <=7d, zero >=90d, linear between.
_FRESH_FULL_DAYS = 7.0
_FRESH_STALE_DAYS = 90.0

# Same low-cardinality cutoff used by the derivation rules.
_LOW_CARDINALITY_MAX = 20

# Cache ceiling above which we suggest running metadata suggest from scans.
LOW_SCORE_THRESHOLD = 0.5

_STRING_TYPE_TOKENS = ("CHAR", "TEXT", "STRING", "VARCHAR")


# -- scoring ------------------------------------------------------------------


def _is_string_type(col_type: str) -> bool:
    up = (col_type or "").upper()
    return any(tok in up for tok in _STRING_TYPE_TOKENS)


def _has_valid_values(col: dict) -> bool:
    vv = col.get("valid_values")
    if vv is None:
        return False
    if isinstance(vv, list):
        return len(vv) > 0
    if isinstance(vv, dict):
        return vv.get("value") not in (None, [], "")
    return bool(vv)


def _freshness_score(age_days: float) -> float:
    if age_days <= _FRESH_FULL_DAYS:
        return 1.0
    if age_days >= _FRESH_STALE_DAYS:
        return 0.0
    span = _FRESH_STALE_DAYS - _FRESH_FULL_DAYS
    return max(0.0, 1.0 - (age_days - _FRESH_FULL_DAYS) / span)


def score_table(meta: dict, *, mtime: float | None = None, now: float | None = None) -> dict:
    """Compute a completeness score for one stored metadata dict.

    Returns a dict with ``score`` (0.0-1.0, rounded to 2 decimals),
    percentage components, and lists of columns missing descriptions /
    valid_values so callers can guide the user / agent to the gaps.
    """
    columns = meta.get("columns") or []
    total = len(columns)

    described = 0
    vv_target = 0
    vv_filled = 0
    missing_descriptions: list[str] = []
    missing_valid_values: list[str] = []

    for col in columns:
        name = col.get("name") or ""
        if _is_human_field(col.get("description")):
            described += 1
        else:
            missing_descriptions.append(name)

        distinct = col.get("distinct_count")
        if (
            _is_string_type(col.get("type") or "")
            and isinstance(distinct, (int, float))
            and 1 < distinct <= _LOW_CARDINALITY_MAX
        ):
            vv_target += 1
            if _has_valid_values(col):
                vv_filled += 1
            else:
                missing_valid_values.append(name)

    desc_pct = 100.0 * described / total if total else 100.0
    # If no columns qualify as valid_values targets, treat as full credit —
    # we don't want to punish tables with nothing enumerable.
    vv_pct = 100.0 * vv_filled / vv_target if vv_target else 100.0

    now_ts = now if now is not None else time.time()
    age_days: float | None = None
    if mtime is not None:
        age_days = max(0.0, (now_ts - mtime) / 86400.0)
        freshness = _freshness_score(age_days)
    else:
        freshness = 0.0

    composite = (
        _W_DESCRIPTION * (desc_pct / 100.0)
        + _W_VALID_VALUES * (vv_pct / 100.0)
        + _W_FRESHNESS * freshness
    )

    return {
        "table": meta.get("table") or "",
        "score": round(composite, 2),
        "column_count": total,
        "column_description_pct": round(desc_pct, 1),
        "valid_values_coverage_pct": round(vv_pct, 1),
        "valid_values_targets": vv_target,
        "freshness_days": round(age_days, 1) if age_days is not None else None,
        "missing_descriptions": missing_descriptions,
        "missing_valid_values": missing_valid_values,
    }


def score_connection(connection: str) -> dict:
    """Score every table with a metadata YAML under *connection*.

    Tables are returned sorted worst-first so the output makes clear
    where the next author effort should go.
    """
    meta_dir = get_metadata_dir(connection)
    if not meta_dir.exists():
        return {"connection": connection, "tables": [], "average_score": None}

    rows: list[dict] = []
    for yaml_file in sorted(meta_dir.glob("*.yaml")):
        meta = _read_yaml(yaml_file)
        if meta is None:
            continue
        rows.append(score_table(meta, mtime=yaml_file.stat().st_mtime))

    rows.sort(key=lambda r: (r.get("score", 0.0), r.get("table", "")))
    avg = round(sum(r.get("score", 0.0) for r in rows) / len(rows), 2) if rows else None

    return {"connection": connection, "tables": rows, "average_score": avg}


# -- suggestions --------------------------------------------------------------


def _existing_column_fields(meta: dict) -> dict[str, set[str]]:
    """Map column name → set of fields that already have a human or auto entry."""
    out: dict[str, set[str]] = {}
    for col in meta.get("columns") or []:
        name = col.get("name")
        if not isinstance(name, str):
            continue
        fields: set[str] = set()
        for key in ("temporal", "likely_sparse", "valid_values"):
            if key in col and col[key] not in (None, ""):
                fields.add(key)
        out[name] = fields
    return out


def _filter_novel(updates: list[FieldUpdate], meta: dict, *, force: bool) -> list[FieldUpdate]:
    """Drop updates that would land on a human-authored field (unless *force*)
    or are already present as an auto entry with the same value."""
    cols_by_name: dict[str, dict] = {}
    for col in meta.get("columns") or []:
        name = col.get("name")
        if isinstance(name, str):
            cols_by_name[name] = col

    keep: list[FieldUpdate] = []
    for upd in updates:
        if upd.column is None:
            container = meta
        else:
            container = cols_by_name.get(upd.column)
            if container is None:
                continue
        existing = container.get(upd.field)
        if _is_human_field(existing) and not force:
            continue
        # Skip if an auto entry already has the identical value
        if isinstance(existing, dict) and existing.get("value") == upd.value:
            continue
        keep.append(upd)
    return keep


def build_suggestions(
    connector: Connector,
    connection: str,
    table: str,
    *,
    force: bool = False,
) -> list[FieldUpdate]:
    """Run deterministic scans and return field updates that are both novel
    and allowed under the human-field protection rules."""
    from querido.core.profile import get_profile
    from querido.core.quality import get_quality
    from querido.core.values import get_distinct_values

    profile_result = get_profile(connector, table, quick=False)
    stats = profile_result.get("stats") or []
    col_info = profile_result.get("col_info") or []

    quality_result = get_quality(connector, table)

    candidates: list[FieldUpdate] = []
    temporal_columns: set[str] = set()
    for upd in derive_from_profile(stats, col_info):
        candidates.append(upd)
        if upd.field == "temporal" and isinstance(upd.column, str):
            temporal_columns.add(upd.column)
    candidates.extend(derive_from_quality(quality_result))

    # For each low-cardinality string column, fetch values and derive
    # valid_values. We look at the profile stats so we only run a values
    # query per column that looks promising.
    for row in stats:
        name = row.get("column_name")
        if not isinstance(name, str) or not name:
            continue
        distinct = row.get("distinct_count")
        is_stringy = row.get("min_length") is not None
        if name in temporal_columns:
            continue
        if (
            is_stringy
            and isinstance(distinct, (int, float))
            and 1 < distinct <= _LOW_CARDINALITY_MAX
        ):
            values_result = get_distinct_values(
                connector, table, name, max_values=_LOW_CARDINALITY_MAX
            )
            candidates.extend(derive_from_values(values_result))

    meta = _read_yaml(metadata_path(connection, table)) or {}
    return _filter_novel(candidates, meta, force=force)


def apply_suggestions(
    connector: Connector,
    connection: str,
    table: str,
    updates: list[FieldUpdate],
    *,
    force: bool = False,
) -> dict:
    """Write *updates* to the metadata YAML, grouping by source."""
    by_source: dict[str, list[FieldUpdate]] = {}
    for upd in updates:
        src = _infer_source(upd)
        by_source.setdefault(src, []).append(upd)

    combined_written: list[dict] = []
    combined_skipped: list[dict] = []
    path = str(metadata_path(connection, table))
    for src, batch in by_source.items():
        summary = apply_updates(connector, connection, table, batch, source=src, force=force)
        combined_written.extend(summary.get("written") or [])
        combined_skipped.extend(summary.get("skipped") or [])
        path = summary.get("path", path)

    return {"written": combined_written, "skipped": combined_skipped, "path": path}


def _infer_source(update: FieldUpdate) -> str:
    """Map a FieldUpdate back to its scan source for provenance tagging."""
    if update.field == "temporal":
        return "profile"
    if update.field == "valid_values":
        return "values"
    if update.field == "likely_sparse":
        return "quality"
    return "profile"


def suggestions_to_dicts(updates: list[FieldUpdate]) -> list[dict[str, Any]]:
    """Serialize a list of :class:`FieldUpdate` for JSON output."""
    return [
        {
            "column": u.column,
            "field": u.field,
            "value": u.value,
            "confidence": u.confidence,
            "source": _infer_source(u),
        }
        for u in updates
    ]


# -- next-steps helper --------------------------------------------------------


def peek_score(connection: str, table: str) -> float | None:
    """Return the table's stored metadata score, or None if no file.

    Cheap enough to call from ``next_steps`` rules — reads one YAML off
    disk. Returns the composite score (0.0-1.0) rounded to 2 decimals.
    """
    path = metadata_path(connection, table)
    if not path.exists():
        return None
    meta = _read_yaml(path)
    if not meta:
        return None
    result = score_table(meta, mtime=path.stat().st_mtime)
    return result.get("score")
