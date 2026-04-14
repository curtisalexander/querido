"""``qdo bundle`` — portable knowledge archives.

A bundle packages enriched metadata and column sets for a set of tables so
they can be shared across teammates or moved between connections.  See
:mod:`querido.core.bundle` for the file layout and merge semantics.
"""

from __future__ import annotations

import sys

import typer

from querido.cli._errors import friendly_errors

app = typer.Typer(help="Export, import, inspect, or diff knowledge bundles.")


def _parse_maps(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise typer.BadParameter(f"--map expects old=new, got: {p!r}")
        old, new = p.split("=", 1)
        old, new = old.strip(), new.strip()
        if not old or not new:
            raise typer.BadParameter(f"--map values must be non-empty: {p!r}")
        out[old] = new
    return out


# -- export -------------------------------------------------------------------


@app.command()
@friendly_errors
def export(
    connection: str = typer.Option(
        ..., "--connection", "-c", help="Named connection or file path."
    ),
    tables: str = typer.Option(
        ..., "--tables", "-t", help="Comma-separated table names to include."
    ),
    output: str = typer.Option(
        ..., "--output", "-o", help="Bundle output path (directory or .zip)."
    ),
    include_column_sets: bool = typer.Option(
        True,
        "--column-sets/--no-column-sets",
        help="Include saved column sets for these tables.",
    ),
    redact: bool = typer.Option(
        False,
        "--redact",
        help="Drop sample values and ranges for columns flagged pii: true.",
    ),
    author: str | None = typer.Option(
        None, "--author", help="Override the author string written to the manifest."
    ),
    as_zip: bool = typer.Option(
        False,
        "--zip",
        help="Write a single .zip file instead of a directory.",
    ),
) -> None:
    """Package metadata (and optional column sets) for TABLES into a bundle."""
    from querido.core.bundle import export_bundle
    from querido.output.envelope import emit_envelope, is_structured_format

    table_list = [t.strip() for t in tables.split(",") if t.strip()]
    if not table_list:
        raise typer.BadParameter("--tables must contain at least one name")

    manifest = export_bundle(
        connection,
        table_list,
        output,
        include_column_sets=include_column_sets,
        redact=redact,
        author=author,
        as_zip=as_zip,
    )

    if is_structured_format():
        emit_envelope(
            command="bundle export",
            data={"output": output, "manifest": manifest},
            next_steps=[
                {
                    "cmd": f"qdo bundle inspect {output}",
                    "why": "Verify the bundle's contents.",
                }
            ],
            connection=connection,
        )
        return

    print(f"Wrote {output}", file=sys.stderr)
    n_tables = len(manifest.get("tables") or [])
    n_sets = len(manifest.get("column_sets") or [])
    missing = manifest.get("missing_tables") or []
    print(f"  {n_tables} table(s), {n_sets} column set(s)", file=sys.stderr)
    if missing:
        print(f"  skipped (no metadata): {', '.join(missing)}", file=sys.stderr)


# -- import -------------------------------------------------------------------


@app.command(name="import")
@friendly_errors
def import_cmd(
    bundle_path: str = typer.Argument(..., help="Bundle path (directory or .zip)."),
    target: str = typer.Option(..., "--into", help="Target connection to import into."),
    maps: list[str] = typer.Option(  # noqa: B008
        None,
        "--map",
        help="Rename a table on import: --map old=new (repeatable).",
    ),
    strategy: str = typer.Option(
        "keep-higher-confidence",
        "--strategy",
        help="Conflict resolution: keep-higher-confidence | theirs | mine | ask.",
    ),
    apply_flag: bool = typer.Option(
        False,
        "--apply",
        help="Actually write changes. Default is dry-run diff.",
    ),
) -> None:
    """Import a bundle into --into. Dry-run by default; pass --apply to write."""
    from querido.core.bundle import import_bundle
    from querido.output.envelope import emit_envelope, is_structured_format

    mapping = _parse_maps(maps or [])
    report = import_bundle(
        bundle_path,
        target,
        maps=mapping,
        strategy=strategy,
        apply=apply_flag,
    )

    if is_structured_format():
        emit_envelope(
            command="bundle import",
            data=report,
            connection=target,
        )
        return

    _print_import_report(report, apply=apply_flag)


def _print_import_report(report: dict, *, apply: bool) -> None:
    header = "Applied" if apply else "Dry run — pass --apply to write"
    print(header, file=sys.stderr)
    print(f"  target: {report.get('target_connection')}", file=sys.stderr)
    print(f"  strategy: {report.get('strategy')}", file=sys.stderr)
    print("", file=sys.stderr)

    for t in report.get("tables") or []:
        src = t.get("source_table")
        tgt = t.get("target_table")
        arrow = "→" if src != tgt else "="
        fp = t.get("fingerprint_status", "unknown")
        actions = t.get("field_actions") or []
        writes = sum(1 for a in actions if a.get("action") == "write")
        skips = sum(1 for a in actions if a.get("action") == "skip")
        note = f"schema={fp}"
        print(f"{src} {arrow} {tgt}  [{note}]  {writes} write, {skips} skip", file=sys.stderr)
        for a in actions:
            col = a.get("column") or "(table)"
            field = a.get("field") or ""
            act = a.get("action")
            reason = a.get("reason", "")
            print(f"    {act:5s}  {col}.{field}  ({reason})", file=sys.stderr)

    cs = report.get("column_sets") or []
    if cs:
        print("", file=sys.stderr)
        print("Column sets:", file=sys.stderr)
        for s in cs:
            src = s.get("source_table")
            tgt = s.get("target_table")
            arrow = "→" if src != tgt else "="
            name = s.get("name")
            n_cols = len(s.get("columns") or [])
            marker = "apply" if s.get("applied") else "plan "
            print(
                f"  [{marker}] {src}.{name} {arrow} {tgt}.{name}  ({n_cols} cols)", file=sys.stderr
            )


# -- inspect ------------------------------------------------------------------


@app.command()
@friendly_errors
def inspect(
    bundle_path: str = typer.Argument(..., help="Bundle path (directory or .zip)."),
) -> None:
    """Summarize a bundle's contents."""
    from querido.core.bundle import inspect_bundle
    from querido.output.envelope import emit_envelope, is_structured_format

    report = inspect_bundle(bundle_path)

    if is_structured_format():
        emit_envelope(command="bundle inspect", data=report)
        return

    m = report.get("manifest") or {}
    print(f"Bundle: {bundle_path}")
    print(f"  format_version: {m.get('format_version')}")
    print(f"  qdo_version:    {m.get('qdo_version')}")
    print(f"  author:         {m.get('author')}")
    print(f"  created_at:     {m.get('created_at')}")
    print(f"  source:         {m.get('connection_source')}")
    print(f"  redacted:       {m.get('redacted', False)}")
    print("")
    print(f"Tables ({report.get('metadata_count', 0)}):")
    for entry in m.get("tables") or []:
        print(f"  - {entry.get('name')}  fp={entry.get('schema_fingerprint')}")
    cs = m.get("column_sets") or []
    print("")
    print(f"Column sets ({len(cs)}):")
    for entry in cs:
        n = len(entry.get("columns") or [])
        print(f"  - {entry.get('table')}.{entry.get('name')}  ({n} cols)")


# -- diff ---------------------------------------------------------------------


@app.command()
@friendly_errors
def diff(
    a: str = typer.Argument(..., help="First bundle (dir or .zip)."),
    b: str = typer.Argument(..., help="Second bundle (dir or .zip)."),
) -> None:
    """Compare two bundles and report differences."""
    from querido.core.bundle import diff_bundles
    from querido.output.envelope import emit_envelope, is_structured_format

    report = diff_bundles(a, b)

    if is_structured_format():
        emit_envelope(command="bundle diff", data=report)
        return

    print(f"A: {a}")
    print(f"B: {b}")
    print("")
    if report.get("tables_only_in_a"):
        print("Only in A:")
        for t in report["tables_only_in_a"]:
            print(f"  + {t}")
    if report.get("tables_only_in_b"):
        print("Only in B:")
        for t in report["tables_only_in_b"]:
            print(f"  + {t}")
    drifts = report.get("schema_drifts") or []
    if drifts:
        print("Schema fingerprint drift:")
        for d in drifts:
            print(f"  ! {d.get('table')}  a={d.get('a')}  b={d.get('b')}")
    only_a_cs = report.get("column_sets_only_in_a") or []
    only_b_cs = report.get("column_sets_only_in_b") or []
    if only_a_cs or only_b_cs:
        print("Column sets:")
        for k in only_a_cs:
            print(f"  only in A: {k}")
        for k in only_b_cs:
            print(f"  only in B: {k}")
    if (
        not report.get("tables_only_in_a")
        and not report.get("tables_only_in_b")
        and not drifts
        and not only_a_cs
        and not only_b_cs
    ):
        print("Bundles are equivalent.")
