"""Metadata store — create, read, list, and refresh enriched table docs."""

from __future__ import annotations

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

    _write_yaml(path, meta)
    return meta


def show_metadata(connection: str, table: str) -> dict | None:
    """Read stored metadata for a table. Returns None if not found."""
    path = metadata_path(connection, table)
    if not path.exists():
        return None
    return _read_yaml(path)


def list_metadata(connection: str) -> list[dict]:
    """List all stored metadata files for a connection.

    Returns a list of dicts with ``table``, ``path``, ``last_modified``,
    and ``completeness`` (percentage of human fields filled).
    """
    meta_dir = get_metadata_dir(connection)
    if not meta_dir.exists():
        return []

    results = []
    for yaml_file in sorted(meta_dir.glob("*.yaml")):
        meta = _read_yaml(yaml_file)
        if meta is None:
            continue
        results.append(
            {
                "table": yaml_file.stem,
                "path": str(yaml_file),
                "last_modified": yaml_file.stat().st_mtime,
                "completeness": _calc_completeness(meta),
            }
        )
    return results


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

    _write_yaml(path, merged)
    return merged


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


def _calc_completeness(meta: dict) -> float:
    """Calculate what percentage of human fields are filled (not placeholders)."""
    total = 0
    filled = 0

    for key in _HUMAN_TABLE_FIELDS:
        total += 1
        val = meta.get(key, "")
        if val and not str(val).startswith("<") and str(val).strip():
            filled += 1

    for col in meta.get("columns", []):
        for key in _HUMAN_COLUMN_FIELDS:
            if key == "description":
                total += 1
                val = col.get(key, "")
                if val and not str(val).startswith("<") and str(val).strip():
                    filled += 1

    return round(100.0 * filled / total, 1) if total else 100.0


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
    except Exception:
        return None
