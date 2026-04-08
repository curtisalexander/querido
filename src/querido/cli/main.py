from __future__ import annotations

import importlib
from typing import Any

import click
import typer
from typer.core import TyperGroup

# ---------------------------------------------------------------------------
# Lazy subcommand loading
# ---------------------------------------------------------------------------
# Instead of importing all 14 subcommand modules at startup, we only import
# the module for the subcommand actually being invoked.  This avoids paying
# the import cost of every subcommand on every CLI call (including --help).

# Commands are organized by category for --help display.  Each entry is
# (command_name, module_path, help_text).  The order here controls the
# order in the help output.
_COMMAND_CATEGORIES: list[tuple[str, list[tuple[str, str, str]]]] = [
    (
        "Explore",
        [
            ("inspect", "querido.cli.inspect", "Inspect table structure."),
            ("preview", "querido.cli.preview", "Preview rows from a table."),
            ("profile", "querido.cli.profile", "Profile table data."),
            ("dist", "querido.cli.dist", "Column distribution visualization."),
            ("values", "querido.cli.values", "Show distinct values for a column."),
            ("quality", "querido.cli.quality", "Data quality summary for a table."),
            ("search", "querido.cli.search", "Search table and column metadata."),
            ("diff", "querido.cli.diff", "Compare schemas between two tables."),
            ("joins", "querido.cli.joins", "Discover likely join keys between tables."),
        ],
    ),
    (
        "Query",
        [
            ("query", "querido.cli.query", "Execute ad-hoc SQL queries."),
            ("catalog", "querido.cli.catalog", "Show full database catalog."),
            ("pivot", "querido.cli.pivot", "Pivot / aggregate table data."),
            ("explain", "querido.cli.explain", "Show query execution plan (EXPLAIN)."),
            ("assert", "querido.cli.assert_cmd", "Assert conditions on query results."),
            ("export", "querido.cli.export", "Export data to a file (csv, tsv, json, jsonl)."),
        ],
    ),
    (
        "Generate",
        [
            ("sql", "querido.cli.sql", "Generate SQL statements for a table."),
            ("template", "querido.cli.template", "Generate documentation templates for tables."),
            ("lineage", "querido.cli.lineage", "View definition and simple lineage."),
        ],
    ),
    (
        "Manage",
        [
            ("config", "querido.cli.config", "Manage connections."),
            ("cache", "querido.cli.cache", "Manage local metadata cache."),
            ("metadata", "querido.cli.metadata", "Manage enriched table metadata."),
            ("completion", "querido.cli.completion", "Generate shell completion scripts."),
        ],
    ),
    (
        "Snowflake",
        [
            ("snowflake", "querido.cli.snowflake", "Snowflake-specific commands."),
        ],
    ),
    (
        "Interactive",
        [
            ("explore", "querido.cli.explore", "Interactive data exploration (TUI)."),
            ("serve", "querido.cli.serve", "Serve interactive web UI."),
        ],
    ),
    (
        "Learn",
        [
            ("tutorial", "querido.cli.tutorial", "Interactive tutorial with National Parks data."),
        ],
    ),
    (
        "Reference",
        [
            ("overview", "querido.cli.overview", "Print CLI overview (markdown)."),
        ],
    ),
]

# Flatten for lookup — preserves the same {name: (module, help)} structure
# that LazyGroup.get_command() expects.
_SUBCOMMANDS: dict[str, tuple[str, str]] = {
    name: (mod, help_text) for _, cmds in _COMMAND_CATEGORIES for name, mod, help_text in cmds
}


class LazyGroup(TyperGroup):
    """A Click Group that defers subcommand imports until actually needed."""

    def __init__(
        self,
        *args: Any,
        lazy_subcommands: dict[str, tuple[str, str]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._lazy_subcommands: dict[str, tuple[str, str]] = lazy_subcommands or {}
        self._command_categories: list[tuple[str, list[tuple[str, str, str]]]] = []

    # -- Click Group interface -----------------------------------------------

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Return all command names (eager + lazy) sorted alphabetically."""
        base = super().list_commands(ctx)
        lazy = list(self._lazy_subcommands.keys())
        return sorted(set(base + lazy))

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        # Try eagerly-registered commands first (the @app.callback, etc.)
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd

        if cmd_name not in self._lazy_subcommands:
            return None

        # Import the module and extract the Typer app
        module_path, _help = self._lazy_subcommands[cmd_name]
        mod = importlib.import_module(module_path)
        sub_app: typer.Typer = mod.app

        # Convert the Typer sub-app to a Click group and register it
        click_group = typer.main.get_group(sub_app)
        click_group.name = cmd_name
        self.add_command(click_group, cmd_name)
        return click_group

    def _get_help_text(self, ctx: click.Context, name: str) -> str:
        """Get help text for a command without importing it if possible."""
        cmd = super().get_command(ctx, name)
        if cmd is not None:
            return cmd.get_short_help_str(limit=80)
        if name in self._lazy_subcommands:
            _, help_text = self._lazy_subcommands[name]
            return help_text
        return ""

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Show commands grouped by category."""
        if not self._command_categories:
            # Fallback to flat list if categories aren't configured
            return super().format_commands(ctx, formatter)

        for category, cmds in self._command_categories:
            rows = []
            for name, _mod, _help in cmds:
                help_text = self._get_help_text(ctx, name)
                rows.append((name, help_text))
            if rows:
                with formatter.section(f"{category} Commands"):
                    formatter.write_dl(rows)

        # Quick start hint after all command categories
        formatter.write("\n")
        with formatter.section("Quick start"):
            formatter.write_dl(
                [
                    ("catalog -c my.db", "List all tables"),
                    ("inspect -c my.db -t users", "Show table columns"),
                    ("preview -c my.db -t users", "See sample rows"),
                    ("profile -c my.db -t users", "Profile statistics"),
                ]
            )


# ---------------------------------------------------------------------------
# Build the app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="qdo",
    help="CLI data analysis toolkit for SQLite, DuckDB, and Snowflake.",
    no_args_is_help=True,
    cls=LazyGroup,
    invoke_without_command=True,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)

# Inject lazy subcommands into the underlying Click group.  Typer constructs
# the Click group at call-time via get_group(), so we register them via a
# callback that patches the group after Typer builds it.
_original_get_group = typer.main.get_group


def _patched_get_group(typer_app: typer.Typer, **kwargs: Any) -> click.Group:
    group = _original_get_group(typer_app, **kwargs)
    if isinstance(group, LazyGroup) and typer_app is app:
        group._lazy_subcommands = _SUBCOMMANDS
        group._command_categories = _COMMAND_CATEGORIES
    return group


typer.main.get_group = _patched_get_group  # type: ignore[assignment]


def version_callback(value: bool) -> None:
    if value:
        from querido import __version__

        print(f"qdo {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
    show_sql: bool = typer.Option(
        False,
        "--show-sql",
        help="Print rendered SQL to stderr before executing.",
    ),
    output_format: str | None = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format: rich, markdown, json, csv, html, yaml.",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug logging to stderr.",
    ),
) -> None:
    """qdo — query, do. Data analysis from your terminal."""
    import os

    valid = {"rich", "markdown", "json", "csv", "html", "yaml"}

    # Resolve format: explicit --format > QDO_FORMAT env var > "rich"
    if output_format is None:
        env_fmt = os.environ.get("QDO_FORMAT", "").lower().strip()
        output_format = env_fmt if env_fmt in valid else "rich"

    if output_format not in valid:
        raise typer.BadParameter(f"--format must be one of: {', '.join(sorted(valid))}")
    ctx.ensure_object(dict)
    ctx.obj["show_sql"] = show_sql
    ctx.obj["format"] = output_format
    ctx.obj["debug"] = debug

    import logging

    logger = logging.getLogger("querido")
    # Reset handlers to avoid accumulation across CliRunner invocations in tests
    logger.handlers.clear()
    if debug:
        import sys

        logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("[qdo] %(message)s"))
        logger.addHandler(handler)
    else:
        logger.setLevel(logging.WARNING)
