"""``qdo metadata`` — manage enriched table documentation."""

from __future__ import annotations

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Manage enriched table metadata (init, show, list, edit, refresh).")


# -- init ---------------------------------------------------------------------

init_app = typer.Typer(help="Initialize metadata for a table.")
app.add_typer(init_app, name="init")


@init_app.callback(invoke_without_command=True)
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


# -- show ---------------------------------------------------------------------

show_app = typer.Typer(help="Show stored metadata for a table.")
app.add_typer(show_app, name="show")


@show_app.callback(invoke_without_command=True)
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


# -- list ---------------------------------------------------------------------

list_app = typer.Typer(help="List stored metadata files.")
app.add_typer(list_app, name="list")


@list_app.callback(invoke_without_command=True)
@friendly_errors
def list_cmd(
    connection: str = typer.Option(..., "--connection", "-c", help="Named connection."),
) -> None:
    """List all tables with stored metadata for a connection."""
    from querido.cli._pipeline import dispatch_output
    from querido.core.metadata import list_metadata

    entries = list_metadata(connection)
    dispatch_output("metadata_list", connection, entries)


# -- edit ---------------------------------------------------------------------

edit_app = typer.Typer(help="Open metadata file in $EDITOR.")
app.add_typer(edit_app, name="edit")


@edit_app.callback(invoke_without_command=True)
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


# -- refresh ------------------------------------------------------------------

refresh_app = typer.Typer(help="Refresh machine fields in metadata.")
app.add_typer(refresh_app, name="refresh")


@refresh_app.callback(invoke_without_command=True)
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
