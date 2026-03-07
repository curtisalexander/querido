from __future__ import annotations

from querido.connectors.base import Connector


def create_connector(config: dict) -> Connector:
    """Create a connector from a connection config dict.

    Config must have a 'type' key ('sqlite', 'duckdb', or 'snowflake').
    """
    db_type = config["type"]

    if db_type == "sqlite":
        from querido.connectors.sqlite import SQLiteConnector

        return SQLiteConnector(config["path"])
    elif db_type == "duckdb":
        try:
            from querido.connectors.duckdb import DuckDBConnector
        except ImportError:
            raise ImportError(
                "DuckDB is not installed. Install it with: pip install 'querido[duckdb]'"
            ) from None
        return DuckDBConnector(config.get("path", ":memory:"))
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
