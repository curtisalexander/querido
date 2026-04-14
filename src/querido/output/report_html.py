# ruff: noqa: E501  -- CSS is a triple-quoted string; long selector lines are fine.
"""HTML renderer for ``qdo report table`` — single-file, offline-ready.

Typography and color-themed section headers follow the cheatsheet
aesthetic at ``~/code/cheatsheets`` (Inter + JetBrains Mono). Layout is
a single-column document — this is a hand-off artifact, not a dense
reference card.

No CDN fonts: Google Fonts is `@import`-ed via CSS with a local-family
fallback so the page still reads correctly offline. No JS required.
Inline SVG is used for null-rate bars.
"""

from __future__ import annotations

import html
from typing import Any

from querido.output import fmt_value


def render_table_report(report: dict) -> str:
    """Render a ``core.report.build_table_report`` dict as HTML."""
    title = report.get("table", "")
    connection = report.get("connection", "")
    generated_at = report.get("generated_at", "")
    row_count = report.get("row_count", 0)

    body = "\n".join(
        [
            _section_header(report),
            _section_metadata(report),
            _section_schema(report),
            _section_quality(report),
            _section_joins(report),
            _section_footer(report),
        ]
    )

    return _PAGE.format(
        title=html.escape(f"{title} — qdo report"),
        body=body,
        css=_CSS,
        # These are referenced by the meta strip at the top of the page
        table=html.escape(str(title)),
        connection=html.escape(str(connection)),
        generated_at=html.escape(str(generated_at)),
        row_count=f"{row_count:,}",
    )


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #


def _section_header(report: dict) -> str:
    table = html.escape(str(report.get("table", "")))
    conn = html.escape(str(report.get("connection", "")))
    dialect = html.escape(str(report.get("dialect", "")))
    row_count = report.get("row_count", 0)
    generated_at = html.escape(str(report.get("generated_at", "")))
    comment = report.get("table_comment") or report.get("table_description") or ""
    subtitle = f'<p class="lede">{html.escape(str(comment))}</p>' if comment else ""
    return f"""
    <section class="head">
      <div class="head-top">
        <div>
          <div class="eyebrow">qdo report · table</div>
          <h1>{table}</h1>
          {subtitle}
        </div>
        <div class="head-meta">
          <div><span class="k">connection</span><span class="v code">{conn}</span></div>
          <div><span class="k">dialect</span><span class="v code">{dialect}</span></div>
          <div><span class="k">rows</span><span class="v">{row_count:,}</span></div>
          <div><span class="k">generated</span><span class="v mono">{generated_at}</span></div>
        </div>
      </div>
    </section>
    """


def _section_metadata(report: dict) -> str:
    meta = report.get("metadata")
    if not meta:
        return _panel(
            "metadata",
            "theme-violet",
            '<p class="empty">No metadata recorded yet. '
            'Run <code class="cmd">qdo metadata init</code> to start capturing '
            "descriptions, owners, and valid-value sets.</p>",
        )

    rows: list[str] = []
    table_desc = meta.get("description") or meta.get("table", {}).get("description")
    owner = meta.get("owner") or meta.get("table", {}).get("owner")
    tags = meta.get("tags") or meta.get("table", {}).get("tags") or []

    if table_desc:
        rows.append(
            f'<tr><td class="k">description</td><td>{html.escape(str(table_desc))}</td></tr>'
        )
    if owner:
        rows.append(f'<tr><td class="k">owner</td><td>{html.escape(str(owner))}</td></tr>')
    if tags:
        tag_html = " ".join(f'<span class="tag">{html.escape(str(t))}</span>' for t in tags)
        rows.append(f'<tr><td class="k">tags</td><td>{tag_html}</td></tr>')

    col_meta = meta.get("columns", {}) or {}
    documented = sum(1 for v in col_meta.values() if isinstance(v, dict) and v.get("description"))
    total = len(report.get("columns", []))
    coverage = f"{documented}/{total} columns documented" if total else "—"
    rows.append(f'<tr><td class="k">coverage</td><td>{coverage}</td></tr>')

    body = (
        f'<table class="kv">{"".join(rows)}</table>'
        if rows
        else '<p class="empty">No fields set.</p>'
    )
    return _panel("metadata", "theme-violet", body)


def _section_schema(report: dict) -> str:
    columns = report.get("columns") or []
    if not columns:
        return _panel(
            "schema",
            "theme-indigo",
            '<p class="empty">No columns reported.</p>',
        )

    header = (
        "<thead><tr>"
        '<th>column</th><th>type</th><th class="num">null&nbsp;%</th>'
        '<th class="num">distinct</th><th>samples</th>'
        "</tr></thead>"
    )
    rows: list[str] = []
    for col in columns:
        name = html.escape(str(col.get("name", "")))
        typ = html.escape(str(col.get("type", "")))
        pk = col.get("primary_key")
        pk_badge = ' <span class="pk">PK</span>' if pk else ""
        not_null = "" if col.get("nullable", True) else ' <span class="nn">NOT NULL</span>'
        null_pct = col.get("null_pct")
        null_cell = _null_bar_cell(null_pct)
        distinct = col.get("distinct_count")
        distinct_cell = (
            f"{distinct:,}" if isinstance(distinct, int) else html.escape(str(distinct or ""))
        )
        samples = col.get("sample_values") or []
        if isinstance(samples, list):
            sample_cell = " ".join(
                f'<code class="sample">{html.escape(fmt_value(s))}</code>' for s in samples[:5]
            )
        else:
            sample_cell = ""
        desc = col.get("description") or col.get("comment") or ""
        desc_row = (
            f'<tr class="desc"><td colspan="5"><span class="desc-label">'
            f"{name}</span>{html.escape(str(desc))}</td></tr>"
            if desc
            else ""
        )
        rows.append(
            f"<tr>"
            f'<td class="col-name"><span class="mono">{name}</span>{pk_badge}{not_null}</td>'
            f'<td class="mono type">{typ}</td>'
            f'<td class="num">{null_cell}</td>'
            f'<td class="num">{distinct_cell}</td>'
            f'<td class="samples">{sample_cell}</td>'
            f"</tr>{desc_row}"
        )

    table_html = f'<table class="schema">{header}<tbody>{"".join(rows)}</tbody></table>'
    return _panel("schema", "theme-indigo", table_html)


def _section_quality(report: dict) -> str:
    quality = report.get("quality") or {}
    cols = quality.get("columns") or []
    if not cols:
        return _panel(
            "quality",
            "theme-amber",
            '<p class="empty">No quality scan results.</p>',
        )

    fails = [c for c in cols if c.get("status") == "fail"]
    warns = [c for c in cols if c.get("status") == "warn"]
    oks = [c for c in cols if c.get("status") == "ok"]

    if not fails and not warns:
        inner = (
            f'<p class="ok">All {len(oks)} columns passed. No null-rate or '
            "uniqueness callouts.</p>"
        )
        if quality.get("sampling_note"):
            inner += f'<p class="sampling">{html.escape(quality["sampling_note"])}</p>'
        return _panel("quality", "theme-emerald", inner)

    parts: list[str] = []
    parts.append(
        f'<p class="summary">'
        f'<span class="pill fail">{len(fails)} fail</span>'
        f'<span class="pill warn">{len(warns)} warn</span>'
        f'<span class="pill ok">{len(oks)} ok</span>'
        f"</p>"
    )

    def _callout_block(label: str, cls: str, items: list[dict]) -> str:
        if not items:
            return ""
        rows = "".join(
            f'<li><span class="mono colname">{html.escape(str(c.get("name", "")))}</span>'
            f'<span class="issues">{html.escape(", ".join(c.get("issues") or []))}</span></li>'
            for c in items
        )
        return f'<div class="callout {cls}"><h3>{label}</h3><ul>{rows}</ul></div>'

    parts.append(_callout_block("fail", "fail", fails))
    parts.append(_callout_block("warn", "warn", warns))
    if quality.get("sampling_note"):
        parts.append(f'<p class="sampling">{html.escape(quality["sampling_note"])}</p>')

    return _panel("quality", "theme-amber", "".join(parts))


def _section_joins(report: dict) -> str:
    joins = report.get("joins") or {}
    candidates = joins.get("candidates") or []
    if not candidates:
        return _panel(
            "related tables",
            "theme-sky",
            '<p class="empty">No candidate join keys found in this database.</p>',
        )

    rows: list[str] = []
    for cand in candidates[:20]:
        tgt = html.escape(str(cand.get("target_table", "")))
        keys = cand.get("join_keys") or []
        best = max((k.get("confidence", 0.0) for k in keys), default=0.0)
        key_html = ", ".join(
            f"<code>{html.escape(str(k.get('source_col', '')))}"
            f" ↔ {html.escape(str(k.get('target_col', '')))}</code>"
            for k in keys[:3]
        )
        rows.append(
            f'<tr><td class="mono">{tgt}</td><td>{key_html}</td>'
            f'<td class="num">{best:.2f}</td></tr>'
        )

    header = (
        "<thead><tr><th>target</th><th>candidate keys</th>"
        '<th class="num">top conf.</th></tr></thead>'
    )
    table_html = f'<table class="joins">{header}<tbody>{"".join(rows)}</tbody></table>'
    return _panel("related tables", "theme-sky", table_html)


def _section_footer(report: dict) -> str:
    command = report.get("command") or ""
    cmd_html = (
        f'<details class="footer-cmd"><summary>Generated with qdo</summary>'
        f'<pre class="mono">{html.escape(command)}</pre></details>'
        if command
        else '<p class="footer-text">Generated with qdo.</p>'
    )
    return f"<footer>{cmd_html}</footer>"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _panel(title: str, theme_class: str, body_html: str) -> str:
    return f"""
    <section class="panel {theme_class}">
      <h2>{html.escape(title)}</h2>
      <div class="panel-body">{body_html}</div>
    </section>
    """


def _null_bar_cell(null_pct: Any) -> str:
    if null_pct is None:
        return '<span class="dim">—</span>'
    try:
        pct = float(null_pct)
    except (TypeError, ValueError):
        return html.escape(str(null_pct))
    pct = max(0.0, min(100.0, pct))
    tone = "ok"
    if pct >= 90:
        tone = "fail"
    elif pct >= 20:
        tone = "warn"
    # 100-unit SVG; CSS scales it.
    bar_w = pct  # percent → unit width
    return (
        f'<span class="null-value">{pct:.1f}%</span>'
        f'<svg class="null-bar" viewBox="0 0 100 6" preserveAspectRatio="none" '
        f'aria-hidden="true">'
        f'<rect class="null-bar-track" x="0" y="0" width="100" height="6" rx="1"/>'
        f'<rect class="null-bar-fill {tone}" x="0" y="0" width="{bar_w:.2f}" '
        f'height="6" rx="1"/>'
        f"</svg>"
    )


# --------------------------------------------------------------------------- #
# Page shell & CSS
# --------------------------------------------------------------------------- #


_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #f4f5f7;
  --card: #ffffff;
  --fg: #1e293b;
  --muted: #64748b;
  --line: #e2e8f0;
  --soft: #f1f5f9;
  --accent: #6366f1;
  --accent-text: #4338ca;
  --ok: #10b981;
  --warn: #f59e0b;
  --fail: #f43f5e;
  --track: #e2e8f0;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f172a;
    --card: #1e293b;
    --fg: #e2e8f0;
    --muted: #94a3b8;
    --line: #334155;
    --soft: #273449;
    --accent: #818cf8;
    --accent-text: #c7d2fe;
    --track: #334155;
  }
}

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.5;
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
}

.page { max-width: 980px; margin: 0 auto; padding: 28px 24px 48px; }

.mono { font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Consolas, monospace; }

/* ── Header ─────────────────────────────────────────────────────────── */
.head {
  margin-bottom: 20px;
  padding-bottom: 18px;
  border-bottom: 3px solid var(--accent);
}
.head-top { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; }
.head .eyebrow {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--accent);
  margin-bottom: 4px;
}
.head h1 {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.9rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--fg);
  line-height: 1.1;
}
.head .lede { font-size: 0.95rem; color: var(--muted); margin-top: 6px; max-width: 60ch; }
.head-meta {
  display: grid;
  grid-template-columns: auto auto;
  gap: 2px 10px;
  font-size: 0.78rem;
  text-align: right;
}
.head-meta .k { color: var(--muted); margin-right: 6px; }
.head-meta .v { color: var(--fg); font-weight: 500; }
.head-meta .code { font-family: 'JetBrains Mono', monospace; font-size: 0.76rem; }

/* ── Panels ─────────────────────────────────────────────────────────── */
.panel {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 16px 18px;
  margin-bottom: 14px;
}
.panel h2 {
  font-size: 0.72rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  padding: 4px 10px;
  border-radius: 5px;
  display: inline-block;
  margin-bottom: 12px;
}
.panel-body { font-size: 0.88rem; }
.panel p + p, .panel p + table, .panel p + .callout, .panel .callout + .callout { margin-top: 10px; }

.theme-indigo  { border-top: 3px solid #6366f1; }
.theme-indigo h2  { background: #eef2ff; color: #4338ca; }
.theme-violet  { border-top: 3px solid #8b5cf6; }
.theme-violet h2  { background: #f5f3ff; color: #6d28d9; }
.theme-amber   { border-top: 3px solid #f59e0b; }
.theme-amber h2   { background: #fffbeb; color: #b45309; }
.theme-emerald { border-top: 3px solid #10b981; }
.theme-emerald h2 { background: #ecfdf5; color: #047857; }
.theme-sky     { border-top: 3px solid #0ea5e9; }
.theme-sky h2     { background: #f0f9ff; color: #0369a1; }

@media (prefers-color-scheme: dark) {
  .theme-indigo h2  { background: #312e81; color: #c7d2fe; }
  .theme-violet h2  { background: #4c1d95; color: #ddd6fe; }
  .theme-amber h2   { background: #451a03; color: #fcd34d; }
  .theme-emerald h2 { background: #064e3b; color: #6ee7b7; }
  .theme-sky h2     { background: #0c4a6e; color: #7dd3fc; }
}

.empty { color: var(--muted); font-style: italic; }
.empty code.cmd { font-style: normal; background: var(--soft); padding: 1px 6px; border-radius: 4px; }

/* ── Tables ─────────────────────────────────────────────────────────── */
table { width: 100%; border-collapse: collapse; }
th, td { padding: 7px 10px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); font-size: 0.85rem; }
th { font-weight: 600; color: var(--muted); text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.06em; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: none; }

.schema td.col-name { white-space: nowrap; }
.schema .mono { font-size: 0.82rem; }
.schema td.type { color: var(--muted); font-size: 0.78rem; }
.schema .pk { font-size: 0.62rem; background: #eef2ff; color: #4338ca; padding: 1px 5px; border-radius: 3px; font-weight: 700; margin-left: 4px; }
.schema .nn { font-size: 0.62rem; background: var(--soft); color: var(--muted); padding: 1px 5px; border-radius: 3px; margin-left: 4px; }
.schema .samples { color: var(--muted); }
.schema code.sample { background: var(--soft); padding: 1px 5px; border-radius: 3px; font-size: 0.76rem; font-family: 'JetBrains Mono', monospace; margin-right: 3px; display: inline-block; margin-bottom: 2px; }
.schema tr.desc td { border-bottom: 1px solid var(--line); padding-top: 0; padding-bottom: 10px; font-size: 0.8rem; color: var(--muted); }
.schema tr.desc .desc-label { font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: var(--accent-text); margin-right: 8px; }

.null-value { font-variant-numeric: tabular-nums; font-size: 0.8rem; }
.null-bar { display: block; width: 100%; height: 6px; margin-top: 3px; }
.null-bar-track { fill: var(--track); }
.null-bar-fill.ok   { fill: var(--ok); }
.null-bar-fill.warn { fill: var(--warn); }
.null-bar-fill.fail { fill: var(--fail); }

.dim { color: var(--muted); }

/* ── Quality callouts ───────────────────────────────────────────────── */
.summary { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.pill { padding: 2px 9px; border-radius: 10px; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
.pill.ok   { background: #ecfdf5; color: #047857; }
.pill.warn { background: #fffbeb; color: #b45309; }
.pill.fail { background: #fff1f2; color: #be123c; }
.callout { border-left: 3px solid var(--line); padding: 8px 12px; background: var(--soft); border-radius: 0 6px 6px 0; margin-top: 10px; }
.callout.fail { border-left-color: var(--fail); }
.callout.warn { border-left-color: var(--warn); }
.callout h3 { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 5px; }
.callout ul { list-style: none; }
.callout li { display: flex; justify-content: space-between; gap: 10px; padding: 2px 0; font-size: 0.82rem; }
.callout .colname { font-size: 0.82rem; color: var(--fg); }
.callout .issues { color: var(--muted); font-size: 0.78rem; }
.ok { color: var(--ok); font-weight: 500; }
.sampling { font-size: 0.76rem; color: var(--muted); font-style: italic; margin-top: 6px; }

/* ── Metadata kv ────────────────────────────────────────────────────── */
table.kv td { border: none; padding: 3px 12px 3px 0; font-size: 0.85rem; }
table.kv td.k { color: var(--muted); width: 110px; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; }
.tag { display: inline-block; background: #f5f3ff; color: #6d28d9; font-size: 0.72rem; padding: 2px 7px; border-radius: 3px; margin-right: 4px; }
@media (prefers-color-scheme: dark) { .tag { background: #4c1d95; color: #ddd6fe; } }

/* ── Joins ──────────────────────────────────────────────────────────── */
.joins code { background: var(--soft); padding: 1px 5px; border-radius: 3px; font-size: 0.76rem; font-family: 'JetBrains Mono', monospace; }

/* ── Footer ─────────────────────────────────────────────────────────── */
footer { margin-top: 24px; padding-top: 14px; border-top: 1px solid var(--line); font-size: 0.78rem; color: var(--muted); }
footer summary { cursor: pointer; }
footer .footer-cmd pre { margin-top: 8px; background: var(--soft); padding: 8px 10px; border-radius: 5px; font-size: 0.76rem; overflow-x: auto; }

/* ── Print ──────────────────────────────────────────────────────────── */
@media print {
  body { background: #fff; color: #000; }
  .panel { break-inside: avoid; border: 1px solid #ccc; box-shadow: none; }
  .head { border-bottom-color: #000; }
  a { color: inherit; text-decoration: none; }
  .schema tr { break-inside: avoid; }
}
"""


_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="page">
{body}
</div>
</body>
</html>
"""
