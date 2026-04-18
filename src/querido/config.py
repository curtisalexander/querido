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


def _set_key(connection: str, table: str, set_name: str) -> str:
    return f"{connection}.{table}.{set_name}"


def save_column_set(
    connection: str,
    table: str,
    set_name: str,
    columns: list[str],
    config_dir: Path | None = None,
) -> None:
    """Save a named column set for a connection + table."""
    data = _load_column_sets_raw(config_dir)
    key = _set_key(connection, table, set_name)
    data[key] = {"columns": columns}
    _write_toml_atomic(_column_sets_path(config_dir), data)


def load_column_set(
    connection: str,
    table: str,
    set_name: str,
    config_dir: Path | None = None,
) -> list[str] | None:
    """Load a named column set. Returns None if not found."""
    data = _load_column_sets_raw(config_dir)
    key = _set_key(connection, table, set_name)
    entry = data.get(key)
    if entry is None:
        return None
    return entry.get("columns", [])


def list_column_sets(
    connection: str | None = None,
    table: str | None = None,
    config_dir: Path | None = None,
) -> dict[str, list[str]]:
    """List column sets, optionally filtered by connection and/or table.

    Returns ``{key: [columns]}`` for matching entries.
    """
    data = _load_column_sets_raw(config_dir)
    result: dict[str, list[str]] = {}
    for key, entry in data.items():
        parts = key.split(".", 2)
        if len(parts) != 3:
            continue
        k_conn, k_table, _k_name = parts
        if connection and k_conn != connection:
            continue
        if table and k_table != table:
            continue
        result[key] = entry.get("columns", [])
    return result


def delete_column_set(
    connection: str,
    table: str,
    set_name: str,
    config_dir: Path | None = None,
) -> bool:
    """Delete a named column set. Returns True if it existed."""
    data = _load_column_sets_raw(config_dir)
    key = _set_key(connection, table, set_name)
    if key not in data:
        return False
    del data[key]
    _write_toml_atomic(_column_sets_path(config_dir), data)
    return True


def resolve_connection(connection: str, db_type: str | None = None) -> dict:
    """Resolve a --connection value to a config dict.

    First tries to look up as a named connection in the config file.
    If not found, treats it as a file path.
    """
    connections = load_connections()

    if connection in connections:
        return connections[connection]

    # Treat as a file path — infer type from extension if not provided
    if db_type is None:
        if connection.endswith(".duckdb") or connection.endswith(".ddb"):
            db_type = "duckdb"
        elif connection.endswith(".parquet"):
            # parquet_path is consumed by factory.py to register the file as a DuckDB view
            return {"type": "duckdb", "path": ":memory:", "parquet_path": connection}
        else:
            db_type = "sqlite"

    # Validate the file exists for local database types
    path = Path(connection)
    if db_type in ("sqlite", "duckdb") and not path.exists():
        named = ", ".join(sorted(connections)) if connections else None
        msg = f"Database file not found: {connection}"
        if named:
            msg += f"\nNamed connections available: {named}"
        msg += "\nTo add a named connection run: qdo config add <name> --type <type> --path <path>"
        raise FileNotFoundError(msg)

    return {"type": db_type, "path": connection}
