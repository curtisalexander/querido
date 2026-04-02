from pathlib import Path

import typer

app = typer.Typer(help="Print CLI overview (markdown).")


@app.callback(invoke_without_command=True)
def overview() -> None:
    """Print the full CLI reference as markdown.

    Useful for piping into an LLM or pager:

        qdo overview | less
        qdo overview | pbcopy
    """
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
