from __future__ import annotations

from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from querido.connectors.base import Connector

app = typer.Typer(help="Search table and column metadata.")


@app.callback(invoke_without_command=True)
def search(
    pattern: str = typer.Option(
        ..., "--pattern", "-p", help="Search pattern (case-insensitive substring match)."
    ),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
    search_type: str = typer.Option(
        "all",
        "--type",
        help="What to search: table, column, or all.",
    ),
    schema: str | None = typer.Option(None, "--schema", help="Schema filter (Snowflake only)."),
) -> None:
    """Search for tables and columns matching a pattern."""
    from querido.cli._util import friendly_errors

    @friendly_errors
    def _run() -> None:
        from querido.config import resolve_connection
        from querido.connectors.factory import create_connector

        valid_types = {"table", "column", "all"}
        if search_type not in valid_types:
            raise typer.BadParameter(f"--type must be one of: {', '.join(sorted(valid_types))}")

        config = resolve_connection(connection, db_type)

        with create_connector(config) as connector:
            from rich.console import Console

            console = Console(stderr=True)
            with console.status(f"Searching for [bold]{pattern}[/bold]…"):
                results = _search_metadata(connector, pattern, search_type, schema)

            from querido.cli._util import get_output_format

            fmt = get_output_format()
            if fmt == "rich":
                from querido.output.console import print_search

                print_search(pattern, results)
            else:
                from querido.output.formats import format_search

                print(format_search(pattern, results, fmt))

    _run()


def _search_metadata(
    connector: Connector,
    pattern: str,
    search_type: str,
    schema: str | None,
) -> list[dict]:
    """Search tables and columns for pattern matches.

    Returns a list of dicts with keys:
      - table_name: str
      - table_type: str ("table" or "view")
      - match_type: str ("table" or "column")
      - column_name: str | None (None for table-level matches)
      - column_type: str | None
    """
    pat = pattern.lower()
    results: list[dict] = []

    tables = connector.get_tables()

    # Filter by schema for Snowflake if specified
    if schema:
        schema_lower = schema.lower()
        tables = [t for t in tables if t["name"].lower().startswith(schema_lower + ".")]

    search_tables = search_type in ("table", "all")
    search_columns = search_type in ("column", "all")

    for tbl in tables:
        tbl_name = tbl["name"]
        tbl_type = tbl["type"]

        # Match table name
        if search_tables and pat in tbl_name.lower():
            results.append(
                {
                    "table_name": tbl_name,
                    "table_type": tbl_type,
                    "match_type": "table",
                    "column_name": None,
                    "column_type": None,
                }
            )

        # Match column names
        if search_columns:
            try:
                columns = connector.get_columns(tbl_name)
            except Exception:
                import sys

                print(
                    f"Warning: could not read columns for '{tbl_name}', skipping.",
                    file=sys.stderr,
                )
                continue
            for col in columns:
                if pat in col["name"].lower():
                    results.append(
                        {
                            "table_name": tbl_name,
                            "table_type": tbl_type,
                            "match_type": "column",
                            "column_name": col["name"],
                            "column_type": col["type"],
                        }
                    )

    return results
