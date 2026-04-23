"""Metadata store — create, read, list, and refresh enriched table docs."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector

# Fields that are auto-populated from the database and safe to overwrite
_MACHINE_TABLE_FIELDS = {"row_count", "table_comment"}
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

# Fields that humans fill in — never overwritten by refresh
_HUMAN_COLUMN_FIELDS = {"description", "pii", "valid_values"}
_HUMAN_TABLE_FIELDS = {
    "table_description",
    "data_owner",
    "update_frequency",
    "notes",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)?")


@dataclass(frozen=True)
class MetadataSearchDoc:
    kind: str
    table: str
    column: str | None
    path: str
    excerpt: str
    term_freqs: Counter[str]
    length: int
    field_terms: dict[str, set[str]]


def get_metadata_dir(connection: str) -> Path:
    """Return the metadata directory for a connection.

    Defaults to ``.qdo/metadata/<connection>/`` in the current directory.
    Respects ``QDO_METADATA_DIR`` env var if set.

    File paths are sanitized to a safe directory name (basename without
    extension) to avoid nested directory issues.
    """
    import os

    safe_name = _sanitize_connection_name(connection)
    base = os.environ.get("QDO_METADATA_DIR")
    if base:
        return Path(base) / safe_name
    return Path(".qdo") / "metadata" / safe_name


def _sanitize_connection_name(connection: str) -> str:
    """Convert a connection string to a safe directory name.

    Named connections pass through unchanged. File paths are reduced
    to their stem (e.g., ``/path/to/my.db`` → ``my``).
    """
    # If it looks like a file path, use the stem
    if "/" in connection or "\\" in connection or connection.endswith((".db", ".duckdb", ".ddb")):
        return Path(connection).stem
    return connection


def metadata_path(connection: str, table: str) -> Path:
    """Return the path to a table's metadata YAML file."""
    return get_metadata_dir(connection) / f"{table}.yaml"


def metadata_history_dir(connection: str, table: str) -> Path:
    """Return the history directory for a table's metadata file."""
    safe_name = _sanitize_connection_name(connection)
    base = os.environ.get("QDO_METADATA_DIR")
    if base:
        return Path(base) / "_history" / safe_name / table
    return Path(".qdo") / "metadata_history" / safe_name / table


def undo_metadata(
    connection: str,
    table: str,
    *,
    steps: int = 1,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """Undo the last *steps* qdo-managed metadata writes for one table."""
    if steps <= 0:
        raise ValueError("--steps must be greater than 0.")

    path = metadata_path(connection, table)
    records = _read_history_records(connection, table)
    if not records:
        raise ValueError(
            f"No metadata undo history for {connection}/{table}. "
            "Only qdo-managed metadata writes can be undone."
        )
    if steps > len(records):
        raise ValueError(
            f"Cannot undo {steps} step(s) for {connection}/{table}; only {len(records)} "
            "qdo-managed write(s) are recorded."
        )

    target = records[-steps:]
    earliest = target[0]
    latest = target[-1]
    current_exists = path.exists()
    current_text = path.read_text(encoding="utf-8") if current_exists else None
    current_fingerprint = _fingerprint_text(current_text)
    expected_fingerprint = latest.get("after_fingerprint")
    if (
        not force
        and isinstance(expected_fingerprint, str)
        and current_fingerprint != expected_fingerprint
    ):
        raise ValueError(
            f"Metadata file has changed since the last qdo-managed write: {path}. "
            "Re-run with --force to restore the recorded snapshot."
        )

    restore_exists = bool(earliest.get("before_exists"))
    snapshot_rel = earliest.get("before_snapshot_path")
    restore_path = metadata_history_dir(connection, table) / str(snapshot_rel or "")
    restore_text: str | None = None
    if restore_exists:
        try:
            restore_text = restore_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(
                f"Metadata undo snapshot is missing for {connection}/{table}: {restore_path}"
            ) from exc

    summary = {
        "connection": connection,
        "table": table,
        "path": str(path),
        "steps": steps,
        "dry_run": dry_run,
        "restored": "delete" if not restore_exists else "snapshot",
        "writes_undone": [
            {
                "timestamp": record.get("timestamp"),
                "command": record.get("command"),
                "session": record.get("session"),
            }
            for record in reversed(target)
        ],
    }

    if dry_run:
        return summary

    if restore_exists:
        assert restore_text is not None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(restore_text, encoding="utf-8")
    else:
        with suppress(FileNotFoundError):
            path.unlink()

    _write_history_records(connection, table, records[:-steps])
    return summary


def init_metadata(
    connector: Connector,
    connection: str,
    table: str,
    *,
    sample_values: int = 3,
    force: bool = False,
) -> dict:
    """Generate and write a metadata YAML file for a table.

    Returns the metadata dict that was written.
    Raises FileExistsError if the file already exists (unless *force*).
    """
    path = metadata_path(connection, table)
    if path.exists() and not force:
        raise FileExistsError(f"Metadata already exists: {path}\nUse --force to overwrite.")

    from querido.core.template import get_template

    template = get_template(connector, table, sample_values=sample_values)

    # Build the YAML-ready dict
    meta = _template_to_metadata(template, connection)

    before_text = path.read_text(encoding="utf-8") if path.exists() else None
    _write_yaml(path, meta)
    _record_metadata_history(
        connection=connection,
        table=table,
        command="metadata init",
        before_text=before_text,
        after_path=path,
    )
    return meta


def show_metadata(connection: str, table: str) -> dict | None:
    """Read stored metadata for a table. Returns None if not found."""
    path = metadata_path(connection, table)
    if not path.exists():
        return None
    return _read_yaml(path)


# Fields surfaced to scanning commands (profile / quality / values / context)
# as part of the write→read compounding loop. Keep in sync with the fields
# written by metadata_write.py + the human-authored fields above.
_SURFACEABLE_COLUMN_FIELDS = (
    "description",
    "valid_values",
    "pii",
    "temporal",
    "likely_sparse",
)


def _unwrap_field(value: object) -> object | None:
    """Unwrap a stored metadata value to its plain form for read-back.

    * Provenance-wrapped values (``{value, source, confidence, ...}``) are
      unwrapped to their ``value``.
    * Placeholder strings (``<description>``), empty strings, and empty
      lists return ``None`` so callers can treat them as absent.
    """
    if isinstance(value, dict):
        keys = tuple(value.keys())
        if "value" in keys and "source" in keys:
            value = next((v for k, v in value.items() if k == "value"), None)
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.startswith("<"):
            return None
        return stripped
    if isinstance(value, list) and not value:
        return None
    return value


def load_column_metadata(connection: str, table: str) -> dict[str, dict]:
    """Return stored per-column metadata for *table* as a name → fields map.

    Reads the table's YAML (if any) and returns ``{column_name: {field: value}}``
    for fields in :data:`_SURFACEABLE_COLUMN_FIELDS` that are present and
    non-placeholder.  Provenance-wrapped values are unwrapped to plain form.

    This is the reader half of the compounding loop: ``profile``, ``quality``,
    ``values``, and ``context`` call it so earlier ``--write-metadata`` runs
    actually influence subsequent scans.

    Returns ``{}`` if the YAML is missing or has no surfaceable fields.
    """
    meta = show_metadata(connection, table)
    if not meta:
        return {}
    result: dict[str, dict] = {}
    for col in meta.get("columns") or []:
        if not isinstance(col, dict):
            continue
        name = col.get("name")
        if not isinstance(name, str):
            continue
        entry: dict = {}
        for field in _SURFACEABLE_COLUMN_FIELDS:
            if field not in col:
                continue
            unwrapped = _unwrap_field(col.get(field))
            if unwrapped is None:
                continue
            entry[field] = unwrapped
        if entry:
            result[name] = entry
    return result


def list_metadata(connection: str) -> list[dict]:
    """List all stored metadata files for a connection.

    ``completeness`` is the same composite score used by ``metadata score``
    (column descriptions + valid_values + freshness), expressed as 0-100.
    Reporting the same number here avoids the trap where ``suggest --apply``
    writes real fields and ``metadata list`` still reads 0%.
    """
    from querido.core.metadata_score import score_table

    meta_dir = get_metadata_dir(connection)
    if not meta_dir.exists():
        return []

    results = []
    for yaml_file in sorted(meta_dir.glob("*.yaml")):
        meta = _read_yaml(yaml_file)
        if meta is None:
            continue
        mtime = yaml_file.stat().st_mtime
        scored = score_table(meta, mtime=mtime)
        results.append(
            {
                "table": yaml_file.stem,
                "path": str(yaml_file),
                "last_modified": mtime,
                "completeness": round(100.0 * scored.get("score", 0.0), 1),
            }
        )
    return results


def search_metadata(
    connection: str,
    query: str,
    *,
    limit: int = 5,
) -> dict:
    """Search stored metadata documents for semantic-ish matches.

    The MVP is deterministic and local-only: it indexes stored YAML files and
    ranks table-level and column-level documents by weighted lexical overlap.
    """
    docs, file_count = _build_metadata_search_docs(connection)
    query_terms = _tokenize(query)
    doc_count = len(docs)
    avgdl = sum(doc.length for doc in docs) / doc_count if docs else 0.0
    doc_freqs = _document_frequencies(docs)

    results = []
    for doc in docs:
        score = _bm25_score(query_terms, doc, doc_freqs, avgdl, doc_count)
        score += _phrase_bonus(query, doc)
        if score <= 0:
            continue
        results.append(
            {
                "kind": doc.kind,
                "table": doc.table,
                "column": doc.column,
                "score": round(score, 3),
                "matched_terms": [term for term in query_terms if term in doc.term_freqs],
                "rationale": _build_search_rationale(query_terms, doc),
                "excerpt": doc.excerpt,
                "path": doc.path,
            }
        )

    results.sort(
        key=lambda item: (
            -float(item["score"]),
            str(item["table"]),
            str(item.get("column") or ""),
            str(item["kind"]),
        )
    )
    limited = results[: max(limit, 0)]
    return {
        "connection": connection,
        "query": query,
        "metadata_file_count": file_count,
        "searched_document_count": len(docs),
        "result_count": len(limited),
        "results": limited,
    }


def refresh_metadata(
    connector: Connector,
    connection: str,
    table: str,
    *,
    sample_values: int = 3,
) -> dict:
    """Re-run inspect/profile and update machine fields, preserving human fields.

    Returns the updated metadata dict.
    Raises FileNotFoundError if no existing metadata to refresh.
    """
    path = metadata_path(connection, table)
    if not path.exists():
        raise FileNotFoundError(f"No metadata to refresh: {path}\nRun 'qdo metadata init' first.")

    existing = _read_yaml(path)
    if existing is None:
        existing = {}

    from querido.core.template import get_template

    template = get_template(connector, table, sample_values=sample_values)
    fresh = _template_to_metadata(template, connection)

    merged = _merge_metadata(existing, fresh)

    before_text = path.read_text(encoding="utf-8")
    _write_yaml(path, merged)
    _record_metadata_history(
        connection=connection,
        table=table,
        command="metadata refresh",
        before_text=before_text,
        after_path=path,
    )
    return merged


def _build_metadata_search_docs(connection: str) -> tuple[list[MetadataSearchDoc], int]:
    meta_dir = get_metadata_dir(connection)
    if not meta_dir.exists():
        return [], 0

    docs: list[MetadataSearchDoc] = []
    yaml_files = sorted(meta_dir.glob("*.yaml"))
    for yaml_file in yaml_files:
        meta = _read_yaml(yaml_file)
        if not isinstance(meta, dict):
            continue
        path_str = str(yaml_file)
        table = str(meta.get("table") or yaml_file.stem)

        table_desc = _stringify_search_value(meta.get("table_description"))
        notes = _stringify_search_value(meta.get("notes"))
        owner = _stringify_search_value(meta.get("data_owner"))
        update_frequency = _stringify_search_value(meta.get("update_frequency"))
        table_comment = _stringify_search_value(meta.get("table_comment"))

        docs.append(
            _build_search_doc(
                kind="table",
                table=table,
                column=None,
                path=path_str,
                excerpt=_build_table_excerpt(
                    table_desc=table_desc,
                    owner=owner,
                    update_frequency=update_frequency,
                    notes=notes,
                    table_comment=table_comment,
                ),
                weighted_terms=(
                    _tokenize(table) * 6
                    + _tokenize(table_desc) * 5
                    + _tokenize(owner) * 3
                    + _tokenize(update_frequency) * 2
                    + _tokenize(table_comment) * 2
                    + _tokenize(notes) * 3
                ),
                field_terms={
                    "table": set(_tokenize(table)),
                    "description": set(_tokenize(table_desc)),
                    "owner": set(_tokenize(owner)),
                    "frequency": set(_tokenize(update_frequency)),
                    "notes": set(_tokenize(notes)),
                },
            )
        )

        for column_meta in meta.get("columns") or []:
            if not isinstance(column_meta, dict):
                continue
            column = column_meta.get("name")
            if not isinstance(column, str) or not column:
                continue
            description = _stringify_search_value(column_meta.get("description"))
            valid_values = _stringify_search_value(column_meta.get("valid_values"))
            pii = _stringify_search_value(column_meta.get("pii"))
            column_type = _stringify_search_value(column_meta.get("type"))
            docs.append(
                _build_search_doc(
                    kind="column",
                    table=table,
                    column=column,
                    path=path_str,
                    excerpt=_build_column_excerpt(
                        column=column,
                        column_type=column_type,
                        description=description,
                        valid_values=valid_values,
                        pii=pii,
                    ),
                    weighted_terms=(
                        _tokenize(column) * 6
                        + _tokenize(table) * 3
                        + _tokenize(description) * 5
                        + _tokenize(valid_values) * 4
                        + _tokenize(column_type) * 2
                        + _tokenize(pii) * 4
                    ),
                    field_terms={
                        "table": set(_tokenize(table)),
                        "column": set(_tokenize(column)),
                        "description": set(_tokenize(description)),
                        "valid_values": set(_tokenize(valid_values)),
                        "pii": set(_tokenize(pii)),
                        "type": set(_tokenize(column_type)),
                    },
                )
            )

    return docs, len(yaml_files)


def _build_search_doc(
    *,
    kind: str,
    table: str,
    column: str | None,
    path: str,
    excerpt: str,
    weighted_terms: list[str],
    field_terms: dict[str, set[str]],
) -> MetadataSearchDoc:
    term_freqs = Counter(weighted_terms)
    return MetadataSearchDoc(
        kind=kind,
        table=table,
        column=column,
        path=path,
        excerpt=excerpt,
        term_freqs=term_freqs,
        length=sum(term_freqs.values()),
        field_terms=field_terms,
    )


def _build_table_excerpt(
    *,
    table_desc: str,
    owner: str,
    update_frequency: str,
    notes: str,
    table_comment: str,
) -> str:
    parts = [table_desc]
    if owner:
        parts.append(f"Owner: {owner}")
    if update_frequency:
        parts.append(f"Update: {update_frequency}")
    if notes:
        parts.append(notes)
    if table_comment:
        parts.append(f"Comment: {table_comment}")
    return " | ".join(part for part in parts if part) or "No table description yet."


def _build_column_excerpt(
    *,
    column: str,
    column_type: str,
    description: str,
    valid_values: str,
    pii: str,
) -> str:
    parts = [f"{column} ({column_type})" if column_type else column]
    if description:
        parts.append(description)
    if valid_values:
        parts.append(f"Valid values: {valid_values}")
    if pii:
        parts.append(f"PII: {pii}")
    return " | ".join(part for part in parts if part)


def _stringify_search_value(value: object) -> str:
    unwrapped = _unwrap_field(value)
    if unwrapped is None:
        return ""
    if isinstance(unwrapped, bool):
        return "pii sensitive true" if unwrapped else "pii sensitive false"
    if isinstance(unwrapped, list):
        return ", ".join(str(item) for item in unwrapped if item is not None)
    return str(unwrapped)


def _tokenize(text: str) -> list[str]:
    terms: list[str] = []
    for token in _TOKEN_RE.findall(text.lower()):
        terms.append(token)
        if "-" in token or "_" in token:
            terms.extend(part for part in re.split(r"[-_]", token) if part and part != token)
    return terms


def _document_frequencies(docs: list[MetadataSearchDoc]) -> Counter[str]:
    doc_freqs: Counter[str] = Counter()
    for doc in docs:
        doc_freqs.update(doc.term_freqs.keys())
    return doc_freqs


def _bm25_score(
    query_terms: list[str],
    doc: MetadataSearchDoc,
    doc_freqs: Counter[str],
    avgdl: float,
    doc_count: int,
) -> float:
    if not query_terms or not doc.length or avgdl <= 0:
        return 0.0

    score = 0.0
    query_counts = Counter(query_terms)
    total_docs = max(doc_count, 1)
    for term, qf in query_counts.items():
        tf = doc.term_freqs.get(term, 0)
        if not tf:
            continue
        df = doc_freqs.get(term, 0)
        idf = math.log(1.0 + ((total_docs - df + 0.5) / (df + 0.5)))
        denom = tf + 1.5 * (1.0 - 0.75 + 0.75 * (doc.length / avgdl))
        score += qf * idf * ((tf * 2.5) / denom)
    return score


def _phrase_bonus(query: str, doc: MetadataSearchDoc) -> float:
    query_lc = query.lower().strip()
    if not query_lc:
        return 0.0

    bonus = 0.0
    table_lc = doc.table.lower()
    column_lc = (doc.column or "").lower()
    excerpt_lc = doc.excerpt.lower()

    if query_lc == table_lc or (column_lc and query_lc == column_lc):
        bonus += 8.0
    if query_lc in table_lc or (column_lc and query_lc in column_lc):
        bonus += 3.0
    if query_lc in excerpt_lc:
        bonus += 2.0

    matched_name_terms = len(set(_tokenize(query)) & (doc.field_terms.get("table", set())))
    matched_name_terms += len(set(_tokenize(query)) & (doc.field_terms.get("column", set())))
    bonus += matched_name_terms * 0.8
    return bonus


def _build_search_rationale(query_terms: list[str], doc: MetadataSearchDoc) -> str:
    reasons: list[str] = []
    for field, label in (
        ("column", "column name"),
        ("table", "table name"),
        ("description", "description"),
        ("valid_values", "valid values"),
        ("owner", "owner"),
        ("notes", "notes"),
        ("pii", "PII flag"),
    ):
        matched = sorted(set(query_terms) & doc.field_terms.get(field, set()))
        if matched:
            reasons.append(f"{label}: {', '.join(matched)}")
    return "; ".join(reasons[:3]) or "General metadata match."


def _template_to_metadata(template: dict, connection: str) -> dict:
    """Convert a get_template() result to the metadata YAML structure."""
    columns = []
    for col in template.get("columns", []):
        entry: dict = {
            "name": col.get("name", ""),
            "type": col.get("type", ""),
            "nullable": col.get("nullable", False),
            "primary_key": col.get("primary_key", False),
            # Human fields — placeholders
            "description": col.get("comment", "") or "<description>",
            # Machine fields
            "distinct_count": col.get("distinct_count"),
            "null_count": col.get("null_count"),
            "null_pct": col.get("null_pct"),
            "min_val": col.get("min_val"),
            "max_val": col.get("max_val"),
            "sample_values": col.get("sample_values", ""),
        }
        columns.append(entry)

    return {
        "table": template.get("table", ""),
        "connection": connection,
        "row_count": template.get("row_count", 0),
        "table_comment": template.get("table_comment", ""),
        # Human fields — placeholders
        "table_description": "<description>",
        "data_owner": "<data_owner>",
        "update_frequency": "<update_frequency>",
        "notes": "",
        "columns": columns,
    }


def _merge_metadata(existing: dict, fresh: dict) -> dict:
    """Merge fresh machine data into existing metadata, preserving human fields."""
    merged = dict(existing)

    # Update machine table fields
    for key in _MACHINE_TABLE_FIELDS:
        if key in fresh:
            merged[key] = fresh.get(key)

    # Preserve human table fields (only update if still placeholder)
    for key in _HUMAN_TABLE_FIELDS:
        if key not in merged:
            merged[key] = fresh.get(key, "")

    # Merge columns
    existing_cols = {c.get("name", ""): c for c in existing.get("columns", [])}
    fresh_cols = fresh.get("columns", [])

    merged_cols = []
    for fc in fresh_cols:
        name = fc.get("name", "")
        ec = existing_cols.get(name, {})

        col = dict(fc)
        # Preserve human column fields from existing
        for key in _HUMAN_COLUMN_FIELDS:
            if key in ec:
                col[key] = ec.get(key)

        merged_cols.append(col)

    merged["columns"] = merged_cols
    return merged


def _write_yaml(path: Path, data: dict) -> None:
    """Write a dict as YAML to *path*."""
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def _read_yaml(path: Path) -> dict | None:
    """Read a YAML file and return its contents as a dict."""
    import yaml

    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return None


def _history_log_path(connection: str, table: str) -> Path:
    return metadata_history_dir(connection, table) / "history.jsonl"


def _read_history_records(connection: str, table: str) -> list[dict]:
    path = _history_log_path(connection, table)
    if not path.exists():
        return []
    records: list[dict] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
    except OSError:
        return []
    return records


def _write_history_records(connection: str, table: str, records: list[dict]) -> None:
    path = _history_log_path(connection, table)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def _record_metadata_history(
    *,
    connection: str,
    table: str,
    command: str,
    before_text: str | None,
    after_path: Path,
) -> None:
    history_dir = metadata_history_dir(connection, table)
    history_dir.mkdir(parents=True, exist_ok=True)
    after_text = after_path.read_text(encoding="utf-8")
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    snapshot_name = (
        f"{len(_read_history_records(connection, table)) + 1:04d}-"
        f"{timestamp.replace(':', '').replace('+00:00', 'Z')}.yaml"
    )
    snapshot_rel: str | None = None
    if before_text is not None:
        snapshot_path = history_dir / snapshot_name
        snapshot_path.write_text(before_text, encoding="utf-8")
        snapshot_rel = snapshot_path.name

    record = {
        "timestamp": timestamp,
        "command": command,
        "session": os.environ.get("QDO_SESSION", "").strip() or None,
        "before_exists": before_text is not None,
        "before_snapshot_path": snapshot_rel,
        "before_fingerprint": _fingerprint_text(before_text),
        "after_fingerprint": _fingerprint_text(after_text),
    }
    records = _read_history_records(connection, table)
    records.append(record)
    _write_history_records(connection, table, records)


def _fingerprint_text(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
