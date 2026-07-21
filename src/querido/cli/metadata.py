"""``qdo metadata`` — manage enriched table documentation."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors
from querido.cli._options import conn_opt, dbtype_opt, table_opt

app = typer.Typer(
    help="Manage enriched table metadata (init, show, list, search, edit, refresh, undo)."
)


@app.command()
@friendly_errors
def init(
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
    sample_values: int = typer.Option(
        3,
        "--sample-values",
        help=(
            "Number of sample values per non-numeric column (0 to skip). "
            "Numeric columns always use min/max instead."
        ),
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing metadata file."),
) -> None:
    """Generate a metadata YAML file for a table.

    Creates .qdo/metadata/<connection>/<table>.yaml with auto-populated
    fields and placeholder human fields ready to fill in.
    """
    from querido.cli._pipeline import emit_json, table_command
    from querido.core.metadata import init_metadata, metadata_path

    with (
        table_command(table=table, connection=connection, db_type=db_type) as ctx,
        ctx.spin(f"Generating metadata for [bold]{ctx.table}[/bold]"),
    ):
        init_metadata(
            ctx.connector,
            connection,
            ctx.table,
            sample_values=sample_values,
            force=force,
        )

    path = metadata_path(connection, ctx.table)

    from querido._shell import cmd

    if emit_json(
        "metadata init",
        {"path": str(path), "table": ctx.table, "created": True},
        next_steps=[
            {
                "cmd": cmd(
                    [
                        "qdo",
                        "metadata",
                        "suggest",
                        "-c",
                        connection,
                        "-t",
                        ctx.table,
                        "--apply",
                    ]
                ),
                "why": "Auto-fill deterministic fields (valid_values, flags) from scans.",
            },
            {
                "cmd": cmd(["qdo", "metadata", "edit", "-c", connection, "-t", ctx.table]),
                "why": "Fill in descriptions, owner, and notes.",
            },
        ],
        connection=connection,
        table=ctx.table,
    ):
        return

    import sys

    print(f"Created: {path}", file=sys.stderr)
    print("Edit the file to fill in descriptions, owner, and notes.", file=sys.stderr)


@app.command()
@friendly_errors
def show(
    table: str = table_opt,
    connection: str = conn_opt,
) -> None:
    """Show stored metadata for a table."""
    from querido.cli._pipeline import emit
    from querido.core.metadata import show_metadata

    meta = show_metadata(connection, table)
    if meta is None:
        raise typer.BadParameter(
            f"No metadata found for {connection}/{table}. Run 'qdo metadata init' first."
        )

    from querido.core.next_steps import for_metadata_show

    emit(
        "metadata show",
        meta,
        dispatch_as="metadata",
        next_steps=lambda: for_metadata_show(meta, connection=connection, table=table),
        connection=connection,
        table=table,
    )


@app.command("list")
@friendly_errors
def list_cmd(
    connection: str = conn_opt,
) -> None:
    """List all tables with stored metadata for a connection."""
    from querido.cli._pipeline import dispatch_output
    from querido.core.metadata import list_metadata

    entries = list_metadata(connection)
    dispatch_output("metadata_list", connection, entries)


@app.command("search")
@friendly_errors
def search_cmd(
    query: str = typer.Argument(..., help="Meaning-based metadata search query."),
    connection: str = conn_opt,
    limit: int = typer.Option(5, "--limit", min=1, max=20, help="Maximum results to return."),
) -> None:
    """Search stored metadata by meaning across table and column descriptions."""
    from querido.cli._pipeline import emit
    from querido.core.metadata import search_metadata
    from querido.core.next_steps import for_metadata_search

    result = search_metadata(connection, query, limit=limit)

    emit(
        "metadata search",
        result,
        dispatch_as="metadata_search",
        next_steps=lambda: for_metadata_search(result, connection=connection),
        connection=connection,
    )


@app.command()
@friendly_errors
def edit(
    table: str = table_opt,
    connection: str = conn_opt,
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
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
    sample_values: int = typer.Option(
        3,
        "--sample-values",
        help=(
            "Number of sample values per non-numeric column (0 to skip). "
            "Numeric columns always use min/max instead."
        ),
    ),
) -> None:
    """Re-run inspect/profile to update machine fields.

    Preserves human-written fields (description, owner, notes) while
    updating auto-populated fields (row counts, types, statistics).
    """
    from querido.cli._pipeline import emit_json, table_command
    from querido.core.metadata import metadata_path, refresh_metadata

    with (
        table_command(table=table, connection=connection, db_type=db_type) as ctx,
        ctx.spin(f"Refreshing metadata for [bold]{ctx.table}[/bold]"),
    ):
        merged = refresh_metadata(
            ctx.connector,
            connection,
            ctx.table,
            sample_values=sample_values,
        )

    path = metadata_path(connection, ctx.table)

    from querido._shell import cmd

    if emit_json(
        "metadata refresh",
        {
            "path": str(path),
            "table": ctx.table,
            "row_count": merged.get("row_count"),
            "column_count": len(merged.get("columns") or []),
        },
        next_steps=[
            {
                "cmd": cmd(["qdo", "metadata", "show", "-c", connection, "-t", ctx.table]),
                "why": "Inspect the refreshed metadata.",
            }
        ],
        connection=connection,
        table=ctx.table,
    ):
        return

    import sys

    print(f"Refreshed: {path}", file=sys.stderr)


@app.command()
@friendly_errors
def undo(
    table: str = table_opt,
    connection: str = conn_opt,
    steps: int = typer.Option(1, "--steps", min=1, help="Undo the last N qdo-managed writes."),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would be undone without restoring the file.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Restore the recorded snapshot even if the current file has drifted.",
    ),
) -> None:
    """Undo the last qdo-managed metadata write(s) for one table."""
    from querido.cli._pipeline import emit_json
    from querido.core.metadata import undo_metadata

    try:
        summary = undo_metadata(
            connection,
            table,
            steps=steps,
            dry_run=dry_run,
            force=force,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from None

    from querido._shell import cmd

    next_steps = [
        {
            "cmd": cmd(["qdo", "metadata", "show", "-c", connection, "-t", table]),
            "why": "Inspect the restored metadata.",
        }
    ]
    if emit_json(
        "metadata undo",
        summary,
        next_steps=next_steps,
        connection=connection,
        table=table,
    ):
        return

    action = "Would restore" if dry_run else "Restored"
    target = (
        "delete the metadata file" if summary.get("restored") == "delete" else "the prior snapshot"
    )
    print(f"{action} {target} for {summary.get('path')}")


@app.command()
@friendly_errors
def score(
    connection: str = conn_opt,
) -> None:
    """Per-table metadata completeness ranking (worst first)."""
    from querido.cli._pipeline import emit_json
    from querido.core.metadata_score import score_connection

    report = score_connection(connection)

    if emit_json(
        "metadata score",
        report,
        next_steps=lambda: _score_next_steps(report, connection),
        connection=connection,
    ):
        return

    _print_score_report(report)


@app.command()
@friendly_errors
def suggest(
    table: str = table_opt,
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
    apply_flag: bool = typer.Option(
        False,
        "--apply",
        help=(
            "Write the suggested additions to .qdo/metadata/<conn>/<table>.yaml. "
            "Human-authored fields (confidence 1.0) are preserved unless --force."
        ),
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
    from querido.cli._pipeline import emit_json, table_command
    from querido.core.metadata import init_metadata, metadata_path
    from querido.core.metadata_score import (
        apply_suggestions,
        build_suggestions,
        suggestions_to_dicts,
    )

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

    if emit_json(
        "metadata suggest",
        payload,
        connection=connection,
        table=ctx.table,
    ):
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
