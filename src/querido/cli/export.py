"""``qdo export`` — export table or query results to a file."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Export data to a file (csv, tsv, json, jsonl).")


@app.callback(invoke_without_command=True)
@friendly_errors
def export(
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    table: str | None = typer.Option(
        None, "--table", "-t", help="Table to export."
    ),
    sql: str | None = typer.Option(
        None, "--sql", "-s", help="SQL query to export."
    ),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Output file path."
    ),
    export_format: str = typer.Option(
        "csv", "--export-format", "-e",
        help="Export format: csv, tsv, json, jsonl.",
    ),
    db_type: str | None = typer.Option(
        None, "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
    filter_expr: str | None = typer.Option(
        None, "--filter", "-w", help="SQL WHERE clause expression."
    ),
    limit: int | None = typer.Option(
        None, "--limit", "-l", min=1, help="Maximum rows to export."
    ),
    columns: str | None = typer.Option(
        None, "--columns",
        help="Comma-separated column names to export.",
    ),
    clipboard: bool = typer.Option(
        False, "--clipboard",
        help="Copy TSV to clipboard (for pasting into Excel).",
    ),
) -> None:
    """Export table or query results to a file or clipboard.

    Examples:

        qdo export -c ./my.db -t users -o users.csv
        qdo export -c ./my.db -t users -o data.tsv -e tsv
        qdo export -c ./my.db --sql "select * from users" -o out.json -e json
        qdo export -c ./my.db -t users --clipboard
    """
    import sys

    from querido.config import resolve_connection
    from querido.connectors.factory import create_connector

    if not table and not sql:
        raise typer.BadParameter("Must provide --table or --sql.")

    valid_formats = {"csv", "tsv", "json", "jsonl"}
    if export_format not in valid_formats:
        raise typer.BadParameter(
            f"--export-format must be one of: {', '.join(sorted(valid_formats))}"
        )

    # Clipboard mode forces TSV and no output file
    if clipboard:
        export_format = "tsv"
        output = None

    col_list = None
    if columns:
        col_list = [c.strip() for c in columns.split(",") if c.strip()]

    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        from rich.console import Console

        from querido.cli._progress import query_status
        from querido.core.export import export_data

        console = Console(stderr=True)
        with query_status(console, "Exporting data", connector):
            result = export_data(
                connector,
                table=table,
                sql=sql,
                output_path=output,
                fmt=export_format,
                limit=limit,
                filter_expr=filter_expr,
                columns=col_list,
            )

        if clipboard:
            from querido.core.export import copy_to_clipboard

            content = result.get("content", "")
            copy_to_clipboard(content)
            console.print(
                f"[green]Copied {result.get('rows', 0):,} rows to clipboard (TSV)[/green]",
            )
        elif output:
            console.print(
                f"[green]Exported {result.get('rows', 0):,} rows to {output}"
                f" ({result.get('size_bytes', 0):,} bytes)[/green]",
            )
        else:
            # No output file and no clipboard — print to stdout
            content = result.get("content", "")
            if content:
                print(content, end="", file=sys.stdout)
