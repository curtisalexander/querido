from __future__ import annotations


def _get_root_obj() -> dict:
    """Walk up the Click context chain and return the root context's obj dict."""
    import click

    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return {}

    root = ctx
    while root.parent is not None:
        root = root.parent

    return root.obj or {}


def get_output_format() -> str:
    """Return the --format value from the root CLI context, defaulting to 'rich'."""
    return _get_root_obj().get("format", "rich")


def maybe_show_sql(sql: str) -> None:
    """Print SQL to stderr if --show-sql was passed."""
    if not _get_root_obj().get("show_sql"):
        return

    from rich.console import Console
    from rich.syntax import Syntax

    console = Console(stderr=True)
    console.print()
    console.print(Syntax(sql.strip(), "sql", theme="monokai", line_numbers=False))
    console.print()
