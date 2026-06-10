from __future__ import annotations

import os
import tomllib
from pathlib import Path


def get_config_dir() -> Path:
    """Return the qdo config directory, respecting QDO_CONFIG env var."""
    env = os.environ.get("QDO_CONFIG")
    if env:
        return Path(env)

    from platformdirs import user_config_dir

    return Path(user_config_dir("qdo"))


def load_connections(config_dir: Path | None = None) -> dict:
    """Load connections from connections.toml."""
    if config_dir is None:
        config_dir = get_config_dir()

    config_file = config_dir / "connections.toml"
    if not config_file.exists():
        return {}

    with open(config_file, "rb") as f:
        data = tomllib.load(f)

    return data.get("connections", {})


def _write_toml_atomic(path: Path, data: dict) -> None:
    """Write a dict as TOML using atomic temp-file + rename."""
    import tempfile

    import tomli_w

    path.parent.mkdir(parents=True, exist_ok=True)
    raw = tomli_w.dumps(data).encode()
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    closed = False
    try:
        os.write(fd, raw)
        os.close(fd)
        closed = True
        Path(tmp).replace(path)
        path.chmod(0o600)
    except OSError:
        if not closed:
            os.close(fd)
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Column sets
# ---------------------------------------------------------------------------

_COLUMN_SETS_FILE = "column_sets.toml"


def _column_sets_path(config_dir: Path | None = None) -> Path:
    if config_dir is None:
        config_dir = get_config_dir()
    return config_dir / _COLUMN_SETS_FILE


def _load_column_sets_raw(config_dir: Path | None = None) -> dict:
    path = _column_sets_path(config_dir)
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _parse_legacy_key(key: str) -> tuple[str, str, str] | None:
    """Best-effort parse of a legacy dot-joined ``connection.table.set`` key.

    Table names may legitimately contain dots (``db.schema.table``), so the
    first segment is taken as the connection, the last as the set name, and
    everything in between as the table. This is correct as long as connection
    and set names themselves contain no dots (the common case).
    """
    parts = key.split(".")
    if len(parts) < 3:
        return None
    return parts[0], ".".join(parts[1:-1]), parts[-1]


def _load_column_set_entries(config_dir: Path | None = None) -> list[dict]:
    """Load all column-set entries as structured dicts.

    The current format stores explicit fields under ``[[sets]]``::

        [[sets]]
        connection = "snow"
        table = "db.schema.tbl"
        set = "wide"
        columns = ["a", "b"]

    Legacy files used flat ``"connection.table.set"`` keys; those are parsed
    best-effort (see :func:`_parse_legacy_key`) and migrated to the new
    format on the next write.
    """
    data = _load_column_sets_raw(config_dir)
    entries: list[dict] = []
    for raw in data.get("sets", []):
        if not isinstance(raw, dict):
            continue
        entries.append(
            {
                "connection": str(raw.get("connection", "")),
                "table": str(raw.get("table", "")),
                "set": str(raw.get("set", "")),
                "columns": list(raw.get("columns", [])),
            }
        )
    for key, value in data.items():
        if key == "sets" or not isinstance(value, dict) or "columns" not in value:
            continue
        parsed = _parse_legacy_key(key)
        if parsed is None:
            continue
        legacy_conn, legacy_table, legacy_set = parsed
        entries.append(
            {
                "connection": legacy_conn,
                "table": legacy_table,
                "set": legacy_set,
                "columns": list(value.get("columns", [])),
            }
        )
    return entries


def _write_column_set_entries(entries: list[dict], config_dir: Path | None = None) -> None:
    _write_toml_atomic(_column_sets_path(config_dir), {"sets": entries})


def _entry_matches(entry: dict, connection: str, table: str, set_name: str) -> bool:
    return (
        entry.get("connection") == connection
        and entry.get("table") == table
        and entry.get("set") == set_name
    )


def save_column_set(
    connection: str,
    table: str,
    set_name: str,
    columns: list[str],
    config_dir: Path | None = None,
) -> None:
    """Save a named column set for a connection + table."""
    entries = _load_column_set_entries(config_dir)
    entries = [e for e in entries if not _entry_matches(e, connection, table, set_name)]
    entries.append(
        {
            "connection": connection,
            "table": table,
            "set": set_name,
            "columns": list(columns),
        }
    )
    _write_column_set_entries(entries, config_dir)


def load_column_set(
    connection: str,
    table: str,
    set_name: str,
    config_dir: Path | None = None,
) -> list[str] | None:
    """Load a named column set. Returns None if not found."""
    for entry in _load_column_set_entries(config_dir):
        if _entry_matches(entry, connection, table, set_name):
            return list(entry.get("columns", []))
    return None


def list_column_sets(
    connection: str | None = None,
    table: str | None = None,
    config_dir: Path | None = None,
) -> list[dict]:
    """List column sets, optionally filtered by connection and/or table.

    Returns a list of ``{"connection", "table", "set", "columns"}`` dicts.
    """
    result: list[dict] = []
    for entry in _load_column_set_entries(config_dir):
        if connection and entry.get("connection") != connection:
            continue
        if table and entry.get("table") != table:
            continue
        result.append(entry)
    return result


def delete_column_set(
    connection: str,
    table: str,
    set_name: str,
    config_dir: Path | None = None,
) -> bool:
    """Delete a named column set. Returns True if it existed."""
    entries = _load_column_set_entries(config_dir)
    kept = [e for e in entries if not _entry_matches(e, connection, table, set_name)]
    if len(kept) == len(entries):
        return False
    _write_column_set_entries(kept, config_dir)
    return True


class ConnectionNotFoundError(ValueError):
    """Raised when a --connection value names a connection that isn't configured.

    Subclasses :class:`ValueError` so best-effort callers that already treat
    resolution problems as soft failures keep working; the CLI error layer
    checks for this class first and maps it to ``CONNECTION_NOT_FOUND``.
    """


_LOCAL_DB_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".duckdb", ".ddb", ".parquet")


def _looks_like_path(value: str) -> bool:
    """Heuristic: does *value* look like a file path rather than a connection name?"""
    if "/" in value or os.sep in value or value.startswith("~"):
        return True
    return value.lower().endswith(_LOCAL_DB_SUFFIXES)


def _expand_local_paths(config: dict) -> dict:
    """Return a copy of *config* with ``~`` expanded in local file paths."""
    out = dict(config)
    for key in ("path", "parquet_path"):
        val = out.get(key)
        if isinstance(val, str) and val.startswith("~"):
            out[key] = os.path.expanduser(val)
    return out


def resolve_connection(connection: str, db_type: str | None = None) -> dict:
    """Resolve a --connection value to a config dict.

    First tries to look up as a named connection in the config file.
    If not found, treats it as a file path (with ``~`` expanded).
    """
    connections = load_connections()

    if connection in connections:
        return _expand_local_paths(connections.get(connection, {}))

    # Treat as a file path — expand ~ and infer type from extension if not provided
    expanded = os.path.expanduser(connection)
    if db_type is None:
        if expanded.endswith(".duckdb") or expanded.endswith(".ddb"):
            db_type = "duckdb"
        elif expanded.endswith(".parquet"):
            # parquet_path is consumed by factory.py to register the file as a DuckDB view
            return {"type": "duckdb", "path": ":memory:", "parquet_path": expanded}
        else:
            db_type = "sqlite"

    # Validate the file exists for local database types
    path = Path(expanded)
    if db_type in ("sqlite", "duckdb") and not path.exists():
        named = ", ".join(sorted(connections)) if connections else None
        if not _looks_like_path(connection):
            # No path separators and no database file extension — almost
            # certainly a mistyped connection name, not a missing file.
            msg = f"Connection '{connection}' not found."
            if named:
                msg += f" Available connections: {named}"
            else:
                msg += " No connections are configured."
            raise ConnectionNotFoundError(msg)
        msg = f"Database file not found: {expanded}"
        if named:
            msg += f"\nNamed connections available: {named}"
        msg += (
            "\nTo add a named connection run: "
            "qdo config add --name <name> --type <type> --path <path>"
        )
        raise FileNotFoundError(msg)

    return {"type": db_type, "path": expanded}
