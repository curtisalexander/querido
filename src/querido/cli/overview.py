"""``qdo overview`` — print CLI reference (markdown or json).

The JSON output is auto-generated from Typer/Click command metadata so it
never drifts from the actual CLI.  Output shapes (for agent consumption) are
maintained in ``_OUTPUT_SHAPES`` — these describe the JSON structure each
command emits.
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="Print CLI overview (markdown or json).")


@app.callback(invoke_without_command=True)
def overview() -> None:
    """Print the full CLI reference.

    Useful for piping into an LLM or pager:

        qdo overview | less
        qdo overview | pbcopy
        qdo -f json overview   # structured command metadata for agents
    """
    from querido.cli._context import get_output_format

    fmt = get_output_format()

    if fmt == "json":
        _print_json()
        return

    docs = Path(__file__).resolve().parents[3] / "docs" / "cli-reference.md"
    if docs.exists():
        print(docs.read_text())
    else:
        _print_fallback()


# ---------------------------------------------------------------------------
# Markdown fallback — auto-generated from command categories
# ---------------------------------------------------------------------------


def _print_fallback() -> None:
    """Minimal reference when the docs/ directory is not available."""
    from querido import __version__
    from querido.cli.main import _COMMAND_CATEGORIES

    lines = [
        f"# qdo CLI Reference (v{__version__})",
        "",
        "`qdo` is a CLI data-analysis toolkit for SQLite, DuckDB, and Snowflake.",
        "",
        "## Quick Start",
        "",
        "```bash",
        "qdo preview -c ./my.db -t users          # preview rows",
        "qdo inspect -c ./my.db -t users          # column metadata",
        "qdo profile -c ./my.db -t users          # statistical profile",
        "qdo context -c ./my.db -t users          # schema + stats + sample values",
        "qdo catalog -c ./my.db                   # full database catalog",
        "```",
        "",
        "## Commands",
        "",
    ]

    for category, cmds in _COMMAND_CATEGORIES:
        lines.append(f"### {category}")
        lines.append("")
        lines.append("| Command | Purpose |")
        lines.append("|---------|---------|")
        for name, _mod, help_text in cmds:
            lines.append(f"| `{name}` | {help_text} |")
        lines.append("")

    lines += [
        "## Global Options",
        "",
        "`--format`, `-f` : rich, json, csv, markdown, html, yaml",
        "`--show-sql`     : Print rendered SQL to stderr",
        "`--debug`        : Enable debug logging to stderr",
        "`--version`, `-V`: Show version",
        "",
        "## Agent Mode",
        "",
        "Set `QDO_FORMAT=json` in your environment to get structured JSON from all",
        "commands by default. Explicit `--format` always takes priority.",
        "",
        "```bash",
        "export QDO_FORMAT=json",
        "qdo catalog -c mydb              # JSON schema",
        'qdo query -c mydb --sql "..."    # JSON results',
        "```",
        "",
        "Run `qdo <command> --help` for details on any command.",
    ]

    print("\n".join(lines))


# ---------------------------------------------------------------------------
# JSON output — auto-generated from Typer/Click metadata
# ---------------------------------------------------------------------------

# Output shapes document the JSON structure each command emits.
# These are maintained manually because they describe runtime output, not
# CLI parameters.  Keys map to command names.
_OUTPUT_SHAPES: dict[str, dict] = {
    "inspect": {
        "table": "string",
        "row_count": "integer",
        "columns": [
            {
                "name": "string",
                "type": "string",
                "nullable": "boolean",
                "default": "string|null",
                "primary_key": "boolean",
            }
        ],
    },
    "preview": {
        "table": "string",
        "limit": "integer",
        "row_count": "integer",
        "rows": [{"column_name": "value"}],
    },
    "profile": {
        "table": "string",
        "row_count": "integer",
        "sampled": "boolean",
        "sample_size": "integer|null",
        "columns": [
            {
                "column_name": "string",
                "column_type": "string",
                "min_val": "any",
                "max_val": "any",
                "null_count": "integer",
                "distinct_count": "integer",
            }
        ],
    },
    "context": {
        "table": "string",
        "dialect": "string",
        "row_count": "integer",
        "columns": [
            {
                "name": "string",
                "type": "string",
                "nullable": "boolean",
                "null_pct": "float",
                "distinct_count": "integer",
                "min": "any|null",
                "max": "any|null",
                "sample_values": ["string"],
                "description": "string|null",
            }
        ],
    },
    "dist": {
        "table": "string",
        "column": "string",
        "mode": "numeric|categorical",
        "total_rows": "integer",
        "null_count": "integer",
        "buckets": [{"bucket_min": "number", "bucket_max": "number", "count": "integer"}],
        "values": [{"value": "any", "count": "integer"}],
    },
    "query": {
        "columns": ["string"],
        "row_count": "integer",
        "limited": "boolean",
        "rows": [{"column_name": "value"}],
    },
    "catalog": {
        "table_count": "integer",
        "tables": [
            {
                "name": "string",
                "type": "table|view",
                "row_count": "integer|null",
                "columns": [
                    {
                        "name": "string",
                        "type": "string",
                        "nullable": "boolean",
                        "comment": "string",
                    }
                ],
            }
        ],
    },
    "values": {
        "table": "string",
        "column": "string",
        "distinct_count": "integer",
        "total_rows": "integer",
        "null_count": "integer",
        "truncated": "boolean",
        "values": [{"value": "any", "count": "integer"}],
    },
    "pivot": {
        "headers": ["string"],
        "rows": [{"column_name": "value"}],
        "row_count": "integer",
        "sql": "string",
    },
    "assert": {
        "passed": "boolean",
        "actual": "number",
        "expected": "number",
        "operator": "eq|gt|lt|gte|lte",
        "name": "string|null",
        "sql": "string",
    },
    "quality": {
        "table": "string",
        "row_count": "integer",
        "duplicate_rows": "integer|null",
        "columns": [
            {
                "name": "string",
                "type": "string",
                "null_count": "integer",
                "null_pct": "float",
                "distinct_count": "integer",
                "uniqueness_pct": "float",
                "status": "ok|warn|fail",
                "issues": ["string"],
            }
        ],
    },
    "joins": {
        "source": "string",
        "candidates": [
            {
                "target_table": "string",
                "join_keys": [
                    {
                        "source_col": "string",
                        "target_col": "string",
                        "match_type": "exact_name|convention",
                        "confidence": "float (0-1)",
                    }
                ],
            }
        ],
    },
    "diff": {
        "left": "string",
        "right": "string",
        "added": [{"name": "string", "type": "string", "nullable": "boolean"}],
        "removed": [{"name": "string", "type": "string", "nullable": "boolean"}],
        "changed": [{"name": "string", "left_type": "string", "right_type": "string"}],
        "unchanged_count": "integer",
    },
    "explain": {
        "plan": "string",
        "sql": "string",
        "dialect": "string",
        "analyzed": "boolean",
    },
    "view-def": {"view": "string", "dialect": "string", "definition": "string"},
    "template": {
        "table": "string",
        "row_count": "integer",
        "table_comment": "string|null",
        "columns": [
            {
                "name": "string",
                "type": "string",
                "nullable": "boolean",
                "distinct_count": "integer",
                "null_count": "integer",
                "sample_values": "string",
            }
        ],
    },
    "metadata": {
        "table": "string",
        "connection": "string",
        "row_count": "integer",
        "table_description": "string",
        "data_owner": "string",
        "columns": [
            {
                "name": "string",
                "type": "string",
                "description": "string",
                "distinct_count": "integer",
            }
        ],
    },
}


def _introspect_command(name: str, module_path: str) -> dict:
    """Introspect a Typer subcommand module to extract options and metadata."""
    import importlib

    import click

    mod = importlib.import_module(module_path)
    sub_app: typer.Typer = mod.app
    click_group = typer.main.get_group(sub_app)

    # Extract description from the click group or callback
    description = click_group.help or ""

    # Extract subcommands if this is a group with children
    subcommands = None
    if hasattr(click_group, "commands") and click_group.commands:
        subcommands = sorted(click_group.commands.keys())
    elif hasattr(click_group, "list_commands"):
        try:
            import click

            ctx = click.Context(click_group)
            sub_names = click_group.list_commands(ctx)
            if sub_names:
                subcommands = sorted(sub_names)
        except Exception:
            pass

    # Extract options from the main callback command
    options = []
    for param in click_group.params:
        if isinstance(param, click.Option):
            flag = ", ".join(param.opts)
            opt: dict = {
                "flag": flag,
                "required": param.required,
                "help": param.help or "",
            }
            options.append(opt)

    result: dict = {
        "name": name,
        "description": description.split("\n")[0].strip() if description else "",
    }
    if options:
        result["options"] = options
    if subcommands:
        result["subcommands"] = subcommands

    output_shape = _OUTPUT_SHAPES.get(name)
    if output_shape:
        result["output_shape"] = output_shape

    return result


def _print_json() -> None:
    """Emit structured JSON describing all commands, auto-generated from Typer metadata."""
    import json

    from querido import __version__
    from querido.cli.main import _COMMAND_CATEGORIES

    commands = []
    for category, cmds in _COMMAND_CATEGORIES:
        for name, module_path, help_text in cmds:
            try:
                cmd = _introspect_command(name, module_path)
                cmd["category"] = category
            except Exception:
                # Fallback: minimal entry from category metadata
                cmd = {
                    "name": name,
                    "description": help_text,
                    "category": category,
                }
            commands.append(cmd)

    global_options = [
        {
            "flag": "-f, --format",
            "values": ["rich", "json", "csv", "markdown", "html", "yaml"],
            "default": "rich",
            "help": "Output format.",
        },
        {"flag": "--show-sql", "help": "Print rendered SQL to stderr before executing."},
        {"flag": "--debug", "help": "Enable debug logging to stderr."},
        {"flag": "-V, --version", "help": "Show version and exit."},
    ]

    connection_resolution = {
        "description": "The -c flag accepts a named connection or a file path.",
        "rules": [
            "Named connection: looked up in connections.toml",
            "File path with .duckdb/.ddb extension: DuckDB",
            "File path with .parquet extension: Parquet (via DuckDB)",
            "Other file path: SQLite",
            "Override with --db-type",
        ],
    }

    error_shape = {
        "description": "When --format json is active, errors are emitted as JSON to stderr.",
        "shape": {
            "error": True,
            "code": "TABLE_NOT_FOUND|COLUMN_NOT_FOUND|DATABASE_ERROR|...",
            "message": "string",
            "hint": "string|null",
            "sql": "string|null",
        },
    }

    payload = {
        "version": __version__,
        "tool": "qdo",
        "description": "CLI data analysis toolkit for SQLite, DuckDB, and Snowflake.",
        "commands": commands,
        "global_options": global_options,
        "connection_resolution": connection_resolution,
        "error_format": error_shape,
        "agent_setup": {
            "description": (
                "Set QDO_FORMAT=json in your agent's environment to get "
                "structured JSON output from all commands by default."
            ),
            "env_var": "QDO_FORMAT",
            "valid_values": ["rich", "json", "csv", "markdown", "html", "yaml"],
            "priority": "explicit --format flag > QDO_FORMAT env var > rich",
            "recommended_workflow": [
                "export QDO_FORMAT=json",
                "qdo catalog -c <conn>  # full schema",
                "qdo context -c <conn> -t <table>  # schema + stats + sample values",
                "qdo query -c <conn> --sql '...'  # ad-hoc queries",
                "qdo assert -c <conn> --sql '...' --expect 0  # validate results",
            ],
        },
    }

    print(json.dumps(payload, indent=2))
