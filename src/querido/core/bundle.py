"""Knowledge bundles — export, import, inspect, diff.

A knowledge bundle is a portable archive of what a user/agent has learned
about some part of a database: enriched table metadata and (optionally)
saved column sets.  Bundles are connection-agnostic — tables are matched
across connections by a schema fingerprint (hash of column names + types),
and ``--map source=target`` renames tables on import.

Layout::

    <name>.qdobundle/
      manifest.yaml          # format_version, qdo_version, author, created_at, tables, column_sets
      metadata/
        <table>.yaml         # per-table YAML + schema_fingerprint
      column-sets/
        <table>.<set>.yaml   # {connection_source, table_source, set_name, columns}

Note:
    Sessions are intentionally excluded from bundles in this MVP.  A future
    phase may add ``sessions/`` as a sibling directory for shipping an
    investigation log alongside the metadata it produced.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from querido.core.metadata import _read_yaml, _write_yaml

if TYPE_CHECKING:
    from querido.connectors.base import Connector


BUNDLE_FORMAT_VERSION = "1"

_IMPORTABLE_TABLE_FIELDS = {
    "table_description",
    "data_owner",
    "update_frequency",
    "notes",
}
_MACHINE_TABLE_FIELDS = {"row_count", "table_comment"}
_NEVER_IMPORT_TABLE_FIELDS = {"table", "connection", "schema_fingerprint", "columns"}

_IMPORTABLE_COLUMN_FIELDS = {
    "description",
    "pii",
    "valid_values",
    "temporal",
    "likely_sparse",
}
_MACHINE_COLUMN_FIELDS = {
    "type",
    "nullable",
    "primary_key",
    "distinct_count",
    "null_count",
    "null_pct",
    "min_val",
    "max_val",
    "min_length",
    "max_length",
    "sample_values",
}
_REDACT_COLUMN_FIELDS = {"sample_values", "min_val", "max_val", "valid_values"}


# ---------------------------------------------------------------------------
# Schema fingerprint
# ---------------------------------------------------------------------------


def _normalize_type(t: str) -> str:
    """Strip parameterization and uppercase.  ``VARCHAR(255)`` → ``VARCHAR``."""
    t = (t or "").strip().upper()
    t = re.sub(r"\(.*\)", "", t)
    return t.strip()


def compute_schema_fingerprint(columns: list[dict]) -> str:
    """Stable 16-char hex of sorted ``(name_lower, normalized_type)`` pairs."""
    items = sorted(
        (str(c.get("name", "")).lower(), _normalize_type(c.get("type", ""))) for c in columns
    )
    payload = "|".join(f"{n}:{t}" for n, t in items)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _fingerprint_for_table(connector: Connector, table: str) -> str | None:
    try:
        cols = connector.get_columns(table)
    except Exception:
        return None
    return compute_schema_fingerprint(cols)


# ---------------------------------------------------------------------------
# Provenance helpers
# ---------------------------------------------------------------------------


def _is_provenance(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and "value" in value
        and "source" in value
        and "confidence" in value
    )


def _confidence_of(value: Any) -> float:
    """Return the confidence attached to a field.

    Provenance dicts use their ``confidence``.  Plain scalars and lists are
    treated as human-authored (``1.0``) when non-empty / non-placeholder,
    else ``0.0``.  Missing fields return ``0.0``.
    """
    if value is None:
        return 0.0
    if _is_provenance(value):
        try:
            return float(value.get("confidence", 0.0))
        except (TypeError, ValueError):
            return 0.0
    if isinstance(value, str):
        s = value.strip()
        if not s or s.startswith("<"):
            return 0.0
        return 1.0
    if isinstance(value, list):
        return 1.0 if value else 0.0
    return 1.0


def _written_at_of(value: Any, fallback_mtime: float) -> str:
    """Extract a sortable ``written_at`` string.  Falls back to file mtime."""
    if _is_provenance(value):
        wa = value.get("written_at")
        if isinstance(wa, str) and wa:
            return wa
    return datetime.fromtimestamp(fallback_mtime, UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Bundle reading (dir or zip)
# ---------------------------------------------------------------------------


@contextmanager
def _open_bundle(path: str | Path) -> Iterator[Path]:
    """Yield a directory Path whether *path* is a dir or a ``.zip``/``.qdobundle`` zip."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Bundle not found: {p}")
    if p.is_dir():
        yield p
        return

    # Treat as zip
    tmp = Path(tempfile.mkdtemp(prefix="qdobundle-read-"))
    try:
        with zipfile.ZipFile(p) as zf:
            zf.extractall(tmp)
        # Zip may wrap its contents in a single top-level directory
        entries = [e for e in tmp.iterdir() if not e.name.startswith(".")]
        if len(entries) == 1 and entries[0].is_dir() and (entries[0] / "manifest.yaml").exists():
            yield entries[0]
        else:
            yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_bundle(
    connection: str,
    tables: list[str],
    output_path: str | Path,
    *,
    include_column_sets: bool = True,
    redact: bool = False,
    author: str | None = None,
    as_zip: bool = False,
) -> dict:
    """Package metadata (and optional column sets) for *tables* into a bundle.

    Returns the written manifest as a dict.
    """
    from querido import __version__
    from querido.config import list_column_sets, resolve_connection
    from querido.connectors.factory import create_connector
    from querido.core.metadata import show_metadata
    from querido.core.metadata_write import _resolve_author

    output_path = Path(output_path)

    # Pull fingerprints from the live DB.
    config = resolve_connection(connection)
    fingerprints: dict[str, str | None] = {}
    with create_connector(config) as conn:
        for t in tables:
            fingerprints[t] = _fingerprint_for_table(conn, t)

    staging = Path(tempfile.mkdtemp(prefix="qdobundle-export-"))
    try:
        meta_dir = staging / "metadata"
        meta_dir.mkdir()

        table_entries: list[dict] = []
        missing: list[str] = []
        for t in tables:
            meta = show_metadata(connection, t)
            if meta is None:
                missing.append(t)
                continue
            out = dict(meta)
            out.pop("connection", None)
            out["schema_fingerprint"] = fingerprints.get(t)
            if redact:
                _apply_redact(out)
            _write_yaml(meta_dir / f"{t}.yaml", out)
            table_entries.append({"name": t, "schema_fingerprint": fingerprints.get(t)})

        column_set_entries: list[dict] = []
        if include_column_sets:
            cs_dir = staging / "column-sets"
            cs_dir.mkdir()
            table_set = set(tables)
            for key, cols in list_column_sets(connection=connection).items():
                parts = key.split(".", 2)
                if len(parts) != 3:
                    continue
                _src_conn, src_table, set_name = parts
                if src_table not in table_set:
                    continue
                payload = {
                    "connection_source": _src_conn,
                    "table_source": src_table,
                    "set_name": set_name,
                    "columns": list(cols),
                }
                _write_yaml(cs_dir / f"{src_table}.{set_name}.yaml", payload)
                column_set_entries.append(
                    {"table": src_table, "name": set_name, "columns": list(cols)}
                )

        manifest = {
            "format_version": BUNDLE_FORMAT_VERSION,
            "qdo_version": __version__,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "author": author or _resolve_author(),
            "connection_source": connection,
            "tables": table_entries,
            "missing_tables": missing,
            "column_sets": column_set_entries,
            "redacted": redact,
        }
        _write_yaml(staging / "manifest.yaml", manifest)

        if as_zip:
            if output_path.exists():
                output_path.unlink()
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _dirs, files in os.walk(staging):
                    for f in files:
                        full = Path(root) / f
                        zf.write(full, full.relative_to(staging))
        else:
            if output_path.exists():
                if output_path.is_dir():
                    shutil.rmtree(output_path)
                else:
                    output_path.unlink()
            shutil.copytree(staging, output_path)

        return manifest
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _apply_redact(meta: dict) -> None:
    """In-place: drop PII-sensitive column fields where ``pii`` is true."""
    for col in meta.get("columns") or []:
        pii = col.get("pii")
        is_pii = pii is True or (isinstance(pii, dict) and bool(pii.get("value")) is True)
        if not is_pii:
            continue
        for field in _REDACT_COLUMN_FIELDS:
            col.pop(field, None)


# ---------------------------------------------------------------------------
# Inspect / diff
# ---------------------------------------------------------------------------


def inspect_bundle(bundle_path: str | Path) -> dict:
    """Return a summary of a bundle's contents (manifest + counts)."""
    with _open_bundle(bundle_path) as root:
        manifest = _read_yaml(root / "manifest.yaml") or {}
        metadata_files = (
            sorted((root / "metadata").glob("*.yaml")) if (root / "metadata").exists() else []
        )
        cs_files = (
            sorted((root / "column-sets").glob("*.yaml"))
            if (root / "column-sets").exists()
            else []
        )
        return {
            "path": str(bundle_path),
            "manifest": manifest,
            "metadata_count": len(metadata_files),
            "column_set_count": len(cs_files),
            "tables": [f.stem for f in metadata_files],
        }


def diff_bundles(a: str | Path, b: str | Path) -> dict:
    """Compare two bundles.  Reports tables/column-sets only in a or b, and
    per-table schema_fingerprint differences.
    """
    with _open_bundle(a) as ra, _open_bundle(b) as rb:
        a_tables = _bundle_tables(ra)
        b_tables = _bundle_tables(rb)
        only_a = sorted(set(a_tables) - set(b_tables))
        only_b = sorted(set(b_tables) - set(a_tables))
        shared = sorted(set(a_tables) & set(b_tables))
        drifts = [
            {"table": t, "a": a_tables[t], "b": b_tables[t]}
            for t in shared
            if a_tables[t] != b_tables[t]
        ]

        a_cs = _bundle_column_set_keys(ra)
        b_cs = _bundle_column_set_keys(rb)
        return {
            "a": str(a),
            "b": str(b),
            "tables_only_in_a": only_a,
            "tables_only_in_b": only_b,
            "shared_tables": shared,
            "schema_drifts": drifts,
            "column_sets_only_in_a": sorted(a_cs - b_cs),
            "column_sets_only_in_b": sorted(b_cs - a_cs),
        }


def _bundle_tables(root: Path) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    meta_dir = root / "metadata"
    if not meta_dir.exists():
        return result
    for f in meta_dir.glob("*.yaml"):
        meta = _read_yaml(f) or {}
        result[f.stem] = meta.get("schema_fingerprint")
    return result


def _bundle_column_set_keys(root: Path) -> set[str]:
    cs_dir = root / "column-sets"
    if not cs_dir.exists():
        return set()
    return {f.stem for f in cs_dir.glob("*.yaml")}


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def import_bundle(
    bundle_path: str | Path,
    target_connection: str,
    *,
    maps: dict[str, str] | None = None,
    strategy: str = "keep-higher-confidence",
    apply: bool = False,
) -> dict:
    """Import a bundle into *target_connection*.

    Without ``apply``, returns a dry-run report of what would change.  With
    ``apply=True``, writes merged metadata and column sets and returns the
    same report with ``applied=True`` entries.
    """
    if strategy not in ("keep-higher-confidence", "theirs", "mine", "ask"):
        raise ValueError(f"Unknown merge strategy: {strategy}")
    maps = dict(maps or {})

    from querido.config import resolve_connection, save_column_set
    from querido.connectors.factory import create_connector
    from querido.core.metadata import metadata_path, show_metadata

    with _open_bundle(bundle_path) as root:
        manifest = _read_yaml(root / "manifest.yaml") or {}
        bundle_tables = manifest.get("tables") or []

        # Compute target fingerprints (best-effort — missing DB just skips check).
        target_fps: dict[str, str | None] = {}
        try:
            config = resolve_connection(target_connection)
            with create_connector(config) as conn:
                existing: set[str] = set()
                with suppress(Exception):
                    existing = {str(r.get("name")) for r in conn.get_tables()}
                for entry in bundle_tables:
                    src = entry.get("name")
                    if not src:
                        continue
                    tgt = maps.get(src, src)
                    if tgt in existing:
                        target_fps[tgt] = _fingerprint_for_table(conn, tgt)
                    else:
                        target_fps[tgt] = None
        except Exception:
            pass

        table_diffs: list[dict] = []
        for entry in bundle_tables:
            src = entry.get("name")
            if not src:
                continue
            tgt = maps.get(src, src)
            bundle_meta_path = root / "metadata" / f"{src}.yaml"
            if not bundle_meta_path.exists():
                continue
            bundle_mtime = bundle_meta_path.stat().st_mtime
            bundle_meta = _read_yaml(bundle_meta_path) or {}

            local_meta = show_metadata(target_connection, tgt) or {}
            local_path = metadata_path(target_connection, tgt)
            local_mtime = local_path.stat().st_mtime if local_path.exists() else 0.0

            src_fp = entry.get("schema_fingerprint") or bundle_meta.get("schema_fingerprint")
            tgt_fp = target_fps.get(tgt)
            fp_status = _fingerprint_status(src_fp, tgt_fp)

            merged, field_actions = _merge_table_metadata(
                local=local_meta,
                incoming=bundle_meta,
                strategy=strategy,
                skip_unknown_columns=(fp_status == "drift"),
                local_mtime=local_mtime,
                incoming_mtime=bundle_mtime,
            )
            merged["connection"] = target_connection
            merged["table"] = tgt
            merged.pop("schema_fingerprint", None)

            if apply and field_actions:
                _write_yaml(local_path, merged)

            table_diffs.append(
                {
                    "source_table": src,
                    "target_table": tgt,
                    "fingerprint_status": fp_status,
                    "source_fingerprint": src_fp,
                    "target_fingerprint": tgt_fp,
                    "field_actions": field_actions,
                    "applied": apply and bool(field_actions),
                }
            )

        # Column sets
        cs_diffs: list[dict] = []
        cs_dir = root / "column-sets"
        if cs_dir.exists():
            for f in sorted(cs_dir.glob("*.yaml")):
                payload = _read_yaml(f) or {}
                src_table = payload.get("table_source", "")
                tgt_table = maps.get(src_table, src_table)
                set_name = payload.get("set_name", "")
                columns = list(payload.get("columns") or [])
                if apply and set_name:
                    save_column_set(target_connection, tgt_table, set_name, columns)
                cs_diffs.append(
                    {
                        "source_table": src_table,
                        "target_table": tgt_table,
                        "name": set_name,
                        "columns": columns,
                        "applied": apply and bool(set_name),
                    }
                )

        return {
            "manifest": manifest,
            "target_connection": target_connection,
            "strategy": strategy,
            "maps": maps,
            "tables": table_diffs,
            "column_sets": cs_diffs,
            "applied": apply,
        }


def _fingerprint_status(src: str | None, tgt: str | None) -> str:
    if tgt is None:
        return "no_local_table" if src else "unknown"
    if src is None:
        return "unknown"
    return "match" if src == tgt else "drift"


def _merge_table_metadata(
    *,
    local: dict,
    incoming: dict,
    strategy: str,
    skip_unknown_columns: bool,
    local_mtime: float,
    incoming_mtime: float,
) -> tuple[dict, list[dict]]:
    """Merge *incoming* bundle metadata into *local*.  Returns (merged, actions)."""
    merged = dict(local) if local else dict(incoming)  # base to preserve structure
    if not local:
        # Starting fresh: drop machine fields from incoming (they describe the
        # source DB, not the target), but keep structure.
        merged = {k: v for k, v in incoming.items() if k not in _MACHINE_TABLE_FIELDS}

    actions: list[dict] = []

    # Table-level authored fields
    for field in sorted(_IMPORTABLE_TABLE_FIELDS | _extra_table_fields(incoming)):
        if field in _NEVER_IMPORT_TABLE_FIELDS or field in _MACHINE_TABLE_FIELDS:
            continue
        inc = incoming.get(field)
        loc = local.get(field) if local else None
        decision = _decide(loc, inc, strategy, local_mtime, incoming_mtime)
        if decision == "write":
            merged[field] = inc
            actions.append({"column": None, "field": field, "action": "write", "reason": strategy})
        elif decision == "skip" and inc is not None:
            actions.append(
                {
                    "column": None,
                    "field": field,
                    "action": "skip",
                    "reason": _skip_reason(loc, inc, strategy),
                }
            )

    # Columns
    local_cols = {c.get("name"): c for c in (local.get("columns") or []) if isinstance(c, dict)}
    merged_cols = list(merged.get("columns") or [])
    merged_by_name = {c.get("name"): c for c in merged_cols if isinstance(c, dict)}

    for inc_col in incoming.get("columns") or []:
        if not isinstance(inc_col, dict):
            continue
        name = inc_col.get("name")
        if not name:
            continue
        loc_col = local_cols.get(name)
        if loc_col is None and skip_unknown_columns:
            actions.append(
                {"column": name, "field": None, "action": "skip", "reason": "schema_drift"}
            )
            continue
        if loc_col is None:
            # No local column with that name but fingerprint matched / unknown —
            # still safe to write authored fields, writing as a new entry.
            new_col = {k: v for k, v in inc_col.items() if k not in _MACHINE_COLUMN_FIELDS}
            merged_cols.append(new_col)
            merged_by_name[name] = new_col
            actions.extend(
                {"column": name, "field": field, "action": "write", "reason": "new_column"}
                for field in sorted(_IMPORTABLE_COLUMN_FIELDS & set(inc_col.keys()))
            )
            continue

        target_col = merged_by_name.get(name)
        if target_col is None:
            continue

        for field in sorted(_IMPORTABLE_COLUMN_FIELDS | _extra_column_fields(inc_col)):
            if field in _MACHINE_COLUMN_FIELDS:
                continue
            if field not in inc_col:
                continue
            inc_v = inc_col.get(field)
            loc_v = loc_col.get(field)
            decision = _decide(loc_v, inc_v, strategy, local_mtime, incoming_mtime)
            if decision == "write":
                target_col[field] = inc_v
                actions.append(
                    {"column": name, "field": field, "action": "write", "reason": strategy}
                )
            elif decision == "skip" and inc_v is not None:
                actions.append(
                    {
                        "column": name,
                        "field": field,
                        "action": "skip",
                        "reason": _skip_reason(loc_v, inc_v, strategy),
                    }
                )

    merged["columns"] = merged_cols
    return merged, actions


def _extra_table_fields(incoming: dict) -> set[str]:
    """Return unknown authored-looking fields on the table root."""
    return {
        k
        for k, v in incoming.items()
        if k not in _NEVER_IMPORT_TABLE_FIELDS
        and k not in _MACHINE_TABLE_FIELDS
        and k not in _IMPORTABLE_TABLE_FIELDS
        and (_is_provenance(v) or isinstance(v, (str, bool, list)))
    }


def _extra_column_fields(col: dict) -> set[str]:
    return {
        k
        for k, v in col.items()
        if k != "name"
        and k not in _MACHINE_COLUMN_FIELDS
        and k not in _IMPORTABLE_COLUMN_FIELDS
        and (_is_provenance(v) or isinstance(v, (str, bool, list)))
    }


def _decide(
    local_v: Any,
    incoming_v: Any,
    strategy: str,
    local_mtime: float,
    incoming_mtime: float,
) -> str:
    """Return ``"write"`` or ``"skip"`` for a single field."""
    if incoming_v is None:
        return "skip"
    if local_v is None or _confidence_of(local_v) == 0.0:
        return "write"
    if strategy == "theirs":
        return "write"
    if strategy == "mine":
        return "skip"
    # keep-higher-confidence (and "ask" falls back to this in non-interactive
    # contexts — the CLI layer handles interactive prompting).
    lc = _confidence_of(local_v)
    ic = _confidence_of(incoming_v)
    if ic > lc:
        return "write"
    if ic < lc:
        return "skip"
    # Tie: newer wins
    la = _written_at_of(local_v, local_mtime)
    ia = _written_at_of(incoming_v, incoming_mtime)
    return "write" if ia > la else "skip"


def _skip_reason(local_v: Any, incoming_v: Any, strategy: str) -> str:
    if strategy == "mine":
        return "local_wins"
    if _confidence_of(local_v) > _confidence_of(incoming_v):
        return "local_higher_confidence"
    return "local_newer"


__all__ = [
    "BUNDLE_FORMAT_VERSION",
    "compute_schema_fingerprint",
    "diff_bundles",
    "export_bundle",
    "import_bundle",
    "inspect_bundle",
]
