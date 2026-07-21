"""qdo snowflake — Snowflake-specific commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

import typer

from querido.cli._errors import friendly_errors
from querido.cli._options import conn_opt, dbtype_opt, table_opt
from querido.cli._validation import require_snowflake

if TYPE_CHECKING:
    from querido.connectors.base import Connector

app = typer.Typer(help="Snowflake-specific commands.")


# ---------------------------------------------------------------------------
# qdo snowflake semantic
# ---------------------------------------------------------------------------


@app.command()
@friendly_errors
def semantic(
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
    output_file: str | None = typer.Option(
        None, "--output", "-o", help="Write DDL to file instead of stdout."
    ),
    sample_values: int = typer.Option(
        25,
        "--sample-values",
        min=0,
        max=100,
        help="Distinct sample values per column (0 to skip). Snowflake recommends 25+.",
    ),
) -> None:
    """Generate create semantic view DDL from table metadata."""
    from querido.cli._pipeline import table_command

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        require_snowflake(ctx.connector.dialect, "semantic")

        with ctx.spin(f"Reading metadata for [bold]{ctx.table}[/bold]"):
            columns = ctx.connector.get_columns(ctx.table)
            table_comment = ctx.connector.get_table_comment(ctx.table)

        if sample_values > 0:
            with ctx.spin(f"Fetching [bold]{sample_values}[/bold] sample values per column"):
                from querido.core.semantic import get_sample_values

                sv = get_sample_values(ctx.connector, ctx.table, columns, limit=sample_values)
        else:
            sv = None

    from querido.core.semantic import build_semantic_view_ddl

    ddl_str = build_semantic_view_ddl(ctx.table, columns, table_comment, sample_values_per_col=sv)

    from querido.cli._pipeline import emit_json

    if output_file:
        from pathlib import Path

        Path(output_file).write_text(ddl_str)

        if emit_json(
            "snowflake semantic",
            {
                "path": output_file,
                "table": ctx.table,
                "column_count": len(columns),
            },
            connection=connection,
            table=ctx.table,
        ):
            return

        import sys

        print(f"Wrote semantic view DDL to {output_file}", file=sys.stderr)
        return

    if emit_json(
        "snowflake semantic",
        {
            "ddl": ddl_str,
            "table": ctx.table,
            "column_count": len(columns),
            "sample_values_per_column": sample_values if sample_values > 0 else 0,
        },
        next_steps=[
            {
                "cmd": f"qdo snowflake semantic -c {connection} -t {ctx.table} -o {ctx.table}.sql",
                "why": "Write the DDL to a file, review it, then run it in "
                "Snowflake to create the semantic view.",
            },
        ],
        connection=connection,
        table=ctx.table,
    ):
        return

    print(ddl_str)


# ---------------------------------------------------------------------------
# qdo snowflake lineage
# ---------------------------------------------------------------------------


@app.command()
@friendly_errors
def lineage(
    object_name: str = typer.Option(..., "--object", help="Fully qualified object name."),
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
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
    from querido.cli._errors import CodedBadParameter
    from querido.cli._pipeline import emit
    from querido.config import resolve_connection
    from querido.connectors.factory import create_connector

    valid_directions = {"upstream", "downstream"}
    if direction not in valid_directions:
        raise CodedBadParameter(
            f"--direction must be one of: {', '.join(sorted(valid_directions))}",
            code="LINEAGE_DIRECTION_INVALID",
        )

    valid_domains = {"table", "column"}
    if domain not in valid_domains:
        raise CodedBadParameter(
            f"--domain must be one of: {', '.join(sorted(valid_domains))}",
            code="LINEAGE_DOMAIN_INVALID",
        )

    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        from rich.console import Console

        console = Console(stderr=True)

        require_snowflake(connector.dialect, "lineage")

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

    def _lineage_next_steps() -> list[dict]:
        other_direction = "upstream" if direction == "downstream" else "downstream"
        return [
            {
                "cmd": f"qdo snowflake lineage -c {connection} --object {object_name} "
                f"--direction {other_direction}",
                "why": f"Trace the {other_direction} side of lineage for this object.",
            },
        ]

    emit(
        "snowflake lineage",
        result,
        dispatch_as="snowflake_lineage",
        next_steps=_lineage_next_steps,
        connection=connection,
        extra_meta={"object": object_name, "direction": direction, "domain": domain},
    )


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
        f"select * from table("
        f"snowflake.core.get_lineage('{object_name}', '{domain}', '{direction}', {depth})"
        f")"
    )

    from querido.cli._context import maybe_show_sql
    from querido.cli._errors import set_last_sql

    maybe_show_sql(sql)
    set_last_sql(sql)

    return connector.execute(sql)
