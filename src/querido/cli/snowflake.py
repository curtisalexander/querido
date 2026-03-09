"""qdo snowflake — Snowflake-specific commands."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from querido.connectors.base import Connector

app = typer.Typer(help="Snowflake-specific commands.")

_conn_opt = typer.Option(..., "--connection", "-c", help="Named connection or file path.")
_dbtype_opt = typer.Option(None, "--db-type", help="Database type. Inferred from path if omitted.")


def _require_snowflake(dialect: str, command: str) -> None:
    if dialect != "snowflake":
        raise typer.BadParameter(
            f"'snowflake {command}' requires a Snowflake connection (got {dialect})."
        )


# ---------------------------------------------------------------------------
# qdo snowflake semantic
# ---------------------------------------------------------------------------


@app.command()
def semantic(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = _conn_opt,
    db_type: str | None = _dbtype_opt,
    output_file: str | None = typer.Option(
        None, "--output", "-o", help="Write YAML to file instead of stdout."
    ),
) -> None:
    """Generate a Cortex Analyst semantic model YAML from table metadata."""
    from querido.cli._util import friendly_errors

    @friendly_errors
    def _run() -> None:
        from querido.cli._util import check_table_exists
        from querido.config import resolve_connection
        from querido.connectors.base import validate_table_name
        from querido.connectors.factory import create_connector

        validate_table_name(table)
        config = resolve_connection(connection, db_type)

        with create_connector(config) as connector:
            from rich.console import Console

            console = Console(stderr=True)

            _require_snowflake(connector.dialect, "semantic")

            from querido.cli._progress import query_status

            with query_status(console, f"Reading metadata for [bold]{table}[/bold]", connector):
                check_table_exists(connector, table)
                columns = connector.get_columns(table)
                table_comment = connector.get_table_comment(table)

        yaml_str = _build_semantic_yaml(table, columns, table_comment)

        if output_file:
            from pathlib import Path

            Path(output_file).write_text(yaml_str)
            import sys

            print(f"Wrote semantic model to {output_file}", file=sys.stderr)
        else:
            print(yaml_str)

    _run()


def _build_semantic_yaml(
    table: str,
    columns: list[dict],
    table_comment: str | None,
) -> str:
    """Build a Cortex Analyst semantic model YAML string."""
    buf = io.StringIO()
    indent = "  "

    from querido.output.formats import yaml_escape

    buf.write(f"name: {table.lower()}_semantic_model\n")
    desc = table_comment or f"Semantic model for {table}"
    buf.write(f"description: {yaml_escape(desc)}\n")
    buf.write("\n")
    buf.write("tables:\n")
    buf.write(f"{indent}- name: {table}\n")
    buf.write(f"{indent}  base_table: {table}\n")
    buf.write(f"{indent}  description: {yaml_escape(desc)}\n")

    # Group columns
    from querido.core.profile import classify_column_kind

    dimensions = []
    time_dimensions = []
    measures = []
    for col in columns:
        kind = classify_column_kind(col)
        if kind == "time_dimension":
            time_dimensions.append(col)
        elif kind == "measure":
            measures.append(col)
        else:
            dimensions.append(col)

    if dimensions:
        buf.write(f"\n{indent}  dimensions:\n")
        for col in dimensions:
            _write_column_entry(buf, col, indent * 2)

    if time_dimensions:
        buf.write(f"\n{indent}  time_dimensions:\n")
        for col in time_dimensions:
            _write_column_entry(buf, col, indent * 2)

    if measures:
        buf.write(f"\n{indent}  measures:\n")
        for col in measures:
            _write_column_entry(buf, col, indent * 2, is_measure=True)

    return buf.getvalue()


def _write_column_entry(
    buf: io.StringIO,
    col: dict,
    prefix: str,
    *,
    is_measure: bool = False,
) -> None:
    """Write a single column entry in the semantic model YAML."""

    from querido.output.formats import yaml_escape

    name = col["name"]
    col_type = col["type"]
    comment = col.get("comment") or "<description>"

    buf.write(f"{prefix}- name: {name}\n")
    buf.write(f"{prefix}  expr: {name}\n")
    buf.write(f"{prefix}  data_type: {col_type}\n")
    buf.write(f"{prefix}  description: {yaml_escape(comment)}\n")
    buf.write(f"{prefix}  synonyms:\n")
    buf.write(f"{prefix}    - <synonym>\n")

    if is_measure:
        buf.write(f"{prefix}  default_aggregation: sum\n")


# ---------------------------------------------------------------------------
# qdo snowflake lineage
# ---------------------------------------------------------------------------


@app.command()
def lineage(
    object_name: str = typer.Option(..., "--object", help="Fully qualified object name."),
    connection: str = _conn_opt,
    db_type: str | None = _dbtype_opt,
    direction: str = typer.Option(
        "downstream",
        "--direction",
        "-d",
        help="Lineage direction: upstream or downstream.",
    ),
    domain: str = typer.Option("table", "--domain", help="Object domain: table or column."),
    depth: int = typer.Option(5, "--depth", help="Maximum traversal depth."),
) -> None:
    """Trace upstream/downstream lineage via Snowflake GET_LINEAGE."""
    from querido.cli._util import friendly_errors

    @friendly_errors
    def _run() -> None:
        from querido.cli._util import get_output_format
        from querido.config import resolve_connection
        from querido.connectors.factory import create_connector

        valid_directions = {"upstream", "downstream"}
        if direction not in valid_directions:
            raise typer.BadParameter(
                f"--direction must be one of: {', '.join(sorted(valid_directions))}"
            )

        valid_domains = {"table", "column"}
        if domain not in valid_domains:
            raise typer.BadParameter(
                f"--domain must be one of: {', '.join(sorted(valid_domains))}"
            )

        config = resolve_connection(connection, db_type)

        with create_connector(config) as connector:
            from rich.console import Console

            console = Console(stderr=True)

            _require_snowflake(connector.dialect, "lineage")

            from querido.cli._progress import query_status

            msg = f"Querying lineage for [bold]{object_name}[/bold] ({direction})"
            with query_status(console, msg, connector):
                rows = _query_lineage(connector, object_name, direction, domain, depth)

        result = {
            "object": object_name,
            "direction": direction,
            "domain": domain,
            "depth": depth,
            "entries": rows,
        }

        fmt = get_output_format()
        if fmt == "rich":
            from querido.output.console import print_snowflake_lineage

            print_snowflake_lineage(result)
        elif fmt == "html":
            from querido.cli._util import emit_html
            from querido.output.html import format_snowflake_lineage_html

            emit_html(format_snowflake_lineage_html(result))
        else:
            from querido.output.formats import format_snowflake_lineage

            print(format_snowflake_lineage(result, fmt))

    _run()


def _query_lineage(
    connector: Connector,
    object_name: str,
    direction: str,
    domain: str,
    depth: int,
) -> list[dict]:
    """Execute GET_LINEAGE and return results."""
    from querido.connectors.base import validate_object_name

    validate_object_name(object_name)

    # Validate allowlists here (not just in the caller) since these values
    # are interpolated directly into SQL.
    if direction not in ("upstream", "downstream"):
        raise ValueError(f"Invalid direction: {direction!r}")
    if domain not in ("table", "column"):
        raise ValueError(f"Invalid domain: {domain!r}")

    sql = (
        f"SELECT * FROM TABLE("
        f"SNOWFLAKE.CORE.GET_LINEAGE('{object_name}', '{domain}', '{direction}', {depth})"
        f")"
    )

    from querido.cli._util import maybe_show_sql, set_last_sql

    maybe_show_sql(sql)
    set_last_sql(sql)

    return connector.execute(sql)
