"""``qdo metadata`` — manage enriched table documentation."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Manage enriched table metadata (init, show, list, edit, refresh).")


@app.command()
@friendly_errors
def init(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None,
        "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
    sample_values: int = typer.Option(
        3,
        "--sample-values",
        help="Number of sample values per column (0 to skip).",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing metadata file."),
) -> None:
    """Generate a metadata YAML file for a table.

    Creates .qdo/metadata/<connection>/<table>.yaml with auto-populated
    fields and placeholder human fields ready to fill in.
    """
    import sys

    from querido.config import resolve_connection
    from querido.connectors.factory import create_connector
    from querido.core.metadata import init_metadata, metadata_path

    config = resolve_connection(connection, db_type)
    with create_connector(config) as connector:
        from rich.console import Console

        from querido.cli._progress import query_status

        console = Console(stderr=True)
        with query_status(console, f"Generating metadata for [bold]{table}[/bold]", connector):
            init_metadata(
                connector,
                connection,
                table,
                sample_values=sample_values,
                force=force,
            )

    path = metadata_path(connection, table)
    print(f"Created: {path}", file=sys.stderr)
    print("Edit the file to fill in descriptions, owner, and notes.", file=sys.stderr)


@app.command()
@friendly_errors
def show(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(..., "--connection", "-c", help="Named connection."),
) -> None:
    """Show stored metadata for a table."""
    from querido.cli._pipeline import dispatch_output
    from querido.core.metadata import show_metadata

    meta = show_metadata(connection, table)
    if meta is None:
        raise typer.BadParameter(
            f"No metadata found for {connection}/{table}. Run 'qdo metadata init' first."
        )

    dispatch_output("metadata", meta)


@app.command("list")
@friendly_errors
def list_cmd(
    connection: str = typer.Option(..., "--connection", "-c", help="Named connection."),
) -> None:
    """List all tables with stored metadata for a connection."""
    from querido.cli._pipeline import dispatch_output
    from querido.core.metadata import list_metadata

    entries = list_metadata(connection)
    dispatch_output("metadata_list", connection, entries)


@app.command()
@friendly_errors
def edit(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(..., "--connection", "-c", help="Named connection."),
) -> None:
    """Open the metadata YAML file in your default editor."""
    import os
    import subprocess

    from querido.core.metadata import metadata_path

    path = metadata_path(connection, table)
    if not path.exists():
        raise typer.BadParameter(f"No metadata found: {path}. Run 'qdo metadata init' first.")

    editor = os.environ.get("EDITOR", "vi")
    subprocess.run([editor, str(path)], check=True)


@app.command()
@friendly_errors
def refresh(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None,
        "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
    sample_values: int = typer.Option(
        3,
        "--sample-values",
        help="Number of sample values per column (0 to skip).",
    ),
) -> None:
    """Re-run inspect/profile to update machine fields.

    Preserves human-written fields (description, owner, notes) while
    updating auto-populated fields (row counts, types, statistics).
    """
    import sys

    from querido.config import resolve_connection
    from querido.connectors.factory import create_connector
    from querido.core.metadata import metadata_path, refresh_metadata

    config = resolve_connection(connection, db_type)
    with create_connector(config) as connector:
        from rich.console import Console

        from querido.cli._progress import query_status

        console = Console(stderr=True)
        with query_status(
            console,
            f"Refreshing metadata for [bold]{table}[/bold]",
            connector,
        ):
            refresh_metadata(
                connector,
                connection,
                table,
                sample_values=sample_values,
            )

    path = metadata_path(connection, table)
    print(f"Refreshed: {path}", file=sys.stderr)


@app.command()
@friendly_errors
def score(
    connection: str = typer.Option(..., "--connection", "-c", help="Named connection."),
) -> None:
    """Per-table metadata completeness ranking (worst first)."""
    from querido.core.metadata_score import score_connection
    from querido.output.envelope import emit_envelope, is_structured_format

    report = score_connection(connection)

    if is_structured_format():
        emit_envelope(
            command="metadata score",
            data=report,
            next_steps=_score_next_steps(report, connection),
            connection=connection,
        )
        return

    _print_score_report(report)


@app.command()
@friendly_errors
def suggest(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None,
        "--db-type",
        help="Database type (sqlite/duckdb). Inferred from path if omitted.",
    ),
    apply_flag: bool = typer.Option(
        False,
        "--apply",
        help="Write the suggested additions to the metadata YAML.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="With --apply: overwrite human-authored fields (confidence 1.0).",
    ),
) -> None:
    """Propose metadata additions for a table as a diff from fresh scans.

    Without ``--apply``, prints what would change.  With ``--apply``, writes
    the additions to ``.qdo/metadata/<connection>/<table>.yaml`` with
    provenance tags identical to ``--write-metadata``.
    """
    from querido.cli._pipeline import table_command
    from querido.core.metadata import init_metadata, metadata_path
    from querido.core.metadata_score import (
        apply_suggestions,
        build_suggestions,
        suggestions_to_dicts,
    )
    from querido.output.envelope import emit_envelope, is_structured_format

    with table_command(table=table, connection=connection, db_type=db_type) as ctx:
        # Ensure a YAML exists so the diff has something to compare against.
        path = metadata_path(connection, ctx.table)
        if not path.exists():
            init_metadata(ctx.connector, connection, ctx.table)

        with ctx.spin(f"Scanning [bold]{ctx.table}[/bold] for suggestions"):
            updates = build_suggestions(ctx.connector, connection, ctx.table, force=force)

        applied: dict | None = None
        if apply_flag and updates:
            applied = apply_suggestions(ctx.connector, connection, ctx.table, updates, force=force)

    payload = {
        "table": ctx.table,
        "suggestions": suggestions_to_dicts(updates),
        "applied": applied,
    }

    if is_structured_format():
        emit_envelope(
            command="metadata suggest",
            data=payload,
            next_steps=[],
            connection=connection,
            table=ctx.table,
        )
        return

    _print_suggestions(payload, path=str(path), applied=bool(applied))


def _score_next_steps(report: dict, connection: str) -> list[dict]:
    """Suggest suggest-runs for the lowest-scoring tables."""
    from querido.core.metadata_score import LOW_SCORE_THRESHOLD
    from querido.output.envelope import cmd

    steps: list[dict] = []
    for row in report.get("tables", [])[:3]:
        score_val = row.get("score")
        table = row.get("table")
        if not table or score_val is None:
            continue
        if score_val >= LOW_SCORE_THRESHOLD:
            break
        steps.append(
            {
                "cmd": cmd(["qdo", "metadata", "suggest", "-c", connection, "-t", table]),
                "why": f"'{table}' scores {score_val:.2f} — propose additions.",
            }
        )
    return steps


def _print_score_report(report: dict) -> None:
    from rich.console import Console
    from rich.table import Table as RichTable

    tables = report.get("tables") or []
    avg = report.get("average_score")
    console = Console()
    if not tables:
        console.print(
            "[yellow]No metadata files found.[/yellow] "
            "Run 'qdo metadata init -c <conn> -t <table>' to create one."
        )
        return

    t = RichTable(title=f"Metadata score — {report.get('connection')}")
    t.add_column("Table", style="cyan")
    t.add_column("Score", justify="right")
    t.add_column("Desc %", justify="right")
    t.add_column("Valid values %", justify="right")
    t.add_column("Freshness", justify="right")

    for row in tables:
        fresh = row.get("freshness_days")
        fresh_str = f"{fresh:.0f}d" if isinstance(fresh, (int, float)) else "—"
        t.add_row(
            str(row.get("table", "")),
            f"{row.get('score', 0):.2f}",
            f"{row.get('column_description_pct', 0):.0f}",
            f"{row.get('valid_values_coverage_pct', 0):.0f}",
            fresh_str,
        )
    console.print(t)
    if avg is not None:
        console.print(f"Average score: [bold]{avg:.2f}[/bold]")


def _print_suggestions(payload: dict, *, path: str, applied: bool) -> None:
    from rich.console import Console
    from rich.table import Table as RichTable

    console = Console()
    suggestions = payload.get("suggestions") or []
    if not suggestions:
        console.print("[green]No novel suggestions.[/green] Metadata is up to date.")
        return

    t = RichTable(
        title=("Applied additions" if applied else "Suggested additions")
        + f" — {payload.get('table', '')}"
    )
    t.add_column("Column", style="cyan")
    t.add_column("Field")
    t.add_column("Value", overflow="fold")
    t.add_column("Source")
    t.add_column("Conf.", justify="right")

    for s in suggestions:
        val = s.get("value")
        val_str = ", ".join(str(v) for v in val) if isinstance(val, list) else str(val)
        t.add_row(
            str(s.get("column") or "(table)"),
            str(s.get("field", "")),
            val_str,
            str(s.get("source", "")),
            f"{s.get('confidence', 0):.2f}",
        )
    console.print(t)
    if applied:
        console.print(f"Wrote {len(suggestions)} field(s) to {path}")
    else:
        console.print(f"\nRe-run with --apply to write these to {path}")
