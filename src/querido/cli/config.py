from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="Manage connections.")


@app.command()
def add(
    name: str = typer.Option(..., "--name", "-n", help="Connection name."),
    db_type: str = typer.Option(
        ..., "--type", "-t", help="Database type (sqlite/duckdb/snowflake)."
    ),
    path: str | None = typer.Option(
        None, "--path", "-p", help="Database file path (sqlite/duckdb)."
    ),
    account: str | None = typer.Option(None, "--account", help="Snowflake account."),
    user: str | None = typer.Option(None, "--user", help="Snowflake user."),
    warehouse: str | None = typer.Option(None, "--warehouse", help="Snowflake warehouse."),
    database: str | None = typer.Option(None, "--database", help="Snowflake database."),
    schema: str | None = typer.Option(None, "--schema", help="Snowflake schema."),
    role: str | None = typer.Option(None, "--role", help="Snowflake role."),
    auth: str | None = typer.Option(None, "--auth", help="Snowflake authenticator."),
    private_key_path: str | None = typer.Option(
        None,
        "--private-key-path",
        help="Path to private key file (.p8) for Snowflake key-pair auth.",
    ),
) -> None:
    """Add a named connection to connections.toml."""
    from querido.config import get_config_dir, load_connections

    if db_type not in ("sqlite", "duckdb", "snowflake"):
        raise typer.BadParameter(
            f"Unsupported db type: {db_type!r}. Use sqlite, duckdb, or snowflake."
        )

    if db_type in ("sqlite", "duckdb") and not path:
        raise typer.BadParameter(f"--path is required for {db_type} connections.")

    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "connections.toml"

    # Load existing connections
    existing = load_connections(config_dir)
    if name in existing:
        raise typer.BadParameter(
            f"Connection '{name}' already exists. Remove it first or choose another name."
        )

    # Build connection entry
    entry: dict[str, str] = {"type": db_type}
    if path:
        entry["path"] = path
    entry.update(
        {
            key: val
            for key, val in [
                ("account", account),
                ("user", user),
                ("warehouse", warehouse),
                ("database", database),
                ("schema", schema),
                ("role", role),
                ("auth", auth),
                ("private_key_path", private_key_path),
            ]
            if val
        }
    )

    # Write back as TOML
    existing[name] = entry
    _write_connections(config_file, existing)

    from rich.console import Console

    Console(stderr=True).print(
        f"[green]Added connection '[bold]{name}[/bold]' to {config_file}[/green]"
    )


@app.command("list")
def list_connections() -> None:
    """List all configured connections."""
    from rich.console import Console
    from rich.table import Table

    from querido.config import get_config_dir, load_connections

    console = Console()
    connections = load_connections()

    if not connections:
        config_dir = get_config_dir()
        console.print(f"[dim]No connections configured. Config dir: {config_dir}[/dim]")
        return

    # Check if any connection uses Snowflake to decide column layout
    has_snowflake = any(c.get("type") == "snowflake" for c in connections.values())

    grid = Table(title="Configured Connections", show_lines=True)
    grid.add_column("Name", style="cyan bold")
    grid.add_column("Type", style="green")
    if has_snowflake:
        grid.add_column("Account", style="dim")
        grid.add_column("Database", style="yellow")
        grid.add_column("Schema", style="dim")
        grid.add_column("Role", style="magenta")
        grid.add_column("Warehouse", style="blue")
    else:
        grid.add_column("Details", style="dim")

    for conn_name, conn_config in connections.items():
        db_type = conn_config.get("type", "?")
        if has_snowflake:
            if db_type in ("sqlite", "duckdb"):
                grid.add_row(
                    conn_name,
                    db_type,
                    "",
                    conn_config.get("path", ""),
                    "",
                    "",
                    "",
                )
            else:
                grid.add_row(
                    conn_name,
                    db_type,
                    conn_config.get("account", ""),
                    conn_config.get("database", ""),
                    conn_config.get("schema", ""),
                    conn_config.get("role", ""),
                    conn_config.get("warehouse", ""),
                )
        else:
            details = conn_config.get("path", "")
            grid.add_row(conn_name, db_type, details)

    console.print(grid)


@app.command()
def clone(
    source: str = typer.Option(..., "--source", "-s", help="Name of the connection to clone."),
    name: str = typer.Option(..., "--name", "-n", help="Name for the new connection."),
    database: str | None = typer.Option(None, "--database", help="Override database."),
    schema: str | None = typer.Option(None, "--schema", help="Override schema."),
    role: str | None = typer.Option(None, "--role", help="Override role."),
    warehouse: str | None = typer.Option(None, "--warehouse", help="Override warehouse."),
    account: str | None = typer.Option(None, "--account", help="Override account."),
    user: str | None = typer.Option(None, "--user", help="Override user."),
    auth: str | None = typer.Option(None, "--auth", help="Override authenticator."),
) -> None:
    """Clone an existing connection with optional overrides.

    Useful for creating per-database Snowflake connections that share the same
    account and credentials but differ in database, role, or warehouse.
    """
    from querido.config import get_config_dir, load_connections

    config_dir = get_config_dir()
    config_file = config_dir / "connections.toml"
    existing = load_connections(config_dir)

    if source not in existing:
        available = ", ".join(sorted(existing)) if existing else "(none)"
        raise typer.BadParameter(f"Source connection '{source}' not found. Available: {available}")

    if name in existing:
        raise typer.BadParameter(
            f"Connection '{name}' already exists. Remove it first or choose another name."
        )

    # Clone and apply overrides
    entry = dict(existing[source])
    entry.update(
        {
            key: val
            for key, val in [
                ("database", database),
                ("schema", schema),
                ("role", role),
                ("warehouse", warehouse),
                ("account", account),
                ("user", user),
                ("auth", auth),
            ]
            if val is not None
        }
    )

    existing[name] = entry
    _write_connections(config_file, existing)

    from rich.console import Console

    Console(stderr=True).print(
        f"[green]Cloned '[bold]{source}[/bold]' → '[bold]{name}[/bold]' in {config_file}[/green]"
    )


@app.command()
def test(
    connection: str = typer.Argument(..., help="Connection name or file path to test."),
    db_type: str | None = typer.Option(
        None, "--db-type", help="Database type (sqlite/duckdb). Inferred from path if omitted."
    ),
) -> None:
    """Test a connection by running SELECT 1."""
    import time

    from rich.console import Console

    from querido.config import resolve_connection
    from querido.connectors.factory import create_connector

    console = Console(stderr=True)
    config = resolve_connection(connection, db_type)
    conn_type = config.get("type", "?")

    try:
        t0 = time.monotonic()
        with create_connector(config) as connector:
            connector.execute("select 1")
        elapsed = time.monotonic() - t0
    except Exception as exc:
        console.print(f"[red bold]FAIL[/red bold] ({conn_type}) {exc}")
        raise typer.Exit(1) from None

    detail = config.get("path") or config.get("account", "")
    console.print(f"[green bold]OK[/green bold] ({conn_type}) {detail} [{elapsed:.3f}s]")

    # Show extra detail for Snowflake connections
    if conn_type == "snowflake":
        for key in ("database", "schema", "role", "warehouse"):
            val = config.get(key, "")
            if val:
                console.print(f"  {key}: {val}")


def _write_connections(config_file: Path | str, connections: dict) -> None:
    """Write connections dict back to TOML format using tomli-w.

    Uses a temp file + atomic rename so a crash mid-write can't corrupt the config.
    """
    import os
    import tempfile

    import tomli_w

    config_file = Path(config_file)
    data = tomli_w.dumps({"connections": connections}).encode()
    fd, tmp = tempfile.mkstemp(dir=config_file.parent, suffix=".tmp")
    closed = False
    try:
        os.write(fd, data)
        os.close(fd)
        closed = True
        Path(tmp).replace(config_file)
        config_file.chmod(0o600)
    except BaseException:
        if not closed:
            os.close(fd)
        Path(tmp).unlink(missing_ok=True)
        raise
