"""HTML output formatters — standalone HTML pages with interactive tables.

Each ``format_*_html()`` function returns a complete HTML document string with
embedded CSS and JavaScript for sorting, filtering, and export (copy / CSV
download).  The shared ``_html_page()`` helper produces the page shell so that
Phase B (``qdo serve``) can re-use the same table markup and JS inside a web
app layout.
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
    This function is the shared shell that Phase B (``qdo serve``) can also
    use when rendering inside a web-app layout.
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
    parts: list[str] = ['<table>']
    parts.append('<thead><tr>')
    for h in headers:
        parts.append(f'<th>{html.escape(str(h))}<span class="sort-arrow"></span></th>')
    parts.append('</tr></thead>')
    parts.append('<tbody>')
    for idx, row in enumerate(rows):
        parts.append(f'<tr data-idx="{idx}">')
        for val in row:
            if val is None or val == "":
                parts.append('<td class="null-val">NULL</td>')
            else:
                parts.append(f'<td>{html.escape(str(val))}</td>')
        parts.append('</tr>')
    parts.append('</tbody></table>')
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
        "Column", "Type", "Min", "Max", "Mean", "Median", "Stddev",
        "Min Len", "Max Len", "Nulls", "Null %", "Distinct",
    ]
    rows: list[list[Any]] = []
    for r in data:
        rows.append([
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
        ])

    sample_note = ""
    if sampled and sample_size:
        sample_note = f" (sampled {sample_size:,} rows)"

    return _html_page(
        title=f"Profile: {table_name}",
        subtitle=f"Total rows: {row_count:,}{sample_note}",
        table_html=_build_table(headers, rows),
        footer_text=f"qdo profile — {len(data)} columns, {row_count:,} rows{sample_note}",
    )


def format_search_html(
    pattern: str,
    results: list[dict],
) -> str:
    """Render search results as a standalone HTML page."""
    if not results:
        return _html_page(
            title=f"Search: '{pattern}'",
            subtitle="No matches found.",
            table_html="<p>No matches.</p>",
        )

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

    return _html_page(
        title=f"Search: '{pattern}'",
        subtitle=f"{len(results)} match(es)",
        table_html=_build_table(headers, rows),
        footer_text=f"qdo search — {len(results)} matches for '{pattern}'",
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


def format_template_html(template_result: dict) -> str:
    """Render template results as a standalone HTML page."""
    table_name = template_result["table"]
    table_comment = template_result["table_comment"]
    row_count = template_result["row_count"]
    columns = template_result["columns"]

    headers = [
        "Column", "Type", "Nullable", "Distinct", "Nulls", "Null %",
        "Min", "Max", "Sample Values", "Business Definition", "Data Owner", "Notes",
    ]
    rows: list[list[Any]] = []
    for col in columns:
        min_display = fmt_value(col.get("min_val")) or fmt_value(col.get("min_length"))
        max_display = fmt_value(col.get("max_val")) or fmt_value(col.get("max_length"))
        rows.append([
            col["name"],
            col["type"],
            "YES" if col["nullable"] else "NO",
            fmt_value(col.get("distinct_count")),
            fmt_value(col.get("null_count")),
            fmt_value(col.get("null_pct")),
            min_display,
            max_display,
            col.get("sample_values", ""),
            "", "", "",  # placeholders
        ])

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
        f'<code>{html.escape(definition)}</code></pre>'
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
