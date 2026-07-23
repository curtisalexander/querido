"""``qdo bundle`` — portable knowledge archives.

A bundle packages enriched metadata and column sets for a set of tables so
they can be shared across teammates or moved between connections.  See
:mod:`querido.core.bundle` for the file layout and merge semantics.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager

import typer

from querido.cli._errors import friendly_errors
from querido.cli._options import conn_opt

app = typer.Typer(help="Export, import, inspect, or diff knowledge bundles.")


@contextmanager
def _target_connector(target: str):
    """Yield an optional connector for best-effort import drift checks."""
    from querido.config import UnsupportedSchemaVersionError, resolve_connection
    from querido.connectors.base import ConnectorError
    from querido.connectors.factory import create_connector

    try:
        config = resolve_connection(target)
        resource = create_connector(config)
        connector = resource.__enter__()
    except UnsupportedSchemaVersionError:
        raise
    except (ConnectorError, FileNotFoundError, ImportError, ValueError):
        yield None
        return

    try:
        yield connector
    finally:
        resource.__exit__(*sys.exc_info())


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
    connection: str = conn_opt,
    # NOTE: ``-t`` here means ``--tables`` (comma-separated list), NOT the singular
    # ``--table`` of ~20 other commands. Deliberate divergence preserved for CLI
    # back-compat (see L21). The help text says "table names to include" so ``--help``
    # is unambiguous; do not "harmonize" to --table.
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
    from pathlib import Path

    from querido.cli._pipeline import database_command, emit_json
    from querido.config import list_column_sets
    from querido.core.bundle import export_bundle

    table_list = [t.strip() for t in tables.split(",") if t.strip()]
    if not table_list:
        raise typer.BadParameter("--tables must contain at least one name")

    column_sets = list_column_sets(connection=connection) if include_column_sets else []
    with database_command(connection=connection) as ctx:
        manifest = export_bundle(
            connection,
            ctx.connector,
            table_list,
            output,
            column_sets=column_sets,
            redact=redact,
            author=author,
            as_zip=as_zip or Path(output).suffix.lower() == ".zip",
        )

    if emit_json(
        "bundle export",
        {"output": output, "manifest": manifest},
        next_steps=[
            {
                "cmd": f"qdo bundle inspect {output}",
                "why": "Verify the bundle's contents.",
            }
        ],
        connection=connection,
    ):
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
    from querido.cli._pipeline import emit_json
    from querido.config import list_column_sets, save_column_set
    from querido.core.bundle import import_bundle, inspect_bundle

    mapping = _parse_maps(maps or [])
    if apply_flag and inspect_bundle(bundle_path)["column_set_count"]:
        # Validate the destination store before core writes any metadata, so
        # an unsupported column-set schema cannot leave a partial import.
        list_column_sets(connection=target)
    with _target_connector(target) as target_connector:
        report = import_bundle(
            bundle_path,
            target,
            target_connector,
            maps=mapping,
            strategy=strategy,
            apply=apply_flag,
        )

    if apply_flag:
        for column_set in report.get("column_sets") or []:
            name = column_set.get("name")
            if not name:
                continue
            save_column_set(
                target,
                column_set.get("target_table", ""),
                name,
                list(column_set.get("columns") or []),
            )
            column_set["applied"] = True

    if emit_json("bundle import", report, connection=target):
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
    from querido.cli._pipeline import emit_json
    from querido.core.bundle import inspect_bundle

    report = inspect_bundle(bundle_path)

    if emit_json("bundle inspect", report):
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
    from querido.cli._pipeline import emit_json
    from querido.core.bundle import diff_bundles

    report = diff_bundles(a, b)

    if emit_json("bundle diff", report):
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
