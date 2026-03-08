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
    for key, val in [
        ("account", account),
        ("user", user),
        ("warehouse", warehouse),
        ("database", database),
        ("schema", schema),
        ("role", role),
        ("auth", auth),
    ]:
        if val:
            entry[key] = val

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

    grid = Table(title="Configured Connections", show_lines=True)
    grid.add_column("Name", style="cyan bold")
    grid.add_column("Type", style="green")
    grid.add_column("Details", style="dim")

    for conn_name, conn_config in connections.items():
        db_type = conn_config.get("type", "?")
        if db_type in ("sqlite", "duckdb"):
            details = conn_config.get("path", "")
        else:
            parts = []
            for key in ("account", "database", "schema", "warehouse"):
                if key in conn_config:
                    parts.append(f"{key}={conn_config[key]}")
            details = ", ".join(parts)
        grid.add_row(conn_name, db_type, details)

    console.print(grid)


def _write_connections(config_file: Path | str, connections: dict) -> None:
    """Write connections dict back to TOML format.

    All connection values are currently strings, so we quote everything.
    If non-string values are needed in the future, use a proper TOML writer.
    """
    lines = []
    for name, config in connections.items():
        lines.append(f"[connections.{name}]")
        for key, val in config.items():
            escaped = str(val).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
        lines.append("")

    Path(config_file).write_text("\n".join(lines) + "\n")
