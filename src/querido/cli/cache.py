import typer

from querido.cli._errors import friendly_errors
from querido.cli._options import conn_opt, dbtype_opt

app = typer.Typer(help="Manage local metadata cache.")


@app.command()
@friendly_errors
def sync(
    connection: str = conn_opt,
    db_type: str | None = dbtype_opt,
    cache_ttl: int = typer.Option(
        24 * 60 * 60,
        "--cache-ttl",
        help="Cache TTL in seconds (default: 86400 = 24h). Set to 0 to always re-sync.",
    ),
) -> None:
    """Fetch all table/column metadata and cache locally."""
    from querido.cache import MetadataCache
    from querido.config import resolve_connection
    from querido.connectors.factory import create_connector

    config = resolve_connection(connection, db_type)

    with create_connector(config) as connector:
        from rich.console import Console

        console = Console(stderr=True)

        from querido.cli._progress import query_status

        # Skip sync if cache is still fresh (unless ttl=0 forces re-sync)
        if cache_ttl > 0:
            check_cache = MetadataCache()
            try:
                if check_cache.is_fresh(connection, ttl_seconds=cache_ttl):
                    console.print(
                        f"[dim]Cache for '{connection}' is still fresh "
                        f"(TTL {cache_ttl}s). Use --cache-ttl 0 to force re-sync.[/dim]"
                    )
                    return
            finally:
                check_cache.close()

        msg = f"Syncing metadata for [bold]{connection}[/bold]"
        with query_status(console, msg, connector):
            cache = MetadataCache()
            try:
                summary = cache.sync(connection, connector)
            finally:
                cache.close()

        console.print(
            f"[green]Cached[/green] {summary['tables']} tables, "
            f"{summary['columns']} columns in {summary['elapsed']}s"
        )


@app.command()
@friendly_errors
def status(
    connection: str | None = typer.Option(
        None, "--connection", "-c", help="Show status for a specific connection."
    ),
) -> None:
    """Show cache status (age, table count, staleness)."""
    from querido.cache import MetadataCache
    from querido.cli._pipeline import emit

    cache = MetadataCache()
    try:
        entries = cache.status(connection)
    finally:
        cache.close()

    emit(
        "cache status",
        entries,
        dispatch_as="cache_status",
        data={"entries": entries},
        connection=connection,
    )


@app.command()
@friendly_errors
def clear(
    connection: str | None = typer.Option(
        None, "--connection", "-c", help="Clear cache for a specific connection only."
    ),
) -> None:
    """Remove cached metadata."""
    from rich.console import Console

    from querido.cache import MetadataCache

    console = Console(stderr=True)
    cache = MetadataCache()
    try:
        count = cache.clear(connection)
    finally:
        cache.close()

    if connection:
        console.print(f"[green]Cleared[/green] {count} cached table(s) for '{connection}'.")
    else:
        console.print(f"[green]Cleared[/green] {count} cached table(s) from all connections.")
