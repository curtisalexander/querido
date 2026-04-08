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

    lines = [
        "| " + " | ".join(_esc(h) for h in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(_esc(cell) for cell in row) + " |" for row in rows)
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
        payload: dict = {
            "table": table_name,
            "limit": limit,
            "row_count": len(data),
            "rows": data,
        }
        return json.dumps(payload, indent=2, default=str)

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
        rows = [
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
            for r in numeric_rows
        ]
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
    from querido.core.semantic import build_semantic_yaml

    columns = template_result["columns"]

    # Build per-column sample values dict from the comma-separated strings.
    sample_values_per_col: dict[str, list[str]] = {}
    for col in columns:
        sv = col.get("sample_values", "")
        if sv:
            sample_values_per_col[col["name"]] = [v.strip() for v in sv.split(",") if v.strip()]

    return build_semantic_yaml(
        template_result["table"],
        columns,
        template_result["table_comment"] or None,
        sample_values_per_col=sample_values_per_col,
    )


def format_template(
    template_result: dict,
    fmt: str,
    *,
    style: str = "table",
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
        flat = [
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
            for col in columns
        ]
        return dicts_to_csv(flat) if flat else ""

    # markdown
    if style == "detailed":
        return _format_template_markdown_detailed(table_name, table_comment, row_count, columns)
    return _format_template_markdown_table(table_name, table_comment, row_count, columns)


def _format_template_markdown_table(
    table_name: str, table_comment: str, row_count: int, columns: list[dict]
) -> str:
    """Flat markdown table (default style)."""
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


def _format_template_markdown_detailed(
    table_name: str, table_comment: str, row_count: int, columns: list[dict]
) -> str:
    """Per-column section markdown (detailed style)."""
    pk_cols = [c["name"] for c in columns if c.get("primary_key")]
    lines: list[str] = [f"## {table_name}", ""]

    summary_parts = [f"**Row count**: {row_count:,}", f"**Columns**: {len(columns)}"]
    if pk_cols:
        summary_parts.append(f"**Primary keys**: {', '.join(pk_cols)}")
    lines.append(" | ".join(summary_parts))
    lines.append("")

    if table_comment:
        lines.append(f"> {table_comment}")
        lines.append("")

    lines.append("---")

    for col in columns:
        name = col["name"]
        col_type = col["type"]
        nullable = col["nullable"]
        is_pk = col.get("primary_key", False)

        # Header line: ### `name` — TYPE (flags)
        flags = []
        if not nullable:
            flags.append("non-nullable")
        if is_pk:
            flags.append("primary key")
        flag_str = f" ({', '.join(flags)})" if flags else ""
        lines.append("")
        lines.append(f"### `{name}` — {col_type}{flag_str}")

        # Stats
        distinct = col.get("distinct_count")
        null_count = col.get("null_count")
        null_pct = col.get("null_pct")

        stat_parts = []
        if distinct is not None:
            stat_parts.append(f"**Distinct values**: {fmt_value(distinct)}")
        if null_count is not None and null_count > 0:
            pct_str = f" ({null_pct}%)" if null_pct else ""
            stat_parts.append(f"**Nulls**: {fmt_value(null_count)}{pct_str}")
        if stat_parts:
            lines.append(f"- {' | '.join(stat_parts)}")

        # Range or length
        min_val = col.get("min_val")
        max_val = col.get("max_val")
        min_len = col.get("min_length")
        max_len = col.get("max_length")
        if min_val is not None and max_val is not None:
            lines.append(f"- **Range**: {fmt_value(min_val)} - {fmt_value(max_val)}")
        elif min_len is not None and max_len is not None:
            lines.append(f"- **Length range**: {fmt_value(min_len)} - {fmt_value(max_len)}")

        # Samples
        samples = col.get("sample_values", "")
        if samples:
            lines.append(f"- **Samples**: {samples}")

        # Comment from database
        comment = col.get("comment", "")
        if comment:
            lines.append(f"- **Comment**: {comment}")

        # Placeholder fields
        lines.append("- **Business definition**: _fill in_")
        lines.append("- **Data owner**: _fill in_")
        lines.append("- **Notes**: _fill in_")

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


# -- metadata -----------------------------------------------------------------


def format_metadata(
    meta: dict,
    fmt: str,
) -> str:
    if fmt == "json":
        return json.dumps(meta, indent=2, default=str)

    if fmt == "csv":
        columns = meta.get("columns", [])
        if not columns:
            return ""
        flat = [
            {
                "name": c.get("name", ""),
                "type": c.get("type", ""),
                "description": c.get("description", ""),
                "nullable": c.get("nullable", False),
                "null_count": c.get("null_count", ""),
                "distinct_count": c.get("distinct_count", ""),
            }
            for c in columns
        ]
        return dicts_to_csv(flat)

    # markdown
    lines = [f"## {meta.get('table', '')}"]
    desc = meta.get("table_description", "")
    if desc and not str(desc).startswith("<"):
        lines.append(f"\n{desc}")
    lines.append(f"\nRow count: {meta.get('row_count', 0):,}")
    lines.append("")
    columns = meta.get("columns", [])
    if columns:
        headers = ["Name", "Type", "Description", "Nulls", "Distinct"]
        rows = [
            [
                c.get("name", ""),
                c.get("type", ""),
                c.get("description", ""),
                str(c.get("null_count", "")),
                str(c.get("distinct_count", "")),
            ]
            for c in columns
        ]
        lines.append(to_markdown_table(headers, rows))
    return "\n".join(lines)


def format_metadata_list(
    connection: str,
    entries: list[dict],
    fmt: str,
) -> str:
    if not entries:
        if fmt == "csv":
            return ""
        if fmt == "json":
            return json.dumps({"connection": connection, "tables": []})
        return f"No metadata stored for {connection}."

    if fmt == "json":
        return json.dumps(
            {"connection": connection, "tables": entries},
            indent=2,
            default=str,
        )

    if fmt == "csv":
        return dicts_to_csv(entries)

    # markdown
    lines = [f"## Metadata: {connection}", ""]
    headers = ["Table", "Completeness", "Path"]
    rows = [
        [
            e.get("table", ""),
            f"{e.get('completeness', 0):.0f}%",
            e.get("path", ""),
        ]
        for e in entries
    ]
    lines.append(to_markdown_table(headers, rows))
    return "\n".join(lines)


# -- explain ------------------------------------------------------------------


def format_explain(
    result: dict,
    fmt: str,
) -> str:
    if fmt == "json":
        return json.dumps(result, indent=2, default=str)

    if fmt == "csv":
        return result.get("plan", "")

    # markdown
    plan = result.get("plan", "")
    dialect = result.get("dialect", "")
    analyzed = " (ANALYZE)" if result.get("analyzed") else ""
    lines = [
        f"## Query Plan — {dialect}{analyzed}",
        "",
        "```",
        plan,
        "```",
    ]
    return "\n".join(lines)


# -- diff ---------------------------------------------------------------------


def format_diff(
    result: dict,
    fmt: str,
) -> str:
    if fmt == "json":
        return json.dumps(result, indent=2, default=str)

    added = result["added"]
    removed = result["removed"]
    changed = result["changed"]

    if fmt == "csv":
        flat = [
            *[
                {
                    "change": "added",
                    "column": c["name"],
                    "left_type": "",
                    "right_type": c["type"],
                    "left_nullable": "",
                    "right_nullable": c["nullable"],
                }
                for c in added
            ],
            *[
                {
                    "change": "removed",
                    "column": c["name"],
                    "left_type": c["type"],
                    "right_type": "",
                    "left_nullable": c["nullable"],
                    "right_nullable": "",
                }
                for c in removed
            ],
            *[
                {
                    "change": "changed",
                    "column": c["name"],
                    "left_type": c["left_type"],
                    "right_type": c["right_type"],
                    "left_nullable": c["left_nullable"],
                    "right_nullable": c["right_nullable"],
                }
                for c in changed
            ],
        ]
        if not flat:
            return ""
        return dicts_to_csv(flat)

    # markdown
    lines = [
        f"## Diff: {result['left']} → {result['right']}",
        "",
    ]
    if not added and not removed and not changed:
        lines.append("Schemas are identical.")
        return "\n".join(lines)

    if added:
        lines.append("### Added (in right only)")
        lines.append("")
        headers = ["Column", "Type", "Nullable"]
        rows = [[c["name"], c["type"], "YES" if c["nullable"] else "NO"] for c in added]
        lines.append(to_markdown_table(headers, rows))
        lines.append("")

    if removed:
        lines.append("### Removed (in left only)")
        lines.append("")
        headers = ["Column", "Type", "Nullable"]
        rows = [[c["name"], c["type"], "YES" if c["nullable"] else "NO"] for c in removed]
        lines.append(to_markdown_table(headers, rows))
        lines.append("")

    if changed:
        lines.append("### Changed")
        lines.append("")
        headers = [
            "Column",
            "Left Type",
            "Right Type",
            "Left Nullable",
            "Right Nullable",
        ]
        rows = [
            [
                c["name"],
                c["left_type"],
                c["right_type"],
                "YES" if c["left_nullable"] else "NO",
                "YES" if c["right_nullable"] else "NO",
            ]
            for c in changed
        ]
        lines.append(to_markdown_table(headers, rows))
        lines.append("")

    lines.append(f"{result['unchanged_count']} unchanged column(s)")
    return "\n".join(lines)


# -- joins --------------------------------------------------------------------


def format_joins(
    result: dict,
    fmt: str,
) -> str:
    candidates = result["candidates"]

    if fmt == "json":
        return json.dumps(result, indent=2, default=str)

    if fmt == "csv":
        flat = [
            {
                "source_table": result["source"],
                "target_table": cand["target_table"],
                "source_col": key["source_col"],
                "target_col": key["target_col"],
                "match_type": key["match_type"],
                "confidence": key["confidence"],
            }
            for cand in candidates
            for key in cand["join_keys"]
        ]
        return dicts_to_csv(flat)

    # markdown
    lines = [f"## Join candidates for {result['source']}", ""]
    headers = [
        "Target",
        "Source Col",
        "Target Col",
        "Match",
        "Confidence",
    ]
    rows = [
        [
            cand["target_table"],
            key["source_col"],
            key["target_col"],
            key["match_type"],
            f"{key['confidence']:.0%}",
        ]
        for cand in candidates
        for key in cand["join_keys"]
    ]
    lines.append(to_markdown_table(headers, rows))
    return "\n".join(lines)


# -- quality ------------------------------------------------------------------


def format_quality(
    result: dict,
    fmt: str,
) -> str:
    columns = result["columns"]
    if not columns:
        return "" if fmt == "csv" else "No columns to check."

    if fmt == "json":
        return json.dumps(result, indent=2, default=str)

    if fmt == "csv":
        flat = [
            {
                "column": col["name"],
                "type": col["type"],
                "null_count": col["null_count"],
                "null_pct": col["null_pct"],
                "distinct_count": col["distinct_count"],
                "uniqueness_pct": col["uniqueness_pct"],
                "min": col["min"],
                "max": col["max"],
                "status": col["status"],
                "issues": "; ".join(col["issues"]),
            }
            for col in columns
        ]
        return dicts_to_csv(flat)

    # markdown
    lines = [
        f"## Quality: {result['table']} ({result['row_count']:,} rows)",
        "",
    ]
    headers = [
        "Column",
        "Type",
        "Nulls",
        "Null %",
        "Distinct",
        "Unique %",
        "Status",
        "Issues",
    ]
    rows = [
        [
            col["name"],
            col["type"],
            f"{col['null_count']:,}",
            f"{col['null_pct']}%",
            f"{col['distinct_count']:,}",
            f"{col['uniqueness_pct']}%",
            col["status"],
            "; ".join(col["issues"]),
        ]
        for col in columns
    ]
    lines.append(to_markdown_table(headers, rows))

    if result["duplicate_rows"] is not None:
        lines.append("")
        dup = result["duplicate_rows"]
        lines.append(f"Duplicate rows: {dup:,}" if dup > 0 else "No duplicate rows")

    return "\n".join(lines)


# -- assert_check -------------------------------------------------------------


def format_assert_check(
    result: dict,
    fmt: str,
) -> str:
    if fmt == "json":
        return json.dumps(result, indent=2, default=str)

    if fmt == "csv":
        return dicts_to_csv([result])

    # markdown
    status = "PASSED" if result["passed"] else "FAILED"
    op_labels = {"eq": "==", "gt": ">", "lt": "<", "gte": ">=", "lte": "<="}
    op_sym = op_labels.get(result["operator"], result["operator"])
    name = result.get("name") or "Assertion"
    lines = [
        f"## {name}: {status}",
        "",
        f"- actual: {result['actual']}",
        f"- expected: {op_sym} {result['expected']}",
    ]
    return "\n".join(lines)


# -- pivot --------------------------------------------------------------------


def format_pivot(
    result: dict,
    fmt: str,
) -> str:
    rows = result["rows"]
    if not rows:
        return "" if fmt == "csv" else "Pivot returned no rows."

    if fmt == "json":
        return json.dumps(result, indent=2, default=str)

    if fmt == "csv":
        return dicts_to_csv(rows)

    # markdown
    headers = result["headers"]
    md_rows = [[str(v) if v is not None else "" for v in row.values()] for row in rows]
    lines = [f"## Pivot Results ({result['row_count']} groups)", ""]
    lines.append(to_markdown_table(headers, md_rows))
    lines.append("")
    lines.append(f"{result['row_count']} group(s)")
    return "\n".join(lines)


# -- values -------------------------------------------------------------------


def format_values(
    result: dict,
    fmt: str,
) -> str:
    values = result["values"]
    if not values:
        return "" if fmt == "csv" else "No values found."

    if fmt == "json":
        return json.dumps(result, indent=2, default=str)

    if fmt == "csv":
        return dicts_to_csv(values)

    # markdown
    col = result["column"]
    tbl = result["table"]
    truncated = result["truncated"]
    header = f"## Values: {tbl}.{col}"
    if truncated:
        header += f" (top {len(values)} of {result['distinct_count']:,})"

    lines = [header, ""]
    headers = ["Value", "Count"]
    rows = [
        [str(v["value"]) if v["value"] is not None else "(NULL)", f"{v['count']:,}"]
        for v in values
    ]
    lines.append(to_markdown_table(headers, rows))
    lines.append("")
    lines.append(f"{result['distinct_count']:,} distinct values, {result['null_count']:,} nulls")
    return "\n".join(lines)


# -- catalog ------------------------------------------------------------------


def format_catalog(
    catalog: dict,
    fmt: str,
) -> str:
    tables = catalog["tables"]
    if not tables:
        return "" if fmt == "csv" else "No tables found."

    if fmt == "json":
        return json.dumps(catalog, indent=2, default=str)

    if fmt == "csv":
        flat: list[dict] = []
        for t in tables:
            row_ct = t["row_count"] if t["row_count"] is not None else ""
            if t["columns"]:
                flat.extend(
                    {
                        "table": t["name"],
                        "table_type": t["type"],
                        "row_count": row_ct,
                        "column": c["name"],
                        "column_type": c["type"],
                        "nullable": c["nullable"],
                        "comment": c.get("comment", ""),
                    }
                    for c in t["columns"]
                )
            else:
                flat.append(
                    {
                        "table": t["name"],
                        "table_type": t["type"],
                        "row_count": row_ct,
                        "column": "",
                        "column_type": "",
                        "nullable": "",
                        "comment": "",
                    }
                )
        return dicts_to_csv(flat) if flat else ""

    # markdown
    lines = [f"## Catalog ({catalog['table_count']} tables)", ""]

    for t in tables:
        row_str = f"{t['row_count']:,}" if t["row_count"] is not None else "N/A"
        lines.append(f"### {t['name']} ({t['type']}, {row_str} rows)")
        lines.append("")
        if t["columns"]:
            headers = ["Column", "Type", "Nullable", "Comment"]
            rows = [
                [c["name"], c["type"], "YES" if c["nullable"] else "NO", c.get("comment", "")]
                for c in t["columns"]
            ]
            lines.append(to_markdown_table(headers, rows))
            lines.append("")

    return "\n".join(lines)


# -- query --------------------------------------------------------------------


def format_query(
    columns: list[str],
    rows: list[dict],
    row_count: int,
    fmt: str,
    *,
    limited: bool = False,
    sql: str = "",
) -> str:
    if not rows:
        return "" if fmt == "csv" else "Query returned no rows."

    if fmt == "json":
        payload: dict = {
            "columns": columns,
            "row_count": row_count,
            "limited": limited,
            "rows": rows,
        }
        return json.dumps(payload, indent=2, default=str)

    if fmt == "csv":
        return dicts_to_csv(rows)

    # markdown
    headers = list(rows[0].keys())
    md_rows = [[str(v) if v is not None else "" for v in row.values()] for row in rows]
    suffix = " (limit reached)" if limited else ""
    lines = [f"## Query Results ({row_count} rows{suffix})", ""]
    lines.append(to_markdown_table(headers, md_rows))
    lines.append("")
    lines.append(f"{row_count} row(s) returned{suffix}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Registry — maps command names to text format functions for dispatch_output()
# ---------------------------------------------------------------------------
REGISTRY: dict[str, object] = {
    "inspect": format_inspect,
    "preview": format_preview,
    "profile": format_profile,
    "search": format_search,
    "dist": format_dist,
    "template": format_template,
    "lineage": format_lineage,
    "snowflake_lineage": format_snowflake_lineage,
    "metadata": format_metadata,
    "metadata_list": format_metadata_list,
    "explain": format_explain,
    "diff": format_diff,
    "joins": format_joins,
    "quality": format_quality,
    "assert_check": format_assert_check,
    "pivot": format_pivot,
    "values": format_values,
    "catalog": format_catalog,
    "query": format_query,
    "frequencies": format_frequencies,
}
