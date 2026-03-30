import typer

app = typer.Typer(help="Interactive data exploration (TUI).")


@app.callback(invoke_without_command=True)
def explore(
    table: str = typer.Option(..., "--table", "-t", help="Table name to explore."),
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    rows: int = typer.Option(1000, "--rows", "-r", min=1, help="Maximum rows to load initially."),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
) -> None:
    """Launch an interactive TUI for exploring table data."""
    from querido.cli._errors import friendly_errors
    from querido.cli._validation import check_table_exists

    @friendly_errors
    def _run() -> None:
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
            check_table_exists(connector, table)

            from querido.tui.app import ExploreApp

            tui_app = ExploreApp(connector=connector, table=table, max_rows=rows)
            tui_app.run()
        finally:
            connector.close()

    _run()
