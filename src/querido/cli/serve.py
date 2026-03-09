"""``qdo serve`` — local web UI."""

import typer

app = typer.Typer(help="Serve interactive web UI.")


@app.callback(invoke_without_command=True)
def serve(
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
    port: int = typer.Option(8888, "--port", "-p", help="Port to serve on."),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to."),
) -> None:
    """Start a local web server for interactive data exploration."""
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        from rich.console import Console

        Console(stderr=True).print(
            "[red]fastapi/uvicorn[/red] is required for the web UI.\n"
            "Install it with: [bold]pip install 'querido\\[web]'[/bold]"
        )
        raise typer.Exit(1) from None

    from querido.cli._util import friendly_errors

    @friendly_errors
    def _run() -> None:
        import uvicorn

        from querido.config import resolve_connection
        from querido.connectors.factory import create_connector
        from querido.web import create_app

        config = resolve_connection(connection, db_type)
        # Allow cross-thread access for async web server
        if config.get("type") == "sqlite":
            config["check_same_thread"] = False
        connector = create_connector(config)
        application = create_app(connector, connection)

        from rich.console import Console

        console = Console(stderr=True)
        console.print(f"\n  [bold]qdo serve[/bold] — {connection}")
        console.print(f"  [dim]http://{host}:{port}[/dim]\n")

        uvicorn.run(application, host=host, port=port, log_level="warning")

    _run()
