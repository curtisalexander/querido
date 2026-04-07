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
| `query -c CONN --sql "SQL" [--limit N]` | Execute ad-hoc SQL |
| `catalog -c CONN [--tables-only]` | Full database catalog |
| `values -c CONN -t TABLE -C COLUMN` | Distinct values for a column |
| `pivot -c CONN -t TABLE -g COL -a "sum(col)"` | Aggregate with GROUP BY |
| `assert -c CONN --sql "SQL" --expect N` | Assert query result (exit 0/1) |
| `quality -c CONN -t TABLE` | Data quality summary (nulls, uniqueness) |
| `joins -c CONN -t TABLE [--target T]` | Discover join keys between tables |
| `diff -c CONN -t A --target B` | Compare schemas between tables |
| `explain -c CONN --sql "SQL" [--analyze]` | Show query execution plan |
| `export -c CONN -t TABLE -o file.csv` | Export to file (csv/tsv/json/jsonl) |
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
`--debug`        : Enable debug logging to stderr
`--version`, `-V`: Show version

## Agent Mode

Set `QDO_FORMAT=json` in your environment to get structured JSON from all
commands by default. Explicit `--format` always takes priority.

```bash
export QDO_FORMAT=json
qdo catalog -c mydb              # JSON schema
qdo query -c mydb --sql "..."    # JSON results
```

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
            "name": "query",
            "description": "Execute ad-hoc SQL and display results.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {
                    "flag": "-s, --sql",
                    "required": False,
                    "help": "SQL query string (alternative: --file or stdin).",
                },
                {
                    "flag": "-F, --file",
                    "required": False,
                    "help": "Path to a .sql file to execute.",
                },
                {
                    "flag": "-l, --limit",
                    "required": False,
                    "help": "Max rows to return (default 1000, 0 = no limit).",
                },
            ],
            "example": 'qdo query -c ./my.db --sql "select * from users"',
            "output_shape": {
                "columns": ["string"],
                "row_count": "integer",
                "limited": "boolean",
                "rows": [{"column_name": "value"}],
            },
        },
        {
            "name": "catalog",
            "description": "Show full database catalog — all tables, columns, row counts.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {
                    "flag": "--tables-only",
                    "required": False,
                    "help": "List tables only (skip columns and row counts).",
                },
                {
                    "flag": "--live",
                    "required": False,
                    "help": "Bypass cache and query the database directly.",
                },
            ],
            "example": "qdo catalog -c ./my.db -f json",
            "output_shape": {
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
        },
        {
            "name": "values",
            "description": "Show all distinct values for a column (with counts).",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "-t, --table", "required": True, "help": "Table name."},
                {"flag": "-C, --column", "required": True, "help": "Column to enumerate."},
                {
                    "flag": "-m, --max",
                    "required": False,
                    "help": "Max distinct values (default 1000).",
                },
                {
                    "flag": "-s, --sort",
                    "required": False,
                    "help": "Sort: value (alphabetical) or frequency (count desc).",
                },
            ],
            "example": "qdo values -c ./my.db -t users -C status -f json",
            "output_shape": {
                "table": "string",
                "column": "string",
                "distinct_count": "integer",
                "total_rows": "integer",
                "null_count": "integer",
                "truncated": "boolean",
                "values": [{"value": "any", "count": "integer"}],
            },
        },
        {
            "name": "pivot",
            "description": "Aggregate data with GROUP BY.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {
                    "flag": "-t, --table",
                    "required": True,
                    "help": "Table name.",
                },
                {
                    "flag": "-g, --group-by",
                    "required": True,
                    "help": "Comma-separated columns to group by.",
                },
                {
                    "flag": "-a, --agg",
                    "required": True,
                    "help": "Aggregation expressions, e.g. sum(amount).",
                },
                {
                    "flag": "-w, --filter",
                    "required": False,
                    "help": "SQL WHERE clause expression.",
                },
                {
                    "flag": "-o, --order-by",
                    "required": False,
                    "help": "SQL ORDER BY (default: group-by columns).",
                },
                {
                    "flag": "-l, --limit",
                    "required": False,
                    "help": "Maximum result rows.",
                },
            ],
            "example": (
                'qdo pivot -c ./my.db -t orders -g region'
                ' -a "sum(amount)" -f json'
            ),
            "output_shape": {
                "headers": ["string"],
                "rows": [{"column_name": "value"}],
                "row_count": "integer",
                "sql": "string",
            },
        },
        {
            "name": "assert",
            "description": "Assert a SQL query result meets a condition. Exit 0=pass, 1=fail.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {
                    "flag": "-s, --sql",
                    "required": False,
                    "help": "SQL query (alternative: --file or stdin).",
                },
                {"flag": "--expect", "required": False, "help": "Assert result == value."},
                {"flag": "--expect-gt", "required": False, "help": "Assert result > value."},
                {"flag": "--expect-lt", "required": False, "help": "Assert result < value."},
                {"flag": "--expect-gte", "required": False, "help": "Assert result >= value."},
                {"flag": "--expect-lte", "required": False, "help": "Assert result <= value."},
                {"flag": "-n, --name", "required": False, "help": "Descriptive name."},
                {"flag": "-q, --quiet", "required": False, "help": "No output, just exit code."},
            ],
            "example": 'qdo assert -c ./my.db --sql "select count(*) from users" --expect 100',
            "output_shape": {
                "passed": "boolean",
                "actual": "number",
                "expected": "number",
                "operator": "eq|gt|lt|gte|lte",
                "name": "string|null",
                "sql": "string",
            },
        },
        {
            "name": "quality",
            "description": "Data quality summary — nulls, uniqueness, issues per column.",
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
                    "help": "Comma-separated columns to check (default: all).",
                },
                {
                    "flag": "--check-duplicates",
                    "required": False,
                    "help": "Check for fully duplicate rows.",
                },
            ],
            "example": "qdo quality -c ./my.db -t users -f json",
            "output_shape": {
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
        },
        {
            "name": "joins",
            "description": "Discover likely join keys between tables.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "-t, --table", "required": True, "help": "Source table."},
                {
                    "flag": "--target",
                    "required": False,
                    "help": "Target table (default: all tables).",
                },
            ],
            "example": "qdo joins -c ./my.db -t orders -f json",
            "output_shape": {
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
        },
        {
            "name": "diff",
            "description": "Compare column schemas between two tables.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "-t, --table", "required": True, "help": "Left table."},
                {"flag": "--target", "required": True, "help": "Right table."},
                {
                    "flag": "--target-connection",
                    "required": False,
                    "help": "Connection for right table (cross-connection diff).",
                },
            ],
            "example": "qdo diff -c ./my.db -t users_v1 --target users_v2 -f json",
            "output_shape": {
                "left": "string",
                "right": "string",
                "added": [{"name": "string", "type": "string", "nullable": "boolean"}],
                "removed": [{"name": "string", "type": "string", "nullable": "boolean"}],
                "changed": [
                    {
                        "name": "string",
                        "left_type": "string",
                        "right_type": "string",
                    }
                ],
                "unchanged_count": "integer",
            },
        },
        {
            "name": "explain",
            "description": "Show query execution plan (EXPLAIN).",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {
                    "flag": "-s, --sql",
                    "required": False,
                    "help": "SQL query (alternative: --file or stdin).",
                },
                {
                    "flag": "--analyze",
                    "required": False,
                    "help": "Run EXPLAIN ANALYZE (DuckDB).",
                },
            ],
            "example": 'qdo explain -c ./my.db --sql "select * from users" -f json',
            "output_shape": {
                "plan": "string",
                "sql": "string",
                "dialect": "string",
                "analyzed": "boolean",
            },
        },
        {
            "name": "export",
            "description": "Export data to a file or clipboard.",
            "options": [
                {
                    "flag": "-c, --connection",
                    "required": True,
                    "help": "Named connection or file path.",
                },
                {"flag": "-t, --table", "required": False, "help": "Table to export."},
                {"flag": "-s, --sql", "required": False, "help": "SQL query to export."},
                {"flag": "-o, --output", "required": False, "help": "Output file path."},
                {
                    "flag": "-e, --export-format",
                    "required": False,
                    "help": "Format: csv, tsv, json, jsonl (default csv).",
                },
                {"flag": "--clipboard", "required": False, "help": "Copy TSV to clipboard."},
                {"flag": "-w, --filter", "required": False, "help": "WHERE clause."},
                {"flag": "-l, --limit", "required": False, "help": "Max rows."},
                {"flag": "--columns", "required": False, "help": "Columns to export."},
            ],
            "example": "qdo export -c ./my.db -t users -o users.csv",
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
                "qdo query -c <conn> --sql '...'  # ad-hoc queries",
                "qdo values -c <conn> -t <table> -C <col>  # distinct values",
                "qdo pivot -c <conn> -t <table> -g <col> -a 'sum(col)'",
            ],
        },
    }

    print(json.dumps(payload, indent=2))
