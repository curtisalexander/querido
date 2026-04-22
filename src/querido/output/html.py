"""HTML output formatters — standalone HTML pages with interactive tables.

Each ``format_*_html()`` function returns a complete HTML document string with
embedded CSS and JavaScript for sorting, filtering, and export (copy / CSV
download).  ``qdo -f html`` opens the result in the default browser.
"""

from __future__ import annotations

import html
import tempfile
import webbrowser
from pathlib import Path
from typing import Any

from querido.output import fmt_value

# ---------------------------------------------------------------------------
# Shared page shell
# ---------------------------------------------------------------------------

_CSS = """\
:root {
  --bg: #ffffff; --fg: #1a1a2e; --accent: #4361ee;
  --border: #dee2e6; --hover: #f0f4ff; --header-bg: #f8f9fa;
  --toolbar-bg: #f1f3f5; --badge-bg: #e9ecef;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1a1a2e; --fg: #e0e0e0; --accent: #7b8cff;
    --border: #3a3a5c; --hover: #2a2a4e; --header-bg: #22223a;
    --toolbar-bg: #22223a; --badge-bg: #2a2a4e;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg); color: var(--fg);
  padding: 24px; line-height: 1.6;
}
h1 { font-size: 1.5rem; margin-bottom: 4px; }
.subtitle { color: #6c757d; font-size: 0.9rem; margin-bottom: 16px; }
.toolbar {
  display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  margin-bottom: 12px; padding: 8px 12px;
  background: var(--toolbar-bg); border-radius: 6px;
}
.toolbar input[type="text"] {
  padding: 6px 10px; border: 1px solid var(--border); border-radius: 4px;
  font-size: 0.85rem; background: var(--bg); color: var(--fg);
  flex: 1; min-width: 200px;
}
.toolbar button, .export-btn {
  padding: 6px 14px; border: 1px solid var(--border); border-radius: 4px;
  background: var(--bg); color: var(--fg); cursor: pointer;
  font-size: 0.82rem; white-space: nowrap;
}
.toolbar button:hover, .export-btn:hover { background: var(--hover); }
.badge {
  display: inline-block; padding: 2px 8px; border-radius: 10px;
  background: var(--badge-bg); font-size: 0.8rem;
}
.table-wrapper { overflow-x: auto; }
table {
  border-collapse: collapse; width: 100%; font-size: 0.85rem;
}
th, td {
  padding: 8px 12px; border: 1px solid var(--border);
  text-align: left; white-space: nowrap;
}
th {
  background: var(--header-bg); cursor: pointer; user-select: none;
  position: sticky; top: 0; z-index: 1;
}
th:hover { background: var(--hover); }
th .sort-arrow { margin-left: 4px; font-size: 0.7rem; opacity: 0.5; }
th.sort-asc .sort-arrow::after { content: "\\25B2"; opacity: 1; }
th.sort-desc .sort-arrow::after { content: "\\25BC"; opacity: 1; }
tr:hover { background: var(--hover); }
.null-val { color: #adb5bd; font-style: italic; }
.toast {
  position: fixed; bottom: 24px; right: 24px; padding: 10px 20px;
  background: #333; color: #fff; border-radius: 6px; font-size: 0.85rem;
  opacity: 0; transition: opacity 0.3s;
}
.toast.show { opacity: 1; }
footer {
  margin-top: 16px; font-size: 0.8rem; color: #6c757d;
  display: flex; gap: 12px; align-items: center;
}
"""

_JS = """\
(function() {
  const table = document.querySelector("table");
  if (!table) return;
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  const ths = Array.from(thead.querySelectorAll("th"));
  const filterInput = document.getElementById("filter-input");
  const rowCountEl = document.getElementById("row-count");
  const totalRows = tbody.querySelectorAll("tr").length;
  let sortCol = -1, sortDir = 0; // 0=none, 1=asc, 2=desc

  // --- Sort ---
  ths.forEach((th, idx) => {
    th.addEventListener("click", () => {
      if (sortCol === idx) { sortDir = (sortDir + 1) % 3; }
      else { sortCol = idx; sortDir = 1; }
      ths.forEach(h => h.classList.remove("sort-asc", "sort-desc"));
      if (sortDir === 1) th.classList.add("sort-asc");
      else if (sortDir === 2) th.classList.add("sort-desc");
      doSort();
    });
  });

  function doSort() {
    const rows = Array.from(tbody.querySelectorAll("tr"));
    if (sortDir === 0) { rows.sort((a,b) => a.dataset.idx - b.dataset.idx); }
    else {
      rows.sort((a, b) => {
        const av = a.children[sortCol]?.textContent ?? "";
        const bv = b.children[sortCol]?.textContent ?? "";
        const an = parseFloat(av.replace(/,/g, "")), bn = parseFloat(bv.replace(/,/g, ""));
        let cmp;
        if (!isNaN(an) && !isNaN(bn)) { cmp = an - bn; }
        else { cmp = av.localeCompare(bv, undefined, {numeric: true, sensitivity: "base"}); }
        return sortDir === 2 ? -cmp : cmp;
      });
    }
    rows.forEach(r => tbody.appendChild(r));
    updateCount();
  }

  // --- Filter ---
  if (filterInput) {
    filterInput.addEventListener("input", () => {
      const q = filterInput.value.toLowerCase();
      tbody.querySelectorAll("tr").forEach(tr => {
        const text = tr.textContent.toLowerCase();
        tr.style.display = text.includes(q) ? "" : "none";
      });
      updateCount();
    });
  }

  function updateCount() {
    if (!rowCountEl) return;
    const visible = tbody.querySelectorAll("tr:not([style*='display: none'])").length;
    rowCountEl.textContent = visible === totalRows
      ? totalRows + " rows"
      : visible + " of " + totalRows + " rows";
  }

  // --- Copy ---
  window.copyTable = function() {
    const rows = Array.from(tbody.querySelectorAll("tr:not([style*='display: none'])"));
    const headers = ths.map(th => th.textContent.trim());
    const lines = [headers.join("\\t")];
    rows.forEach(r => {
      lines.push(Array.from(r.children).map(td => td.textContent).join("\\t"));
    });
    navigator.clipboard.writeText(lines.join("\\n")).then(() => showToast("Copied to clipboard"));
  };

  // --- Export CSV ---
  window.exportCSV = function() {
    const rows = Array.from(tbody.querySelectorAll("tr:not([style*='display: none'])"));
    const headers = ths.map(th => th.textContent.trim());
    const escapeCSV = v => {
      const s = String(v);
      if (s.includes(",") || s.includes('"') || s.includes("\\n"))
        return '"' + s.replace(/"/g, '""') + '"';
      return s;
    };
    const lines = [headers.map(escapeCSV).join(",")];
    rows.forEach(r => {
      lines.push(Array.from(r.children).map(td => escapeCSV(td.textContent)).join(","));
    });
    const blob = new Blob([lines.join("\\n")], {type: "text/csv"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (document.title || "export") + ".csv";
    a.click();
    URL.revokeObjectURL(a.href);
    showToast("CSV downloaded");
  };

  // --- Toast ---
  function showToast(msg) {
    let t = document.querySelector(".toast");
    if (!t) {
      t = document.createElement("div");
      t.className = "toast";
      document.body.appendChild(t);
    }
    t.textContent = msg; t.classList.add("show");
    setTimeout(() => t.classList.remove("show"), 2000);
  }
})();
"""


def _html_page(title: str, subtitle: str, table_html: str, footer_text: str = "") -> str:
    """Build a complete standalone HTML page wrapping *table_html*.

    The page includes embedded CSS/JS for sorting, filtering, copy/export.
    """
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<div class="subtitle">{html.escape(subtitle)}</div>
<div class="toolbar">
  <input type="text" id="filter-input" placeholder="Filter rows…">
  <span class="badge" id="row-count"></span>
  <button onclick="copyTable()">Copy</button>
  <button onclick="exportCSV()">Export CSV</button>
</div>
<div class="table-wrapper">
{table_html}
</div>
<footer>{html.escape(footer_text)}</footer>
<script>{_JS}</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Table builder
# ---------------------------------------------------------------------------


def _build_table(headers: list[str], rows: list[list[Any]]) -> str:
    """Build an HTML ``<table>`` with ``<thead>``/``<tbody>``."""
    parts: list[str] = ["<table>", "<thead><tr>"]
    parts.extend(
        f'<th>{html.escape(str(h))}<span class="sort-arrow"></span></th>' for h in headers
    )
    parts.append("</tr></thead>")
    parts.append("<tbody>")
    for idx, row in enumerate(rows):
        parts.append(f'<tr data-idx="{idx}">')
        for val in row:
            if val is None:
                parts.append('<td class="null-val">NULL</td>')
            elif val == "":
                parts.append("<td></td>")
            else:
                parts.append(f"<td>{html.escape(str(val))}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# open_html — write to temp file and open in browser
# ---------------------------------------------------------------------------


def open_html(html_content: str, prefix: str = "qdo-") -> Path:
    """Write *html_content* to a temporary file and open it in the default browser.

    Returns the path to the written file.
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".html",
        prefix=prefix,
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(html_content)
    path = Path(tmp.name)
    webbrowser.open(path.as_uri())
    return path


# ---------------------------------------------------------------------------
# Per-command formatters
# ---------------------------------------------------------------------------


def format_inspect_html(
    table_name: str,
    columns: list[dict],
    row_count: int,
    verbose: bool = False,
    table_comment: str | None = None,
) -> str:
    """Render inspect results as a standalone HTML page."""
    headers = ["Column", "Type", "Nullable", "Default", "Primary Key"]
    if verbose:
        headers.append("Comment")

    rows: list[list[Any]] = []
    for col in columns:
        row: list[Any] = [
            col["name"],
            col["type"],
            "YES" if col["nullable"] else "NO",
            str(col["default"]) if col["default"] is not None else "",
            "PK" if col.get("primary_key") else "",
        ]
        if verbose:
            row.append(col.get("comment") or "")
        rows.append(row)

    subtitle = f"Row count: {row_count:,}"
    if table_comment:
        subtitle = f"{table_comment} — {subtitle}"

    return _html_page(
        title=f"Inspect: {table_name}",
        subtitle=subtitle,
        table_html=_build_table(headers, rows),
        footer_text=f"qdo inspect — {len(columns)} columns, {row_count:,} rows",
    )


def format_preview_html(
    table_name: str,
    data: list[dict],
    limit: int,
) -> str:
    """Render preview results as a standalone HTML page."""
    if not data:
        return _html_page(
            title=f"Preview: {table_name}",
            subtitle="No rows found.",
            table_html="<p>No data.</p>",
        )

    headers = list(data[0].keys())
    rows = [[row.get(h) for h in headers] for row in data]

    return _html_page(
        title=f"Preview: {table_name}",
        subtitle=f"Showing {len(data)} row(s) (limit {limit})",
        table_html=_build_table(headers, rows),
        footer_text=f"qdo preview — {len(data)} rows",
    )


def format_profile_html(
    table_name: str,
    data: list[dict],
    row_count: int,
    sampled: bool,
    sample_size: int | None,
) -> str:
    """Render profile results as a standalone HTML page."""
    if not data:
        return _html_page(
            title=f"Profile: {table_name}",
            subtitle="No columns to profile.",
            table_html="<p>No data.</p>",
        )

    headers = [
        "Column",
        "Type",
        "Min",
        "Max",
        "Mean",
        "Median",
        "Stddev",
        "Min Len",
        "Max Len",
        "Nulls",
        "Null %",
        "Distinct",
    ]
    rows: list[list[Any]] = [
        [
            r["column_name"],
            r["column_type"],
            fmt_value(r.get("min_val")),
            fmt_value(r.get("max_val")),
            fmt_value(r.get("mean_val")),
            fmt_value(r.get("median_val")),
            fmt_value(r.get("stddev_val")),
            fmt_value(r.get("min_length")),
            fmt_value(r.get("max_length")),
            fmt_value(r.get("null_count")),
            fmt_value(r.get("null_pct")),
            fmt_value(r.get("distinct_count")),
        ]
        for r in data
    ]

    sample_note = ""
    if sampled and sample_size:
        sample_note = f" (sampled {sample_size:,} rows)"

    return _html_page(
        title=f"Profile: {table_name}",
        subtitle=f"Total rows: {row_count:,}{sample_note}",
        table_html=_build_table(headers, rows),
        footer_text=f"qdo profile — {len(data)} columns, {row_count:,} rows{sample_note}",
    )


def format_dist_html(dist_result: dict) -> str:
    """Render distribution results as a standalone HTML page."""
    table_name = dist_result["table"]
    column = dist_result["column"]
    mode = dist_result["mode"]
    total_rows = dist_result["total_rows"]
    null_count = dist_result["null_count"]

    if mode == "numeric":
        buckets = dist_result["buckets"]
        headers = ["Bucket Min", "Bucket Max", "Count"]
        rows = [
            [fmt_value(b["bucket_min"]), fmt_value(b["bucket_max"]), f"{b['count']:,}"]
            for b in buckets
        ]
    else:
        values = dist_result["values"]
        headers = ["Value", "Count"]
        rows = [
            [
                str(v["value"]) if v["value"] is not None else "(NULL)",
                f"{v['count']:,}",
            ]
            for v in values
        ]

    null_note = f" (nulls: {null_count:,})" if null_count else ""

    return _html_page(
        title=f"Distribution: {table_name}.{column}",
        subtitle=f"Mode: {mode} — Total rows: {total_rows:,}{null_note}",
        table_html=_build_table(headers, rows),
        footer_text=f"qdo dist — {table_name}.{column}",
    )


def format_template_html(template_result: dict, *, style: str = "table") -> str:
    """Render template results as a standalone HTML page."""
    table_name = template_result["table"]
    table_comment = template_result["table_comment"]
    row_count = template_result["row_count"]
    columns = template_result["columns"]

    headers = [
        "Column",
        "Type",
        "Nullable",
        "Distinct",
        "Nulls",
        "Null %",
        "Min",
        "Max",
        "Sample Values",
        "Business Definition",
        "Data Owner",
        "Notes",
    ]
    rows: list[list[Any]] = []
    for col in columns:
        min_display = fmt_value(col.get("min_val")) or fmt_value(col.get("min_length"))
        max_display = fmt_value(col.get("max_val")) or fmt_value(col.get("max_length"))
        rows.append(
            [
                col["name"],
                col["type"],
                "YES" if col["nullable"] else "NO",
                fmt_value(col.get("distinct_count")),
                fmt_value(col.get("null_count")),
                fmt_value(col.get("null_pct")),
                min_display,
                max_display,
                col.get("sample_values", ""),
                "",
                "",
                "",  # placeholders
            ]
        )

    subtitle = f"Row count: {row_count:,}"
    if table_comment:
        subtitle = f"{table_comment} — {subtitle}"

    return _html_page(
        title=f"Template: {table_name}",
        subtitle=subtitle,
        table_html=_build_table(headers, rows),
        footer_text=f"qdo template — {len(columns)} columns",
    )


def format_lineage_html(lineage_result: dict) -> str:
    """Render view lineage as a standalone HTML page."""
    view_name = lineage_result["view"]
    dialect = lineage_result["dialect"]
    definition = lineage_result["definition"]

    # For view definitions, we show the SQL in a code block rather than a table
    code_html = (
        f'<pre style="background:var(--header-bg);padding:16px;border-radius:6px;'
        f'overflow-x:auto;font-size:0.85rem;border:1px solid var(--border)">'
        f"<code>{html.escape(definition)}</code></pre>"
    )

    return _html_page(
        title=f"View: {view_name}",
        subtitle=f"Dialect: {dialect}",
        table_html=code_html,
        footer_text=f"qdo lineage — {view_name}",
    )


def format_snowflake_lineage_html(lineage_result: dict) -> str:
    """Render Snowflake lineage results as a standalone HTML page."""
    object_name = lineage_result["object"]
    direction = lineage_result["direction"]
    entries = lineage_result["entries"]

    if not entries:
        return _html_page(
            title=f"Lineage: {object_name} ({direction})",
            subtitle=f"No {direction} lineage found.",
            table_html=f"<p>No {direction} lineage found for '{html.escape(object_name)}'.</p>",
        )

    headers = list(entries[0].keys())
    rows = [[e.get(h) for h in headers] for e in entries]

    return _html_page(
        title=f"Lineage: {object_name} ({direction})",
        subtitle=f"{len(entries)} lineage entries",
        table_html=_build_table(headers, rows),
        footer_text=f"qdo snowflake lineage — {object_name}",
    )


def format_frequencies_html(
    table_name: str,
    freq_data: dict[str, list[dict]],
    row_count: int,
) -> str:
    """Render frequencies results as a standalone HTML page."""
    headers = ["Column", "Value", "Count", "%"]
    rows: list[list[Any]] = []
    for col_name, col_rows in freq_data.items():
        for r in col_rows:
            pct = round(100.0 * r["count"] / row_count, 2) if row_count else 0
            val = str(r["value"]) if r["value"] is not None else "(NULL)"
            rows.append([col_name, val, f"{r['count']:,}", str(pct)])

    return _html_page(
        title=f"Frequencies: {table_name}",
        subtitle=f"Total rows: {row_count:,}",
        table_html=_build_table(headers, rows) if rows else "<p>No frequency data.</p>",
        footer_text=f"qdo profile --top — {table_name}",
    )


def format_metadata_html(
    meta: dict,
) -> str:
    """Render stored metadata as a standalone HTML page."""
    columns = meta.get("columns", [])
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

    return _html_page(
        title=f"Metadata: {meta.get('table', '')}",
        subtitle=f"Row count: {meta.get('row_count', 0):,}",
        table_html=_build_table(headers, rows) if rows else "<p>No columns.</p>",
        footer_text=f"qdo metadata show — {meta.get('table', '')}",
    )


def format_metadata_list_html(
    connection: str,
    entries: list[dict],
) -> str:
    """Render metadata listing as a standalone HTML page."""
    if not entries:
        return _html_page(
            title=f"Metadata: {connection}",
            subtitle="No metadata stored.",
            table_html="<p>No data.</p>",
        )

    headers = ["Table", "Completeness", "Path"]
    rows = [
        [
            e.get("table", ""),
            f"{e.get('completeness', 0):.0f}%",
            e.get("path", ""),
        ]
        for e in entries
    ]

    return _html_page(
        title=f"Metadata: {connection}",
        subtitle=f"{len(entries)} table(s)",
        table_html=_build_table(headers, rows),
        footer_text=f"qdo metadata list — {connection}",
    )


def format_metadata_search_html(
    result: dict,
) -> str:
    """Render metadata-search results as a standalone HTML page."""
    matches = result.get("results") or []
    if not matches:
        return _html_page(
            title=f"Metadata Search: {result.get('query', '')}",
            subtitle=f"No matches in {result.get('connection', '')}",
            table_html="<p>No results.</p>",
            footer_text="qdo metadata search",
        )

    headers = ["Kind", "Table", "Column", "Score", "Matched", "Excerpt"]
    rows = [
        [
            str(row.get("kind", "")),
            str(row.get("table", "")),
            str(row.get("column") or ""),
            str(row.get("score", "")),
            ", ".join(str(term) for term in row.get("matched_terms") or []),
            str(row.get("excerpt", "")),
        ]
        for row in matches
    ]

    return _html_page(
        title=f"Metadata Search: {result.get('query', '')}",
        subtitle=f"{len(matches)} result(s) in {result.get('connection', '')}",
        table_html=_build_table(headers, rows),
        footer_text="qdo metadata search",
    )


def format_explain_html(
    result: dict,
) -> str:
    """Render query plan as a standalone HTML page."""
    plan = result.get("plan", "")
    dialect = result.get("dialect", "")
    analyzed = " (ANALYZE)" if result.get("analyzed") else ""

    # Render plan as preformatted text
    import html

    plan_html = f"<pre style='font-family:monospace;padding:1em'>{html.escape(plan)}</pre>"

    return _html_page(
        title=f"Query Plan — {dialect}{analyzed}",
        subtitle=result.get("sql", ""),
        table_html=plan_html,
        footer_text="qdo explain",
    )


def format_diff_html(
    result: dict,
) -> str:
    """Render schema diff as a standalone HTML page."""
    added = result["added"]
    removed = result["removed"]
    changed = result["changed"]

    if not added and not removed and not changed:
        return _html_page(
            title=f"Diff: {result['left']} → {result['right']}",
            subtitle="Schemas are identical.",
            table_html="<p>No differences.</p>",
        )

    headers = ["Change", "Column", "Left Type", "Right Type", "Left Nullable", "Right Nullable"]
    rows: list[list] = [
        *[
            ["added", c["name"], "", c["type"], "", "YES" if c["nullable"] else "NO"]
            for c in added
        ],
        *[
            ["removed", c["name"], c["type"], "", "YES" if c["nullable"] else "NO", ""]
            for c in removed
        ],
        *[
            [
                "changed",
                c["name"],
                c["left_type"],
                c["right_type"],
                "YES" if c["left_nullable"] else "NO",
                "YES" if c["right_nullable"] else "NO",
            ]
            for c in changed
        ],
    ]

    summary = (
        f"{len(added)} added, {len(removed)} removed, "
        f"{len(changed)} changed, {result['unchanged_count']} unchanged"
    )
    if isinstance(result.get("previous_row_count"), int) and isinstance(
        result.get("current_row_count"), int
    ):
        delta = result.get("row_count_delta")
        delta_text = f"{delta:+,}" if isinstance(delta, int) else "n/a"
        summary += (
            f" · rows {result['previous_row_count']:,} → "
            f"{result['current_row_count']:,} ({delta_text})"
        )
    return _html_page(
        title=f"Diff: {result['left']} → {result['right']}",
        subtitle=summary,
        table_html=_build_table(headers, rows),
        footer_text="qdo diff",
    )


def format_joins_html(
    result: dict,
) -> str:
    """Render join candidates as a standalone HTML page."""
    candidates = result["candidates"]
    if not candidates:
        return _html_page(
            title=f"Joins: {result['source']}",
            subtitle="No join candidates found.",
            table_html="<p>No data.</p>",
        )

    headers = ["Target", "Source Col", "Target Col", "Match", "Confidence"]
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

    return _html_page(
        title=f"Joins: {result['source']}",
        subtitle=f"{len(candidates)} table(s) with join candidates",
        table_html=_build_table(headers, rows),
        footer_text=f"qdo joins — {result['source']}",
    )


def format_quality_html(
    result: dict,
) -> str:
    """Render data quality summary as a standalone HTML page."""
    columns = result["columns"]
    if not columns:
        return _html_page(
            title=f"Quality: {result['table']}",
            subtitle="No columns to check.",
            table_html="<p>No data.</p>",
        )

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

    subtitle = f"{result['row_count']:,} rows"
    if result.get("sampled") and result.get("sample_size"):
        subtitle += f" (sampled {result['sample_size']:,})"
    if result["duplicate_rows"] is not None:
        subtitle += f", {result['duplicate_rows']:,} duplicate rows"

    footer = f"qdo quality \u2014 {result['table']}"
    if result.get("sampling_note"):
        footer += f" | {result['sampling_note']}"

    return _html_page(
        title=f"Quality: {result['table']}",
        subtitle=subtitle,
        table_html=_build_table(headers, rows),
        footer_text=footer,
    )


def format_assert_check_html(
    result: dict,
) -> str:
    """Render assertion result as a standalone HTML page."""
    status = "PASSED" if result["passed"] else "FAILED"
    op_labels = {"eq": "==", "gt": ">", "lt": "<", "gte": ">=", "lte": "<="}
    op_sym = op_labels.get(result["operator"], result["operator"])
    name = result.get("name") or "Assertion"

    headers = ["Field", "Value"]
    rows = [
        ["Name", name],
        ["Status", status],
        ["Actual", str(result["actual"])],
        ["Expected", f"{op_sym} {result['expected']}"],
    ]

    return _html_page(
        title=f"Assert: {name}",
        subtitle=status,
        table_html=_build_table(headers, rows),
        footer_text=f"qdo assert — {status}",
    )


def format_pivot_html(
    result: dict,
) -> str:
    """Render pivot results as a standalone HTML page."""
    rows = result["rows"]
    if not rows:
        return _html_page(
            title="Pivot Results",
            subtitle="No rows returned.",
            table_html="<p>No data.</p>",
        )

    headers = result["headers"]
    table_rows = [[row.get(h) for h in headers] for row in rows]

    return _html_page(
        title="Pivot Results",
        subtitle=f"{result['row_count']} group(s)",
        table_html=_build_table(headers, table_rows),
        footer_text=f"qdo pivot — {result['row_count']} groups",
    )


def format_values_html(
    result: dict,
) -> str:
    """Render distinct values as a standalone HTML page."""
    values = result["values"]
    col = result["column"]
    tbl = result["table"]
    truncated = result["truncated"]

    if not values:
        return _html_page(
            title=f"Values: {tbl}.{col}",
            subtitle="No values found.",
            table_html="<p>No data.</p>",
        )

    subtitle = f"{result['distinct_count']:,} distinct values, {result['null_count']:,} nulls"
    if truncated:
        subtitle += f" (showing top {len(values)})"

    headers = ["Value", "Count"]
    rows = [
        [str(v["value"]) if v["value"] is not None else "(NULL)", f"{v['count']:,}"]
        for v in values
    ]

    return _html_page(
        title=f"Values: {tbl}.{col}",
        subtitle=subtitle,
        table_html=_build_table(headers, rows),
        footer_text=f"qdo values — {tbl}.{col}",
    )


def format_freshness_html(
    result: dict,
) -> str:
    """Render freshness results as a standalone HTML page."""
    candidates = result.get("candidates") or []
    subtitle = f"{result.get('status', 'unknown')} — {result.get('row_count', 0):,} rows"

    if not candidates:
        return _html_page(
            title=f"Freshness: {result.get('table', '')}",
            subtitle=subtitle,
            table_html=(
                f"<p>{html.escape(str(result.get('reason') or 'No temporal columns found.'))}</p>"
            ),
            footer_text="qdo freshness",
        )

    headers = ["Column", "Type", "Null %", "Earliest", "Latest", "Age Days", "Signals"]
    rows = [
        [
            candidate.get("name", ""),
            candidate.get("type", ""),
            f"{float(candidate.get('null_pct', 0.0)):.2f}",
            candidate.get("earliest_value") or "",
            candidate.get("latest_value") or "",
            (
                f"{float(candidate['latest_age_days']):.2f}"
                if candidate.get("latest_age_days") is not None
                else ""
            ),
            ", ".join(candidate.get("reasons") or []),
        ]
        for candidate in candidates
    ]

    return _html_page(
        title=f"Freshness: {result.get('table', '')}",
        subtitle=subtitle,
        table_html=_build_table(headers, rows),
        footer_text=f"qdo freshness — {result.get('selected_column') or 'no selected column'}",
    )


def format_plan_html(
    result: dict,
) -> str:
    """Render a dry-run plan as a standalone HTML page."""
    headers = ["Field", "Value"]
    rows = []
    for key in (
        "action",
        "mode",
        "summary",
        "executable",
        "destination",
        "format",
        "table",
        "output_path",
        "limit",
    ):
        value = result.get(key)
        if value not in (None, "", []):
            rows.append([key, str(value)])
    if result.get("sql"):
        rows.append(["sql", str(result["sql"])])
    if result.get("effects"):
        rows.append(["effects", " | ".join(str(x) for x in result["effects"])])
    if result.get("writes"):
        rows.append(["writes", " | ".join(str(x) for x in result["writes"])])

    return _html_page(
        title=f"Plan: {result.get('action', 'plan')}",
        subtitle=str(result.get("summary", "")),
        table_html=_build_table(headers, rows),
        footer_text="qdo --plan",
    )


def format_estimate_html(
    result: dict,
) -> str:
    """Render an estimate as a standalone HTML page."""
    headers = ["Field", "Value"]
    rows = []
    for key in (
        "action",
        "dialect",
        "complexity",
        "cost_hint",
        "row_estimate",
        "row_estimate_source",
        "output_row_ceiling",
        "destination",
        "format",
        "table",
        "output_path",
    ):
        value = result.get(key)
        if value not in (None, "", []):
            rows.append([key, str(value)])
    if result.get("notes"):
        rows.append(["notes", " | ".join(str(x) for x in result["notes"])])
    if result.get("sql"):
        rows.append(["sql", str(result["sql"])])
    if result.get("explain_plan"):
        rows.append(["explain_plan", str(result["explain_plan"])])

    return _html_page(
        title=f"Estimate: {result.get('action', 'estimate')}",
        subtitle=str(result.get("summary", "")),
        table_html=_build_table(headers, rows),
        footer_text="qdo --estimate",
    )


def format_search_html(
    result: dict,
) -> str:
    """Render ranked command-search results as standalone HTML."""
    matches = result.get("results") or []
    if not matches:
        return _html_page(
            title="Search",
            subtitle=f"No strong matches for: {result.get('query', '')}",
            table_html="<p>No data.</p>",
            footer_text="qdo search",
        )

    headers = ["Command", "Category", "Score", "Description", "Why", "Help"]
    rows = [
        [
            match.get("name", ""),
            match.get("category", ""),
            match.get("score", ""),
            match.get("description", ""),
            match.get("rationale", ""),
            match.get("help_command", ""),
        ]
        for match in matches
    ]

    return _html_page(
        title="Search",
        subtitle=f"{result.get('result_count', 0)} match(es) for: {result.get('query', '')}",
        table_html=_build_table(headers, rows),
        footer_text="qdo search",
    )


def format_context_html(
    result: dict,
) -> str:
    """Render table context as a standalone HTML page."""
    columns = result.get("columns", [])
    table_name = result.get("table", "")
    row_count = result.get("row_count", 0)
    dialect = result.get("dialect", "")
    sampled = result.get("sampled", False)
    sample_size = result.get("sample_size")
    table_desc = result.get("table_description") or result.get("table_comment") or ""

    if not columns:
        return _html_page(
            title=f"Context: {table_name}",
            subtitle="No columns found.",
            table_html="<p>No data.</p>",
        )

    headers = ["Column", "Type", "Null%", "Distinct", "Range / Sample Values", "Notes"]
    rows: list[list[Any]] = []
    for col in columns:
        null_pct = col.get("null_pct")
        null_str = f"{null_pct}%" if null_pct is not None else ""

        distinct = col.get("distinct_count")
        distinct_str = f"{distinct:,}" if distinct is not None else ""

        sample = col.get("sample_values")
        min_v = col.get("min")
        max_v = col.get("max")
        if sample:
            range_str = ", ".join(str(v) for v in sample[:5])
            if len(sample) > 5:
                range_str += " ..."
        elif min_v is not None and max_v is not None:
            range_str = f"{min_v} \u2192 {max_v}"
        else:
            range_str = ""

        notes_parts: list[str] = []
        if col.get("primary_key"):
            notes_parts.append("PK")
        if col.get("pii"):
            notes_parts.append("PII")
        if col.get("description"):
            notes_parts.append(col.get("description", ""))
        rows.append(
            [
                col.get("name", ""),
                col.get("type", ""),
                null_str,
                distinct_str,
                range_str,
                "  ".join(notes_parts),
            ]
        )

    count_str = f"{row_count:,}"
    if sampled and sample_size:
        count_str += f" ({sample_size:,} sampled)"
    subtitle = f"{dialect} \u2014 {count_str} rows"
    if table_desc:
        subtitle = f"{table_desc} \u2014 {subtitle}"

    return _html_page(
        title=f"Context: {table_name}",
        subtitle=subtitle,
        table_html=_build_table(headers, rows),
        footer_text=f"qdo context \u2014 {len(columns)} columns, {row_count:,} rows",
    )


def format_catalog_html(
    catalog: dict,
) -> str:
    """Render database catalog as a standalone HTML page."""
    tables = catalog["tables"]
    if not tables:
        return _html_page(
            title="Catalog",
            subtitle="No tables found.",
            table_html="<p>No data.</p>",
        )

    headers = ["Table", "Type", "Columns", "Rows"]
    rows = []
    for t in tables:
        col_count = str(len(t["columns"])) if t["columns"] is not None else "-"
        row_count = f"{t['row_count']:,}" if t["row_count"] is not None else "-"
        rows.append([t["name"], t["type"], col_count, row_count])

    return _html_page(
        title="Catalog",
        subtitle=f"{catalog['table_count']} tables",
        table_html=_build_table(headers, rows),
        footer_text=f"qdo catalog — {catalog['table_count']} tables",
    )


def format_catalog_functions_html(
    result: dict,
) -> str:
    """Render function catalog as a standalone HTML page."""
    if not result.get("supported", True):
        return _html_page(
            title="Function Catalog",
            subtitle=str(result.get("reason") or "Function catalog unavailable."),
            table_html="<p>No data.</p>",
        )

    functions = result.get("functions") or []
    if not functions:
        return _html_page(
            title="Function Catalog",
            subtitle="No functions found.",
            table_html="<p>No data.</p>",
        )

    headers = ["Name", "Schema", "Type", "Overloads", "Returns", "Notes"]
    rows = []
    for entry in functions:
        notes_parts = []
        languages = entry.get("languages") or []
        if languages:
            notes_parts.append(f"lang: {', '.join(languages)}")
        notes = entry.get("notes") or []
        if notes:
            notes_parts.append(", ".join(notes))
        if entry.get("description"):
            notes_parts.append(str(entry["description"]))
        rows.append(
            [
                entry.get("name", ""),
                entry.get("schema", ""),
                entry.get("type", ""),
                entry.get("overload_count", 0),
                ", ".join(entry.get("return_types") or []),
                " | ".join(notes_parts),
            ]
        )

    return _html_page(
        title="Function Catalog",
        subtitle=f"{result['function_count']} functions",
        table_html=_build_table(headers, rows),
        footer_text=f"qdo catalog functions — {result['function_count']} functions",
    )


def format_query_html(
    columns: list[str],
    rows: list[dict],
    row_count: int,
    *,
    limited: bool = False,
    sql: str = "",
) -> str:
    """Render ad-hoc query results as a standalone HTML page."""
    if not rows:
        return _html_page(
            title="Query Results",
            subtitle="Query returned no rows.",
            table_html="<p>No data.</p>",
        )

    headers = list(rows[0].keys())
    table_rows = [[row.get(h) for h in headers] for row in rows]
    suffix = " (limit reached)" if limited else ""

    return _html_page(
        title="Query Results",
        subtitle=f"{row_count} row(s) returned{suffix}",
        table_html=_build_table(headers, table_rows),
        footer_text=f"qdo query — {row_count} rows",
    )


# ---------------------------------------------------------------------------
# Registry — maps command names to HTML output functions for dispatch_output()
# ---------------------------------------------------------------------------
REGISTRY: dict[str, object] = {
    "search": format_search_html,
    "inspect": format_inspect_html,
    "preview": format_preview_html,
    "profile": format_profile_html,
    "estimate": format_estimate_html,
    "plan": format_plan_html,
    "context": format_context_html,
    "dist": format_dist_html,
    "freshness": format_freshness_html,
    "template": format_template_html,
    "lineage": format_lineage_html,
    "snowflake_lineage": format_snowflake_lineage_html,
    "metadata": format_metadata_html,
    "metadata_list": format_metadata_list_html,
    "metadata_search": format_metadata_search_html,
    "explain": format_explain_html,
    "diff": format_diff_html,
    "joins": format_joins_html,
    "quality": format_quality_html,
    "assert_check": format_assert_check_html,
    "pivot": format_pivot_html,
    "values": format_values_html,
    "catalog": format_catalog_html,
    "catalog_functions": format_catalog_functions_html,
    "query": format_query_html,
    "frequencies": format_frequencies_html,
}
