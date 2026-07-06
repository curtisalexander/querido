"""CLI context helpers — output format, SQL display, HTML emission."""

from __future__ import annotations

from querido._runtime import _get_root_obj
from querido._runtime import get_output_format as get_output_format


def emit_html(html_content: str, prefix: str = "qdo-") -> None:
    """Write *html_content* to a temp file, open it in the browser, and print the path."""
    from querido.output.html import open_html

    path = open_html(html_content, prefix=prefix)
    import sys

    print(f"Opened {path}", file=sys.stderr)


def maybe_show_sql(sql: str) -> None:
    """Print SQL to stderr if --show-sql was passed."""
    if not _get_root_obj().get("show_sql"):
        return

    print_sql(sql)


def print_sql(sql: str) -> None:
    """Print SQL to stderr with syntax highlighting."""
    from rich.console import Console
    from rich.syntax import Syntax

    console = Console(stderr=True)
    console.print()
    console.print(Syntax(sql.strip(), "sql", theme="monokai", line_numbers=False))
    console.print()
