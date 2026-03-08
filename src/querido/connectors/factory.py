from __future__ import annotations

from querido.connectors.base import Connector


def create_connector(config: dict) -> Connector:
    """Create a connector from a connection config dict.

    Config must have a 'type' key ('sqlite', 'duckdb', or 'snowflake').
    """
    db_type = config.get("type")
    if not db_type:
        raise ValueError("Connection config missing required 'type' key.")

    if db_type == "sqlite":
        from querido.connectors.sqlite import SQLiteConnector

        path = config.get("path")
        if not path:
            raise ValueError("SQLite connection config missing required 'path' key.")
        return SQLiteConnector(path)
    elif db_type == "duckdb":
        try:
            from querido.connectors.duckdb import DuckDBConnector
        except ImportError:
            raise ImportError(
                "DuckDB is not installed. Install it with: pip install 'querido[duckdb]'"
            ) from None
        connector = DuckDBConnector(config.get("path", ":memory:"))
        if "parquet_path" in config:
            connector.register_parquet(config["parquet_path"])
        return connector
    elif db_type == "snowflake":
        try:
            from querido.connectors.snowflake import SnowflakeConnector
        except ImportError:
            raise ImportError(
                "Snowflake connector is not installed. "
                "Install it with: pip install 'querido[snowflake]'"
            ) from None
        return SnowflakeConnector(**config)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
