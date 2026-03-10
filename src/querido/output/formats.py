"""Machine-readable output formatters (markdown, json, csv)."""

from __future__ import annotations

import csv
import io
import json

from querido.output import fmt_value


def to_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a list of rows as a markdown table."""

    def _esc(s: str) -> str:
        return s.replace("|", "\\|")

    lines = []
    lines.append("| " + " | ".join(_esc(h) for h in headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_esc(cell) for cell in row) + " |")
    return "\n".join(lines)


def dicts_to_csv(data: list[dict]) -> str:
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
        return dicts_to_csv(rows)

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
    lines.append(to_markdown_table(headers, rows))
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
        return dicts_to_csv(data)

    # markdown
    headers = list(data[0].keys())
    rows = [[str(v) if v is not None else "" for v in row.values()] for row in data]
    lines = [f"## Preview: {table_name} (limit {limit})", ""]
    lines.append(to_markdown_table(headers, rows))
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
        return dicts_to_csv(data)

    # markdown
    numeric_rows = [r for r in data if r.get("min_val") is not None]
    string_rows = [r for r in data if r.get("min_length") is not None]
    classified = {r["column_name"] for r in numeric_rows} | {r["column_name"] for r in string_rows}
    other_rows = [r for r in data if r["column_name"] not in classified]

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
                    fmt_value(r["min_val"]),
                    fmt_value(r["max_val"]),
                    fmt_value(r["mean_val"]),
                    fmt_value(r["median_val"]),
                    fmt_value(r["stddev_val"]),
                    fmt_value(r["null_count"]),
                    fmt_value(r["null_pct"]),
                    fmt_value(r["distinct_count"]),
                ]
            )
        lines.append(to_markdown_table(headers, rows))
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
                    fmt_value(r["min_length"]),
                    fmt_value(r["max_length"]),
                    fmt_value(r["distinct_count"]),
                    fmt_value(r["null_count"]),
                    fmt_value(r["null_pct"]),
                ]
            )
        lines.append(to_markdown_table(headers, rows))
        lines.append("")

    if other_rows:
        lines.append(f"## Profile: {table_name} — Other Columns")
        lines.append("")
        headers = ["Column", "Type", "Nulls", "Null %", "Distinct"]
        rows = []
        for r in other_rows:
            rows.append(
                [
                    str(r["column_name"]),
                    str(r["column_type"]),
                    fmt_value(r["null_count"]),
                    fmt_value(r["null_pct"]),
                    fmt_value(r["distinct_count"]),
                ]
            )
        lines.append(to_markdown_table(headers, rows))
        lines.append("")

    sample_note = ""
    if sampled and sample_size:
        sample_note = f" (sampled {sample_size:,} rows)"
    lines.append(f"Total rows: {row_count:,}{sample_note}")
    return "\n".join(lines)


# -- search --------------------------------------------------------------------


def format_search(
    pattern: str,
    results: list[dict],
    fmt: str,
) -> str:
    if not results:
        if fmt == "csv":
            return ""
        if fmt == "json":
            return json.dumps({"pattern": pattern, "results": []}, indent=2)
        return f"No matches found for '{pattern}'."

    if fmt == "json":
        return json.dumps({"pattern": pattern, "results": results}, indent=2, default=str)

    if fmt == "csv":
        flat = [
            {
                "table_name": r["table_name"],
                "table_type": r["table_type"],
                "match_type": r["match_type"],
                "column_name": r["column_name"] or "",
                "column_type": r["column_type"] or "",
            }
            for r in results
        ]
        return dicts_to_csv(flat)

    # markdown
    lines = [f"## Search: '{pattern}'", ""]
    headers = ["Table", "Type", "Match", "Column", "Column Type"]
    rows = [
        [
            r["table_name"],
            r["table_type"],
            r["match_type"],
            r["column_name"] or "",
            r["column_type"] or "",
        ]
        for r in results
    ]
    lines.append(to_markdown_table(headers, rows))
    lines.append("")
    lines.append(f"{len(results)} match(es)")
    return "\n".join(lines)


# -- dist ----------------------------------------------------------------------


def format_dist(
    dist_result: dict,
    fmt: str,
) -> str:
    table_name = dist_result["table"]
    column = dist_result["column"]
    mode = dist_result["mode"]
    total_rows = dist_result["total_rows"]
    null_count = dist_result["null_count"]

    if fmt == "json":
        return json.dumps(dist_result, indent=2, default=str)

    if mode == "numeric":
        buckets = dist_result["buckets"]
        if fmt == "csv":
            flat = [
                {
                    "bucket_min": b["bucket_min"],
                    "bucket_max": b["bucket_max"],
                    "count": b["count"],
                }
                for b in buckets
            ]
            return dicts_to_csv(flat) if flat else ""

        # markdown
        lines = [f"## Distribution: {table_name}.{column}", ""]
        headers = ["Bucket", "Count"]
        rows = [
            [f"{fmt_value(b['bucket_min'])} - {fmt_value(b['bucket_max'])}", f"{b['count']:,}"]
            for b in buckets
        ]
        lines.append(to_markdown_table(headers, rows))
        lines.append("")
        null_note = f" (nulls: {null_count:,})" if null_count else ""
        lines.append(f"Total rows: {total_rows:,}{null_note}")
        return "\n".join(lines)
    else:
        values = dist_result["values"]
        if fmt == "csv":
            flat = [
                {
                    "value": v["value"] if v["value"] is not None else "(NULL)",
                    "count": v["count"],
                }
                for v in values
            ]
            return dicts_to_csv(flat) if flat else ""

        # markdown
        lines = [f"## Distribution: {table_name}.{column}", ""]
        headers = ["Value", "Count"]
        rows = [
            [
                str(v["value"]) if v["value"] is not None else "(NULL)",
                f"{v['count']:,}",
            ]
            for v in values
        ]
        lines.append(to_markdown_table(headers, rows))
        lines.append("")
        null_note = f" (nulls: {null_count:,})" if null_count else ""
        lines.append(f"Total rows: {total_rows:,}{null_note}")
        return "\n".join(lines)


# -- template ------------------------------------------------------------------


def yaml_escape(value: str) -> str:
    """Escape a string for safe YAML output."""
    if not value:
        return '""'
    # Quote strings that contain special YAML characters or look like non-strings
    yaml_special = ":{}\n[]#&*!|>',\"@`"
    yaml_keywords = ("true", "false", "null", "yes", "no")
    needs_quoting = any(c in value for c in yaml_special) or value.lower() in yaml_keywords
    if needs_quoting:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        return f'"{escaped}"'
    return value


def _format_template_yaml(template_result: dict) -> str:
    """Render template metadata as a Cortex Analyst-compatible semantic model YAML."""
    table_name = template_result["table"]
    short_name = table_name.rsplit(".", 1)[-1]
    table_comment = template_result["table_comment"]
    row_count = template_result["row_count"]
    columns = template_result["columns"]

    ind = "  "
    lines: list[str] = []

    lines.append(f"name: {short_name.lower()}_semantic_model")
    desc = table_comment or f"Semantic model for {table_name}"
    lines.append(f"description: {yaml_escape(desc)}")
    lines.append("")
    lines.append("tables:")
    lines.append(f"{ind}- name: {short_name}")
    lines.append(f"{ind}  base_table: {table_name}")
    lines.append(f"{ind}  description: {yaml_escape(desc)}")
    lines.append(f"{ind}  row_count: {row_count}")

    dimensions: list[dict] = []
    time_dimensions: list[dict] = []
    measures: list[dict] = []
    from querido.core.profile import classify_column_kind

    for col in columns:
        kind = classify_column_kind(col)
        if kind == "time_dimension":
            time_dimensions.append(col)
        elif kind == "measure":
            measures.append(col)
        else:
            dimensions.append(col)

    def _write_col(col: dict, *, is_measure: bool = False) -> None:
        prefix = ind * 2
        col_desc = col.get("comment") or "<description>"
        lines.append(f"{prefix}- name: {col['name']}")
        lines.append(f"{prefix}  expr: {col['name']}")
        lines.append(f"{prefix}  data_type: {col['type']}")
        lines.append(f"{prefix}  description: {yaml_escape(col_desc)}")
        lines.append(f"{prefix}  synonyms:")
        lines.append(f"{prefix}    - <synonym>")
        if is_measure:
            lines.append(f"{prefix}  default_aggregation: sum")
        if col.get("sample_values"):
            lines.append(f"{prefix}  sample_values: {yaml_escape(col['sample_values'])}")

    if dimensions:
        lines.append(f"\n{ind}  dimensions:")
        for col in dimensions:
            _write_col(col)

    if time_dimensions:
        lines.append(f"\n{ind}  time_dimensions:")
        for col in time_dimensions:
            _write_col(col)

    if measures:
        lines.append(f"\n{ind}  measures:")
        for col in measures:
            _write_col(col, is_measure=True)

    lines.append("")
    return "\n".join(lines)


def format_template(
    template_result: dict,
    fmt: str,
) -> str:
    table_name = template_result["table"]
    table_comment = template_result["table_comment"]
    row_count = template_result["row_count"]
    columns = template_result["columns"]

    if fmt == "json":
        return json.dumps(template_result, indent=2, default=str)

    if fmt == "yaml":
        return _format_template_yaml(template_result)

    if fmt == "csv":
        flat = []
        for col in columns:
            flat.append(
                {
                    "column": col["name"],
                    "type": col["type"],
                    "nullable": "YES" if col["nullable"] else "NO",
                    "distinct_count": fmt_value(col["distinct_count"]),
                    "null_count": fmt_value(col["null_count"]),
                    "null_pct": fmt_value(col["null_pct"]),
                    "min": fmt_value(col["min_val"]) or fmt_value(col["min_length"]),
                    "max": fmt_value(col["max_val"]) or fmt_value(col["max_length"]),
                    "sample_values": col.get("sample_values") or "",
                    "business_definition": "",
                    "data_owner": "",
                    "notes": "",
                }
            )
        return dicts_to_csv(flat) if flat else ""

    # markdown
    lines: list[str] = [f"## {table_name}", ""]
    if table_comment:
        lines.append(f"> {table_comment}")
        lines.append("")
    lines.append(f"Row count: {row_count:,}")
    lines.append("")

    headers = [
        "Column",
        "Type",
        "Nullable",
        "Distinct",
        "Nulls",
        "Min",
        "Max",
        "Sample Values",
        "Business Definition",
        "Data Owner",
        "Notes",
    ]
    rows = []
    for col in columns:
        min_display = fmt_value(col["min_val"]) or fmt_value(col["min_length"])
        max_display = fmt_value(col["max_val"]) or fmt_value(col["max_length"])
        rows.append(
            [
                col["name"],
                col["type"],
                "YES" if col["nullable"] else "NO",
                fmt_value(col["distinct_count"]),
                fmt_value(col["null_count"]),
                min_display,
                max_display,
                col.get("sample_values") or "",
                "",
                "",
                "",
            ]
        )
    lines.append(to_markdown_table(headers, rows))
    return "\n".join(lines)


# -- lineage -------------------------------------------------------------------


def format_lineage(
    lineage_result: dict,
    fmt: str,
) -> str:
    view_name = lineage_result["view"]
    dialect = lineage_result["dialect"]
    definition = lineage_result["definition"]

    if fmt == "json":
        return json.dumps(lineage_result, indent=2, default=str)

    if fmt == "csv":
        return dicts_to_csv([{"view": view_name, "dialect": dialect, "definition": definition}])

    # markdown
    lines = [
        f"## View: {view_name}",
        "",
        f"Dialect: {dialect}",
        "",
        "```sql",
        definition,
        "```",
    ]
    return "\n".join(lines)


# -- snowflake lineage ---------------------------------------------------------


def format_snowflake_lineage(
    lineage_result: dict,
    fmt: str,
) -> str:
    object_name = lineage_result["object"]
    direction = lineage_result["direction"]
    entries = lineage_result["entries"]

    if fmt == "json":
        return json.dumps(lineage_result, indent=2, default=str)

    if not entries:
        if fmt == "csv":
            return ""
        return f"No {direction} lineage found for '{object_name}'."

    if fmt == "csv":
        return dicts_to_csv(entries)

    # markdown
    lines = [f"## Lineage: {object_name} ({direction})", ""]
    headers = list(entries[0].keys())
    rows = [[str(v) if v is not None else "" for v in row.values()] for row in entries]
    lines.append(to_markdown_table(headers, rows))
    lines.append("")
    lines.append(f"{len(entries)} lineage entries")
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
        return dicts_to_csv(flat) if flat else ""

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
        lines.append(to_markdown_table(headers, md_rows))
        lines.append("")
    return "\n".join(lines)
