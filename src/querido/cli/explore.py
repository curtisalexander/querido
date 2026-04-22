import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Interactive TUI with selected-column context and wide-table triage.")


@app.callback(invoke_without_command=True)
@friendly_errors
def explore(
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    rows: int = typer.Option(1000, "--rows", "-r", min=1, help="Maximum rows to load initially."),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
) -> None:
    """Launch the interactive TUI for table exploration.

    The grid uses semantic cues so primary keys, sorted columns, null-heavy
    columns, and explicit NULL cells stand out quickly. Press ``m`` to open
    the selected-column sidebar, ``p`` to profile, and ``d`` for a column
    distribution. On wide tables, profiling starts with quick triage so you
    can focus full stats on the most useful columns first.
    """
    from querido.cli._validation import resolve_table
    from querido.config import resolve_connection
    from querido.connectors.base import validate_table_name
    from querido.connectors.factory import create_connector

    validate_table_name(table)
    config = resolve_connection(connection, db_type)

    try:
        from textual.app import App as _App  # noqa: F401
    except ImportError:
        from rich.console import Console

        console = Console(stderr=True)
        console.print(
            "[red]textual[/red] is required for the explore TUI.\n"
            "Install it with: [bold]uv pip install 'querido\\[tui]'[/bold]"
        )
        raise typer.Exit(1) from None

    connector = create_connector(config)
    try:
        resolved = resolve_table(connector, table)

        from querido.tui.app import ExploreApp

        tui_app = ExploreApp(
            connector=connector,
            table=resolved,
            max_rows=rows,
            connection_name=connection,
        )
        tui_app.run()
    finally:
        connector.close()
