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

    return {"type": db_type, "path": connection}
