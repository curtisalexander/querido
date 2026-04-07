"""Export table or query results to a file."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from querido.connectors.base import Connector


def export_data(
    connector: Connector,
    *,
    table: str | None = None,
    sql: str | None = None,
    output_path: str | None = None,
    fmt: str = "csv",
    limit: int | None = None,
    filter_expr: str | None = None,
    columns: list[str] | None = None,
) -> dict:
    """Export data to a file or return content as a string.

    Provide either *table* or *sql* (not both).

    Returns::

        {
            "path": str | None,
            "rows": int,
            "format": str,
            "size_bytes": int,
            "content": str | None,  # set when output_path is None (clipboard)
        }
    """
    query_sql = _build_query(connector, table=table, sql=sql,
                             limit=limit, filter_expr=filter_expr,
                             columns=columns)

    data = connector.execute(query_sql)
    content = _format_data(data, fmt)

    if output_path:
        path = Path(output_path)
        path.write_text(content, encoding="utf-8")
        size_bytes = path.stat().st_size
    else:
        size_bytes = len(content.encode("utf-8"))

    return {
        "path": output_path,
        "rows": len(data),
        "format": fmt,
        "size_bytes": size_bytes,
        "content": content if output_path is None else None,
    }


def _build_query(
    connector: Connector,
    *,
    table: str | None,
    sql: str | None,
    limit: int | None,
    filter_expr: str | None,
    columns: list[str] | None,
) -> str:
    """Build the SQL query for the export."""
    if sql:
        base = sql.rstrip().rstrip(";")
        if limit:
            return f"select * from ({base}) as _q limit {limit}"
        return base

    if not table:
        raise ValueError("Either --table or --sql must be provided.")

    from querido.connectors.base import validate_column_name, validate_table_name

    validate_table_name(table)

    def _q(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    if columns:
        for c in columns:
            validate_column_name(c)
        col_list = ", ".join(_q(c) for c in columns)
    else:
        col_list = "*"

    parts = [f"select {col_list} from {_q(table)}"]

    if filter_expr:
        parts.append(f"where {filter_expr}")

    if limit:
        parts.append(f"limit {limit}")

    return " ".join(parts)


def _format_data(data: list[dict], fmt: str) -> str:
    """Format row data as a string in the requested format."""
    if not data:
        if fmt == "json":
            return "[]"
        if fmt == "jsonl":
            return ""
        return ""

    if fmt == "csv":
        return _to_delimited(data, delimiter=",")

    if fmt == "tsv":
        return _to_delimited(data, delimiter="\t")

    if fmt == "json":
        return json.dumps(data, indent=2, default=str)

    if fmt == "jsonl":
        lines = [json.dumps(row, default=str) for row in data]
        return "\n".join(lines)

    raise ValueError(f"Unsupported export format: {fmt!r}")


def _to_delimited(data: list[dict], *, delimiter: str) -> str:
    """Write rows as delimiter-separated text."""
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=list(data[0].keys()), delimiter=delimiter,
    )
    writer.writeheader()
    writer.writerows(data)
    return buf.getvalue()


def copy_to_clipboard(content: str) -> None:
    """Copy *content* to the system clipboard.

    Uses pbcopy (macOS), xclip (Linux), or clip (Windows).
    Raises RuntimeError if no clipboard tool is available.
    """
    import platform
    import subprocess

    system = platform.system()
    if system == "Darwin":
        cmd = ["pbcopy"]
    elif system == "Linux":
        cmd = ["xclip", "-selection", "clipboard"]
    elif system == "Windows":
        cmd = ["clip"]
    else:
        raise RuntimeError(f"Clipboard not supported on {system}")

    try:
        subprocess.run(
            cmd, input=content, text=True, check=True,
            capture_output=True, timeout=5,
        )
    except FileNotFoundError:
        raise RuntimeError(
            f"Clipboard tool not found: {cmd[0]}. "
            f"Install it or use --output to write to a file."
        ) from None
