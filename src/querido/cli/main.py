from __future__ import annotations

import importlib
import sys
from typing import Any

import click
import typer
from typer.core import TyperGroup

from querido.cli.argv_hoist import hoist_format_flag

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
        "Start Here",
        [
            ("catalog", "querido.cli.catalog", "Discover tables, columns, and row counts."),
            ("context", "querido.cli.context", "Understand one table in a single call."),
            ("metadata", "querido.cli.metadata", "Capture and read shared table knowledge."),
            ("query", "querido.cli.query", "Answer a question with ad-hoc SQL."),
            ("report", "querido.cli.report", "Generate a shareable HTML hand-off report."),
        ],
    ),
    (
        "Investigate Deeper",
        [
            ("inspect", "querido.cli.inspect", "Inspect table structure."),
            ("preview", "querido.cli.preview", "Preview rows from a table."),
            ("profile", "querido.cli.profile", "Profile table data."),
            ("dist", "querido.cli.dist", "Column distribution visualization."),
            ("values", "querido.cli.values", "Show distinct values for a column."),
            (
                "freshness",
                "querido.cli.freshness",
                "Detect timestamp columns and summarize recency.",
            ),
            ("quality", "querido.cli.quality", "Data quality summary for a table."),
            ("diff", "querido.cli.diff", "Compare schemas between two tables."),
            ("joins", "querido.cli.joins", "Discover likely join keys between tables."),
            ("pivot", "querido.cli.pivot", "Pivot / aggregate table data."),
            ("explain", "querido.cli.explain", "Show query execution plan (EXPLAIN)."),
            ("assert", "querido.cli.assert_cmd", "Assert conditions on query results."),
            ("export", "querido.cli.export", "Export data to a file (csv, tsv, json, jsonl)."),
        ],
    ),
    (
        "Automate And Share",
        [
            (
                "bundle",
                "querido.cli.bundle",
                "Export, import, inspect, or diff knowledge bundles.",
            ),
            (
                "workflow",
                "querido.cli.workflow",
                "Run, lint, list, or show declarative workflows.",
            ),
            ("session", "querido.cli.session", "Manage agent-workflow sessions."),
            ("template", "querido.cli.template", "Generate documentation templates for tables."),
        ],
    ),
    (
        "Generate",
        [
            ("sql", "querido.cli.sql", "Generate SQL statements for a table."),
            ("view-def", "querido.cli.view_def", "Show SQL definition of a view."),
        ],
    ),
    (
        "Setup",
        [
            ("config", "querido.cli.config", "Manage connections."),
            ("cache", "querido.cli.cache", "Manage local metadata cache."),
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
            (
                "explore",
                "querido.cli.explore",
                "Interactive TUI with selected-column context and wide-table triage.",
            ),
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

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        """Record the raw subcommand argv on the context before dispatch.

        The session recorder (installed by the root callback) reads this in
        its finalizer to persist the exact invocation to ``steps.jsonl``.
        """
        ctx.ensure_object(dict)
        ctx.obj["_raw_argv"] = list(args)
        return super().resolve_command(ctx, args)

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
                    ("catalog -c my.db", "Discover tables to investigate."),
                    ("context -c my.db -t users", "Understand one table in depth."),
                    ("metadata init -c my.db -t users", "Capture what you've learned."),
                    ("query -c my.db --sql 'select ...'", "Answer a concrete question."),
                    ("report table -c my.db -t users", "Hand off a shareable report."),
                ]
            )


# ---------------------------------------------------------------------------
# Build the app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="qdo",
    help=(
        "Agent-first data exploration CLI — accumulate understanding of your data so "
        "every subsequent investigation is sharper than the last."
    ),
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


def _maybe_start_session(ctx: typer.Context) -> None:
    """If ``QDO_SESSION`` is set, install a stdout tee and register a finalizer.

    The session records one JSONL step per CLI invocation into
    ``.qdo/sessions/<name>/``. The finalizer runs during context teardown so
    the step is recorded whether the command succeeds or fails.
    """
    import sys

    from querido.core.session import SessionRecorder, active_session_name

    name = active_session_name()
    if not name:
        return

    # argv is captured by LazyGroup.resolve_command() into ctx.obj before the
    # subcommand dispatches. Kick off the recorder here (pre-subcommand) so
    # stdout capture is active from the start.
    ctx.ensure_object(dict)

    recorder = SessionRecorder(name=name, argv=[])
    recorder.start()

    def _finalize() -> None:
        raw_argv = ctx.obj.get("_raw_argv") or sys.argv[1:]
        # Skip for ``qdo session ...`` meta-commands — recording a
        # ``session show`` into its own session is confusing.
        if raw_argv and raw_argv[0] == "session":
            recorder.cancel()
            return
        recorder.argv = list(raw_argv)
        exc_info = sys.exc_info()
        exit_code = 0
        if exc_info[0] is not None:
            exc = exc_info[1]
            if isinstance(exc, SystemExit):
                code = exc.code
                exit_code = int(code) if isinstance(code, int) else 1
            elif isinstance(exc, (typer.Exit,)):
                exit_code = int(getattr(exc, "exit_code", 1) or 0)
            else:
                exit_code = 1
        recorder.stop(exit_code=exit_code)

    ctx.call_on_close(_finalize)


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
        help="Output format: rich, markdown, json, csv, html, yaml, agent.",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug logging to stderr.",
    ),
) -> None:
    """qdo — query, do. Data analysis from your terminal."""
    import os

    _maybe_start_session(ctx)

    valid = {"rich", "markdown", "json", "csv", "html", "yaml", "agent"}

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


def run() -> None:
    """Console-script entrypoint. Hoists `-f/--format` to the front of argv so
    it reaches the root callback regardless of where an agent placed it, then
    hands off to the Typer app.

    Also reconfigures stdout/stderr to UTF-8 with ``errors="replace"``. On
    Windows the default codec is ``cp1252`` — which can't encode the bullet
    characters and em dashes Rich emits — and any non-TTY invocation (pipe,
    redirect, subprocess) crashes with ``UnicodeEncodeError``. This bit us on
    Windows CI via ``session replay`` child processes; the fix is global so
    it also covers users piping qdo output into other tools.
    """
    import contextlib

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with contextlib.suppress(OSError, ValueError):
                reconfigure(encoding="utf-8", errors="replace")
    sys.argv[1:] = hoist_format_flag(sys.argv[1:])
    app()
