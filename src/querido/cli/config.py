from __future__ import annotations

from pathlib import Path

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Manage connections.")


def _missing_backend_extra(db_type: str) -> str | None:
    """Return the extras name (``duckdb`` / ``snowflake``) if the backend
    driver isn't importable. ``None`` means the backend is ready to use.

    SQLite is stdlib, so it never reports missing.
    """
    import importlib.util

    module = {"duckdb": "duckdb", "snowflake": "snowflake.connector"}.get(db_type)
    if module is None:
        return None
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ValueError):
        return db_type
    return None if spec is not None else db_type


@app.command()
@friendly_errors
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

    console = Console(stderr=True)
    console.print(f"[green]Added connection '[bold]{name}[/bold]' to {config_file}[/green]")

    missing = _missing_backend_extra(db_type)
    if missing:
        console.print(
            f"[yellow]Warning:[/yellow] the {db_type} backend isn't installed. "
            f"Run [bold]uv pip install 'querido\\[{missing}]'[/bold] "
            "before using this connection."
        )


@app.command("list")
@friendly_errors
def list_connections() -> None:
    """List all configured connections."""
    from querido.config import get_config_dir, load_connections
    from querido.output.envelope import emit_envelope, is_structured_format

    connections = load_connections()
    rows = [
        {
            "name": conn_name,
            "type": conn_config.get("type", "?"),
            "path": conn_config.get("path"),
            "account": conn_config.get("account"),
            "database": conn_config.get("database"),
            "schema": conn_config.get("schema"),
            "role": conn_config.get("role"),
            "warehouse": conn_config.get("warehouse"),
        }
        for conn_name, conn_config in sorted(connections.items())
    ]

    if is_structured_format():
        emit_envelope(command="config list", data={"connections": rows})
        return

    from rich.console import Console
    from rich.table import Table

    console = Console()

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
@friendly_errors
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

    console = Console(stderr=True)
    console.print(
        f"[green]Cloned '[bold]{source}[/bold]' → '[bold]{name}[/bold]' in {config_file}[/green]"
    )

    source_type = str(existing.get(name, {}).get("type", ""))
    missing = _missing_backend_extra(source_type)
    if missing:
        console.print(
            f"[yellow]Warning:[/yellow] the {source_type} backend isn't installed. "
            f"Run [bold]uv pip install 'querido\\[{missing}]'[/bold] "
            "before using this connection."
        )


@app.command()
@friendly_errors
def remove(
    name: str = typer.Option(..., "--name", "-n", help="Connection name to remove."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Remove a named connection from connections.toml.

    Saved column sets referencing this connection are left in place —
    remove them with ``qdo config column-set delete`` if you no longer
    need them.
    """
    from querido.config import get_config_dir, load_connections

    config_dir = get_config_dir()
    config_file = config_dir / "connections.toml"

    existing = load_connections(config_dir)
    if name not in existing:
        raise typer.BadParameter(
            f"Connection '{name}' not found. Use 'qdo config list' to see configured connections."
        )

    if not yes:
        confirmed = typer.confirm(f"Remove connection '{name}'?", default=False, err=True)
        if not confirmed:
            from rich.console import Console

            Console(stderr=True).print("[dim]Aborted — no connection removed.[/dim]")
            raise typer.Exit(0)

    del existing[name]
    _write_connections(config_file, existing)

    from rich.console import Console

    Console(stderr=True).print(
        f"[green]Removed connection '[bold]{name}[/bold]' from {config_file}[/green]"
    )


@app.command()
@friendly_errors
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


# ---------------------------------------------------------------------------
# Column set management
# ---------------------------------------------------------------------------

column_set_app = typer.Typer(help="Manage saved column sets.")
app.add_typer(column_set_app, name="column-set")


@column_set_app.command("save")
@friendly_errors
def column_set_save(
    connection: str = typer.Option(..., "--connection", "-c", help="Connection name."),
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    name: str = typer.Option(..., "--name", "-n", help="Column set name."),
    columns: str = typer.Option(..., "--columns", help="Comma-separated column names."),
) -> None:
    """Save a named column set for a connection + table."""
    from rich.console import Console

    from querido.config import save_column_set

    col_list = [c.strip() for c in columns.split(",") if c.strip()]
    if not col_list:
        raise typer.BadParameter("No columns provided.")

    save_column_set(connection, table, name, col_list)
    Console(stderr=True).print(
        f"[green]Saved column set '[bold]{name}[/bold]' "
        f"({len(col_list)} columns) for {connection}.{table}[/green]"
    )


@column_set_app.command("list")
@friendly_errors
def column_set_list(
    connection: str | None = typer.Option(
        None, "--connection", "-c", help="Filter by connection."
    ),
    table: str | None = typer.Option(None, "--table", "-t", help="Filter by table."),
) -> None:
    """List saved column sets."""
    from rich.console import Console
    from rich.table import Table

    from querido.config import list_column_sets

    console = Console()
    sets = list_column_sets(connection=connection, table=table)

    if not sets:
        console.print("[dim]No column sets found.[/dim]")
        return

    grid = Table(title="Saved Column Sets", show_lines=True)
    grid.add_column("Connection", style="cyan bold")
    grid.add_column("Table", style="green")
    grid.add_column("Set Name", style="yellow")
    grid.add_column("Columns", style="dim")

    for key, cols in sets.items():
        parts = key.split(".", 2)
        if len(parts) != 3:
            continue
        k_conn, k_table, k_name = parts
        grid.add_row(k_conn, k_table, k_name, ", ".join(cols))

    console.print(grid)


@column_set_app.command("show")
@friendly_errors
def column_set_show(
    connection: str = typer.Option(..., "--connection", "-c", help="Connection name."),
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    name: str = typer.Option(..., "--name", "-n", help="Column set name."),
) -> None:
    """Show columns in a saved column set."""
    from rich.console import Console

    from querido.config import load_column_set

    cols = load_column_set(connection, table, name)
    console = Console()
    if cols is None:
        console.print(f"[red]Column set '{name}' not found for {connection}.{table}[/red]")
        raise typer.Exit(1)
    console.print(f"[bold]{name}[/bold] ({connection}.{table}): {len(cols)} columns")
    for col in cols:
        console.print(f"  {col}")


@column_set_app.command("delete")
@friendly_errors
def column_set_delete(
    connection: str = typer.Option(..., "--connection", "-c", help="Connection name."),
    table: str = typer.Option(..., "--table", "-t", help="Table name."),
    name: str = typer.Option(..., "--name", "-n", help="Column set name."),
) -> None:
    """Delete a saved column set."""
    from rich.console import Console

    from querido.config import delete_column_set

    deleted = delete_column_set(connection, table, name)
    console = Console(stderr=True)
    if deleted:
        console.print(
            f"[green]Deleted column set '[bold]{name}[/bold]' for {connection}.{table}[/green]"
        )
    else:
        console.print(f"[red]Column set '{name}' not found for {connection}.{table}[/red]")
        raise typer.Exit(1)


def _write_connections(config_file: Path | str, connections: dict) -> None:
    """Write connections dict back to TOML format using tomli-w."""
    from querido.config import _write_toml_atomic

    _write_toml_atomic(Path(config_file), {"connections": connections})
