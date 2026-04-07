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
        # Fallback: bundled inline reference when running from an installed
        # package where the docs/ directory may not be present.
        _print_fallback()


def _print_fallback() -> None:
    """Minimal inline reference when the docs file is not available."""
    from querido import __version__

    print(f"""\
# qdo CLI Reference (v{__version__})

`qdo` is a CLI data-analysis toolkit for SQLite, DuckDB, and Snowflake.

## Quick Start

```bash
qdo preview -c ./my.db -t users          # preview rows
qdo inspect -c ./my.db -t users          # column metadata
qdo profile -c ./my.db -t users          # statistical profile
qdo search  -c ./my.db -p email          # search tables/columns
qdo sql ddl -c ./my.db -t users          # generate DDL
```

## Commands

| Command | Purpose |
|---------|---------|
| `inspect -c CONN -t TABLE` | Column metadata and row count |
| `preview -c CONN -t TABLE [-r ROWS]` | Preview rows (default 20) |
| `profile -c CONN -t TABLE [--top N]` | Statistical profile |
| `dist -c CONN -t TABLE -C COLUMN` | Column distribution |
| `search -c CONN -p PATTERN` | Search tables/columns by name |
| `lineage -c CONN -v VIEW` | View SQL definition |
| `template -c CONN -t TABLE` | Documentation template |
| `sql select\\|ddl\\|insert -c CONN -t TABLE` | Generate SQL |
| `cache sync -c CONN` | Cache metadata locally |
| `config add` | Add named connection |
| `config clone` | Clone connection with overrides |
| `config list` | List connections |
| `explore -c CONN -t TABLE` | Interactive TUI |
| `serve -c CONN` | Web UI |
| `overview` | This reference |

## Global Options

`--format`, `-f` : rich, json, csv, markdown, html, yaml
`--show-sql`     : Print rendered SQL to stderr
`--version`, `-V`: Show version

Run `qdo <command> --help` for details on any command.
""")


def _print_json() -> None:
    """Emit structured JSON describing all commands, options, and output shapes."""
    import json

    from querido import __version__

    commands = [
        {
            "name": "inspect",
            "description": "Show column metadata and row count for a table.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "-t, --table", "required": True, "help": "Table name."},
                {
                    "flag": "-v, --verbose",
                    "required": False,
                    "help": "Include table/column comments.",
                },
            ],
            "example": "qdo inspect -c ./my.db -t users",
            "output_shape": {
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
        },
        {
            "name": "preview",
            "description": "Preview sample rows from a table.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "-t, --table", "required": True, "help": "Table name."},
                {"flag": "-r, --rows", "required": False, "help": "Number of rows (default 20)."},
            ],
            "example": "qdo preview -c ./my.db -t users -r 5",
            "output_shape": {
                "table": "string",
                "limit": "integer",
                "row_count": "integer",
                "rows": [{"column_name": "value"}],
            },
        },
        {
            "name": "profile",
            "description": "Statistical profile of columns (min, max, mean, nulls, distinct).",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "-t, --table", "required": True, "help": "Table name."},
                {
                    "flag": "--columns",
                    "required": False,
                    "help": "Comma-separated column names to profile.",
                },
                {
                    "flag": "--sample N",
                    "required": False,
                    "help": "Sample size (default: auto-sample at >1M rows).",
                },
                {"flag": "--no-sample", "required": False, "help": "Disable sampling."},
                {
                    "flag": "--top N",
                    "required": False,
                    "help": "Show top-N frequent values per column.",
                },
            ],
            "example": "qdo profile -c ./my.db -t users --top 5",
            "output_shape": {
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
        },
        {
            "name": "dist",
            "description": "Column distribution — histogram for numeric, top-N for categorical.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "-t, --table", "required": True, "help": "Table name."},
                {"flag": "-C, --column", "required": True, "help": "Column to analyze."},
                {
                    "flag": "--buckets N",
                    "required": False,
                    "help": "Number of histogram buckets (default 20).",
                },
                {
                    "flag": "--top N",
                    "required": False,
                    "help": "Top-N values for categorical (default 20).",
                },
            ],
            "example": "qdo dist -c ./my.db -t users -C city",
            "output_shape": {
                "table": "string",
                "column": "string",
                "mode": "numeric|categorical",
                "total_rows": "integer",
                "null_count": "integer",
                "buckets": [{"bucket_min": "number", "bucket_max": "number", "count": "integer"}],
                "values": [{"value": "any", "count": "integer"}],
            },
        },
        {
            "name": "search",
            "description": "Search table and column names by substring pattern.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {
                    "flag": "-p, --pattern",
                    "required": True,
                    "help": "Search pattern (case-insensitive).",
                },
                {
                    "flag": "--type",
                    "required": False,
                    "help": "Filter: table, column, or all (default: all).",
                },
                {
                    "flag": "--no-cache",
                    "required": False,
                    "help": "Bypass cache and query directly.",
                },
            ],
            "example": "qdo search -c ./my.db -p email",
            "output_shape": {
                "pattern": "string",
                "results": [
                    {
                        "table_name": "string",
                        "table_type": "string",
                        "match_type": "string",
                        "column_name": "string|null",
                        "column_type": "string|null",
                    }
                ],
            },
        },
        {
            "name": "template",
            "description": "Generate documentation template with auto-populated metadata.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "-t, --table", "required": True, "help": "Table name."},
                {
                    "flag": "--sample-values N",
                    "required": False,
                    "help": "Sample values per column (default 3, 0 to skip).",
                },
            ],
            "example": "qdo template -c ./my.db -t users",
            "output_shape": {
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
        },
        {
            "name": "lineage",
            "description": "Retrieve the SQL definition of a view.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "-v, --view", "required": True, "help": "View name."},
            ],
            "example": "qdo lineage -c ./my.db -v my_view",
            "output_shape": {"view": "string", "dialect": "string", "definition": "string"},
        },
        {
            "name": "sql",
            "description": "Generate SQL statements for a table.",
            "subcommands": ["select", "insert", "ddl", "scratch", "task", "udf", "procedure"],
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "-t, --table", "required": True, "help": "Table name."},
            ],
            "example": "qdo sql select -c ./my.db -t users",
        },
        {
            "name": "cache",
            "description": "Manage local metadata cache.",
            "subcommands": ["sync", "status", "clear"],
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {
                    "flag": "--cache-ttl",
                    "required": False,
                    "help": "Cache TTL in seconds (default: 86400). Set 0 to force re-sync.",
                },
            ],
            "example": "qdo cache sync -c my-conn",
        },
        {
            "name": "config",
            "description": "Manage named connections.",
            "subcommands": ["add", "list", "clone", "test"],
        },
        {
            "name": "explore",
            "description": "Interactive TUI for data exploration (requires querido[tui]).",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "-t, --table", "required": True, "help": "Table name."},
            ],
            "requires": "querido[tui]",
        },
        {
            "name": "serve",
            "description": "Launch local web UI for data exploration (requires querido[web]).",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "--port", "required": False, "help": "Port number (default 8888)."},
            ],
            "requires": "querido[web]",
        },
    ]

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
    }

    print(json.dumps(payload, indent=2))
