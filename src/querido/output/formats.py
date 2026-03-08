"""Machine-readable output formatters (markdown, json, csv)."""

from __future__ import annotations

import csv
import io
import json

from querido.output import _fmt


def _to_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a list of rows as a markdown table."""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _dicts_to_csv(data: list[dict]) -> str:
    """Render a list of dicts as CSV."""
    if not data:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(data[0].keys()))
    writer.writeheader()
    writer.writerows(data)
    return buf.getvalue().rstrip("\n")


# -- inspect ------------------------------------------------------------------


def format_inspect(
    table_name: str,
    columns: list[dict],
    row_count: int,
    fmt: str,
    verbose: bool = False,
    table_comment: str | None = None,
) -> str:
    if fmt == "json":
        payload: dict = {"table": table_name, "row_count": row_count, "columns": columns}
        if verbose and table_comment:
            payload["table_comment"] = table_comment
        return json.dumps(payload, indent=2, default=str)

    if fmt == "csv":
        rows = []
        for col in columns:
            row: dict = {
                "column": col["name"],
                "type": col["type"],
                "nullable": "YES" if col["nullable"] else "NO",
                "default": str(col["default"]) if col["default"] is not None else "",
                "primary_key": "PK" if col.get("primary_key") else "",
            }
            if verbose:
                row["comment"] = col.get("comment") or ""
            rows.append(row)
        return _dicts_to_csv(rows)

    # markdown
    headers = ["Column", "Type", "Nullable", "Default", "Primary Key"]
    if verbose:
        headers.append("Comment")
    rows = []
    for col in columns:
        row_data = [
            col["name"],
            col["type"],
            "YES" if col["nullable"] else "NO",
            str(col["default"]) if col["default"] is not None else "",
            "PK" if col.get("primary_key") else "",
        ]
        if verbose:
            row_data.append(col.get("comment") or "")
        rows.append(row_data)
    lines = [f"## {table_name}", ""]
    if table_comment:
        lines.append(f"> {table_comment}")
        lines.append("")
    lines.append(_to_markdown_table(headers, rows))
    lines.append("")
    lines.append(f"Row count: {row_count:,}")
    return "\n".join(lines)


# -- preview ------------------------------------------------------------------


def format_preview(
    table_name: str,
    data: list[dict],
    limit: int,
    fmt: str,
) -> str:
    if not data:
        return "" if fmt == "csv" else "No rows found."

    if fmt == "json":
        return json.dumps(data, indent=2, default=str)

    if fmt == "csv":
        return _dicts_to_csv(data)

    # markdown
    headers = list(data[0].keys())
    rows = [[str(v) if v is not None else "" for v in row.values()] for row in data]
    lines = [f"## Preview: {table_name} (limit {limit})", ""]
    lines.append(_to_markdown_table(headers, rows))
    lines.append("")
    lines.append(f"Showing {len(data)} row(s)")
    return "\n".join(lines)


# -- profile ------------------------------------------------------------------


def format_profile(
    table_name: str,
    data: list[dict],
    row_count: int,
    sampled: bool,
    sample_size: int | None,
    fmt: str,
) -> str:
    if not data:
        return "" if fmt == "csv" else "No columns to profile."

    if fmt == "json":
        payload: dict = {
            "table": table_name,
            "row_count": row_count,
            "sampled": sampled,
            "columns": data,
        }
        if sampled and sample_size:
            payload["sample_size"] = sample_size
        return json.dumps(payload, indent=2, default=str)

    if fmt == "csv":
        return _dicts_to_csv(data)

    # markdown
    numeric_rows = [r for r in data if r.get("min_val") is not None]
    string_rows = [r for r in data if r.get("min_length") is not None]

    lines: list[str] = []

    if numeric_rows:
        lines.append(f"## Profile: {table_name} — Numeric Columns")
        lines.append("")
        headers = [
            "Column",
            "Type",
            "Min",
            "Max",
            "Mean",
            "Median",
            "Stddev",
            "Nulls",
            "Null %",
            "Distinct",
        ]
        rows = []
        for r in numeric_rows:
            rows.append(
                [
                    str(r["column_name"]),
                    str(r["column_type"]),
                    _fmt(r["min_val"]),
                    _fmt(r["max_val"]),
                    _fmt(r["mean_val"]),
                    _fmt(r["median_val"]),
                    _fmt(r["stddev_val"]),
                    _fmt(r["null_count"]),
                    _fmt(r["null_pct"]),
                    _fmt(r["distinct_count"]),
                ]
            )
        lines.append(_to_markdown_table(headers, rows))
        lines.append("")

    if string_rows:
        lines.append(f"## Profile: {table_name} — String Columns")
        lines.append("")
        headers = ["Column", "Type", "Min Len", "Max Len", "Distinct", "Nulls", "Null %"]
        rows = []
        for r in string_rows:
            rows.append(
                [
                    str(r["column_name"]),
                    str(r["column_type"]),
                    _fmt(r["min_length"]),
                    _fmt(r["max_length"]),
                    _fmt(r["distinct_count"]),
                    _fmt(r["null_count"]),
                    _fmt(r["null_pct"]),
                ]
            )
        lines.append(_to_markdown_table(headers, rows))
        lines.append("")

    sample_note = ""
    if sampled and sample_size:
        sample_note = f" (sampled {sample_size:,} rows)"
    lines.append(f"Total rows: {row_count:,}{sample_note}")
    return "\n".join(lines)


# -- frequencies ---------------------------------------------------------------


def format_frequencies(
    table_name: str,
    freq_data: dict[str, list[dict]],
    row_count: int,
    fmt: str,
) -> str:
    if fmt == "json":
        return json.dumps(
            {"table": table_name, "row_count": row_count, "frequencies": freq_data},
            indent=2,
            default=str,
        )

    if fmt == "csv":
        flat: list[dict] = []
        for col_name, rows in freq_data.items():
            for r in rows:
                pct = round(100.0 * r["count"] / row_count, 2) if row_count else 0
                flat.append(
                    {"column": col_name, "value": r["value"], "count": r["count"], "pct": pct}
                )
        return _dicts_to_csv(flat) if flat else ""

    # markdown
    lines: list[str] = []
    for col_name, rows in freq_data.items():
        if not rows:
            continue
        lines.append(f"### Top values: {table_name}.{col_name}")
        lines.append("")
        headers = ["Value", "Count", "%"]
        md_rows = []
        for r in rows:
            pct = round(100.0 * r["count"] / row_count, 2) if row_count else 0
            val = str(r["value"]) if r["value"] is not None else "(NULL)"
            md_rows.append([val, f"{r['count']:,}", str(pct)])
        lines.append(_to_markdown_table(headers, md_rows))
        lines.append("")
    return "\n".join(lines)
